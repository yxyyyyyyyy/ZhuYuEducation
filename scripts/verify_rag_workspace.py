from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import ChatMessageORM, ChatSessionORM, KnowledgeChunkORM, KnowledgeDocumentORM, RetrievalCaseORM  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.sql_repository import sql_repository  # noqa: E402


client = TestClient(app)


def cleanup(title: str, case_prefix: str, session_title: str) -> None:
    with sql_repository.session() as session:
        documents = session.execute(
            select(KnowledgeDocumentORM).where(KnowledgeDocumentORM.title == title)
        ).scalars().all()
        for document in documents:
            session.execute(delete(KnowledgeChunkORM).where(KnowledgeChunkORM.document_id == document.id))
            session.delete(document)

        cases = session.execute(
            select(RetrievalCaseORM).where(RetrievalCaseORM.label.like(f"{case_prefix}%"))
        ).scalars().all()
        for case in cases:
            session.delete(case)

        chats = session.execute(
            select(ChatSessionORM).where(ChatSessionORM.title == session_title)
        ).scalars().all()
        for chat in chats:
            session.execute(delete(ChatMessageORM).where(ChatMessageORM.session_id == chat.id))
            session.delete(chat)


def main() -> None:
    marker = uuid.uuid4().hex[:8]
    title = f"RAG工作区验证资料_{marker}"
    session_title = f"RAG工作区验证对话_{marker}"
    case_prefix = f"RAG工作区验证_{marker}"
    cleanup(title, case_prefix, session_title)

    try:
        login = client.post(
            "/auth/login",
            json={"email": "demo@zhuyu.local", "password": "demo123456"},
        )
        assert login.status_code == 200
        headers = {"X-Session-Token": login.json()["token"]}

        content = (
            f"{title}\n"
            "一次函数的翼形斜率证据说明：斜率 k 描述图像倾斜方向和变化速度，截距 b 描述与 y 轴交点。"
        )
        upload = client.post(
            "/teacher/documents/upload",
            headers=headers,
            data={
                "topic_id": "linear_functions",
                "doc_type": "handout",
                "title": title,
                "source_name": "verify-upload.txt",
            },
            files={"file": ("verify-upload.txt", content.encode("utf-8"), "text/plain")},
        )
        assert upload.status_code == 200, upload.text
        document_id = upload.json()["id"]
        assert upload.json()["chunk_count"] >= 1
        print("document upload ok")

        documents = client.get("/teacher/documents", headers=headers)
        assert documents.status_code == 200
        uploaded_doc = next(item for item in documents.json() if item["id"] == document_id)
        assert uploaded_doc["chunk_count"] >= 1
        assert "content_preview" in uploaded_doc
        print("document list metadata ok")

        search = client.post(
            "/teacher/documents/search",
            headers=headers,
            json={
                "query": "翼形斜率证据怎么解释一次函数斜率和截距",
                "topic_id": "linear_functions",
                "strategy": "hybrid",
                "limit": 5,
            },
        )
        assert search.status_code == 200, search.text
        assert any(hit["document_title"] == title for hit in search.json())
        print("document search evidence ok")

        for label, query, topic_id, doc_type in [
            (f"{case_prefix}_斜率", "翼形斜率证据", "linear_functions", "handout"),
            (f"{case_prefix}_函数", "教材里怎么理解函数对应关系", "functions", "textbook"),
        ]:
            created = client.post(
                "/teacher/retrieval-cases",
                headers=headers,
                json={
                    "label": label,
                    "query": query,
                    "expected_topic_id": topic_id,
                    "expected_doc_type": doc_type,
                },
            )
            assert created.status_code == 200, created.text
        cases = client.get("/teacher/retrieval-cases", headers=headers)
        assert cases.status_code == 200
        assert len([case for case in cases.json() if case["label"].startswith(case_prefix)]) == 2
        run = client.post("/teacher/retrieval-cases/run", headers=headers)
        assert run.status_code == 200, run.text
        assert run.json()["total_cases"] >= 2
        assert "hit_at_1" in run.json()
        print("retrieval cases ok")

        students = client.get("/students", headers=headers).json()
        student_id = students[0]["id"]
        chat_session = client.post(
            f"/students/{student_id}/chat/sessions",
            headers=headers,
            json={"title": session_title},
        )
        assert chat_session.status_code == 200
        session_id = chat_session.json()["id"]
        turn = client.post(
            f"/chat/sessions/{session_id}/messages",
            headers=headers,
            json={
                "topic_id": "linear_functions",
                "content": "请根据翼形斜率证据解释一次函数斜率和截距",
                "difficulty_signal": 0.4,
            },
        )
        assert turn.status_code == 200, turn.text
        citations = turn.json()["assistant"]["citations"]
        assert citations and isinstance(citations[0], dict)
        assert any(item["document_title"] == title for item in citations)
        assert any(item["snippet"] for item in citations)
        print("structured chat citations ok")

        deleted = client.delete(f"/teacher/documents/{document_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        remaining = client.get("/teacher/documents", headers=headers).json()
        assert all(item["id"] != document_id for item in remaining)
        print("document delete ok")
        print("rag workspace verification passed")
    finally:
        cleanup(title, case_prefix, session_title)


if __name__ == "__main__":
    main()
