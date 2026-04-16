from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import PracticeRecordORM, QuestionBankORM, ReportRecordORM, StudentMasteryORM, StudentProfileORM  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.sql_repository import sql_repository  # noqa: E402


client = TestClient(app)


def cleanup_student(student_id: int | None, question_ids: list[str] | None = None) -> None:
    with sql_repository.session() as session:
        if student_id:
            session.execute(delete(PracticeRecordORM).where(PracticeRecordORM.student_profile_id == student_id))
            session.execute(delete(ReportRecordORM).where(ReportRecordORM.student_profile_id == student_id))
            session.execute(delete(StudentMasteryORM).where(StudentMasteryORM.student_profile_id == student_id))
            session.execute(delete(StudentProfileORM).where(StudentProfileORM.id == student_id))
        if question_ids:
            session.execute(delete(QuestionBankORM).where(QuestionBankORM.external_id.in_(question_ids)))


def main() -> None:
    student_id = None

    login = client.post(
        "/auth/login",
        json={"email": "demo@zhuyu.local", "password": "demo123456"},
    )
    assert login.status_code == 200
    headers = {"X-Session-Token": login.json()["token"]}

    topics = client.get("/graph/topics", headers=headers)
    assert topics.status_code == 200
    l2_topic = next((item for item in topics.json() if item.get("level") == 2 and item.get("parent_id")), None)
    assert l2_topic, "no level-2 topic found"

    created = client.post(
        "/students",
        headers=headers,
        json={
            "name": f"学生体验验证{uuid.uuid4().hex[:6]}",
            "grade_level": "初二",
            "target_subject": l2_topic["subject"],
            "target_topic_id": l2_topic["id"],
        },
    )
    assert created.status_code == 200
    student_id = created.json()["id"]

    semantic_qid = f"verify_semantic_blank_{uuid.uuid4().hex[:8]}"
    multi_qid = f"verify_multi_blank_{uuid.uuid4().hex[:8]}"

    try:
        imported = client.post(
            "/teacher/question-bank/import",
            headers=headers,
            json={
                "questions": [
                    {
                        "id": semantic_qid,
                        "knowledge_l1_id": l2_topic["parent_id"],
                        "knowledge_l2_id": l2_topic["id"],
                        "stem": "自变量先确定还是因变量先确定？",
                        "difficulty_level": 2,
                        "knowledge_tiers": ["基础知识点"],
                        "answer": "先确定自变量",
                        "explanation": "自变量决定因变量的取值。",
                        "question_type": "blank",
                        "tags": ["概念"],
                    },
                    {
                        "id": multi_qid,
                        "knowledge_l1_id": l2_topic["parent_id"],
                        "knowledge_l2_id": l2_topic["id"],
                        "stem": "函数关系中常见变量记作 ____ 和 ____。",
                        "difficulty_level": 2,
                        "knowledge_tiers": ["核心知识点"],
                        "answer": "x，y",
                        "explanation": "常见自变量与因变量记作 x 和 y。",
                        "question_type": "blank",
                        "blank_count": 2,
                        "score_points": [
                            {"title": "自变量", "points": 1, "keywords": ["x"]},
                            {"title": "因变量", "points": 1, "keywords": ["y"]},
                        ],
                    },
                ]
            },
        )
        assert imported.status_code == 200

        semantic = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": semantic_qid,
                "student_answer": "先确定自变量",
                "duration_seconds": 10,
            },
        )
        assert semantic.status_code == 200
        assert semantic.json()["score_label"] in {"1/1", "100%"}
        assert semantic.json()["is_correct"] is True
        print("single-blank grading ok")

        structured = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": multi_qid,
                "student_answer": "x，y",
                "blank_answers": ["x", "y"],
                "duration_seconds": 10,
            },
        )
        assert structured.status_code == 200
        assert structured.json()["score"] >= 0.9
        assert structured.json()["is_correct"] is True
        print("structured multi-blank grading ok")

        partial = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": multi_qid,
                "student_answer": "，y",
                "blank_answers": ["", "y"],
                "duration_seconds": 10,
            },
        )
        assert partial.status_code == 200
        assert partial.json()["score"] < 0.8
        assert partial.json()["is_correct"] is False
        print("blank position preservation ok")

        report = client.post(
            f"/students/{student_id}/reports/generate",
            headers=headers,
            json={"target_topic_id": l2_topic["id"]},
        )
        assert report.status_code == 200
        latest = client.get(f"/students/{student_id}/reports/latest", headers=headers)
        assert latest.status_code == 200
        assert latest.json()["id"] == report.json()["id"]
        print("report history ok")

        student_page = client.get("/student")
        assert student_page.status_code == 200
        html = student_page.text
        assert 'data-page="graph"' in html
        assert "knowledgeGraphPreview" in html
        assert "reportHistoryView" in html
        assert "reportTopicId" in html
        print("student markup ok")

        print("student experience verification passed")
    finally:
        cleanup_student(student_id, [semantic_qid, multi_qid])


if __name__ == "__main__":
    main()
