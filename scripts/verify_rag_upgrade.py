from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


client = TestClient(app)


def main() -> None:
    login = client.post(
        "/auth/login",
        json={"email": "demo@zhuyu.local", "password": "demo123456"},
    )
    assert login.status_code == 200
    headers = {"X-Session-Token": login.json()["token"]}

    textbook_hits = client.post(
        "/teacher/documents/search",
        headers=headers,
        json={"query": "教材里怎么理解函数对应关系", "topic_id": "functions", "limit": 3},
    )
    assert textbook_hits.status_code == 200
    textbook_results = textbook_hits.json()
    assert textbook_results
    print("textbook-oriented retrieval ok")

    handout_hits = client.post(
        "/teacher/documents/search",
        headers=headers,
        json={"query": "讲义里一次函数的斜率和截距", "topic_id": "linear_functions", "limit": 3},
    )
    assert handout_hits.status_code == 200
    handout_results = handout_hits.json()
    assert handout_results
    assert handout_results[0]["doc_type"] in {"handout", "textbook", "solution"}
    print("hybrid vector retrieval ok")

    student_list = client.get("/students", headers=headers).json()
    student_id = student_list[0]["id"]
    session = client.post(
        f"/students/{student_id}/chat/sessions",
        headers=headers,
        json={"title": "RAG 检索测试"},
    )
    session_id = session.json()["id"]
    turn = client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={
            "topic_id": "linear_functions",
            "content": "请结合讲义解释一次函数里的斜率和截距",
            "difficulty_signal": 0.7,
        },
    )
    assert turn.status_code == 200
    assert turn.json()["assistant"]["citations"]
    print("rag citation flow ok")
    print("rag upgrade verification passed")


if __name__ == "__main__":
    main()
