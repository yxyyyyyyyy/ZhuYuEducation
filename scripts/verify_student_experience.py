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

    created = client.post(
        "/students",
        headers=headers,
        json={
            "name": f"学生体验验证{uuid.uuid4().hex[:6]}",
            "grade_level": "七年级",
            "target_subject": "数学",
            "target_topic_id": "functions",
        },
    )
    assert created.status_code == 200
    student_id = created.json()["id"]
    semantic_qid = f"verify_semantic_blank_{uuid.uuid4().hex[:8]}"

    try:
        imported = client.post(
            "/teacher/question-bank/import",
            headers=headers,
            json={
                "questions": [
                    {
                        "id": semantic_qid,
                        "topic_id": "functions",
                        "stem": "自变量先确定还是因变量先确定？",
                        "difficulty": 0.35,
                        "answer": "先确定自变量",
                        "explanation": "自变量决定因变量的取值。",
                        "tags": ["概念"],
                    }
                ]
            },
        )
        assert imported.status_code == 200

        semantic = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": semantic_qid,
                "student_answer": "自变量",
                "duration_seconds": 10,
            },
        )
        assert semantic.status_code == 200
        assert semantic.json()["score_label"] == "1/1"
        assert semantic.json()["evaluation_method"] == "keyword_match"
        assert semantic.json()["is_correct"] is True
        print("single-blank keyword grading ok")

        question = client.get("/questions/q_fun_02", headers=headers)
        assert question.status_code == 200
        assert question.json()["blank_count"] == 2
        assert [item["title"] for item in question.json()["score_points"]] == ["自变量", "因变量"]
        print("multi-blank metadata ok")

        structured = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": "q_fun_02",
                "student_answer": "x，y",
                "blank_answers": ["x", "y"],
                "duration_seconds": 10,
            },
        )
        assert structured.status_code == 200
        assert structured.json()["score_label"] == "2/2"
        assert structured.json()["is_correct"] is True
        print("structured multi-blank grading ok")

        legacy = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": "q_fun_02",
                "student_answer": "x y",
                "duration_seconds": 10,
            },
        )
        assert legacy.status_code == 200
        assert legacy.json()["score_label"] == "2/2"
        assert legacy.json()["is_correct"] is True
        print("legacy whitespace grading ok")

        partial = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": "q_fun_02",
                "student_answer": "，y",
                "blank_answers": ["", "y"],
                "duration_seconds": 10,
            },
        )
        assert partial.status_code == 200
        assert partial.json()["score_label"] == "1/2"
        assert partial.json()["is_correct"] is False
        assert partial.json()["breakdown"][0]["earned_points"] == 0
        assert partial.json()["breakdown"][1]["earned_points"] == 1
        print("blank position preservation ok")

        single_blank = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": "q_fun_01",
                "student_answer": "7",
                "duration_seconds": 10,
            },
        )
        assert single_blank.status_code == 200
        assert single_blank.json()["score_label"] == "1/1"
        print("single-blank regression ok")

        punctuated = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={
                "question_id": "q_lf_02",
                "student_answer": "第一、二",
                "duration_seconds": 10,
            },
        )
        assert punctuated.status_code == 200
        assert punctuated.json()["evaluation_method"] != "multi_blank"
        print("punctuated answer regression ok")

        report = client.post(
            f"/students/{student_id}/reports/generate",
            headers=headers,
            json={"target_topic_id": "functions"},
        )
        assert report.status_code == 200
        latest = client.get(f"/students/{student_id}/reports/latest", headers=headers)
        assert latest.status_code == 200
        assert latest.json()["id"] == report.json()["id"]
        history = client.get(f"/students/{student_id}/reports", headers=headers)
        assert history.status_code == 200
        assert history.json()
        assert history.json()[0]["id"] == report.json()["id"]
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
        cleanup_student(student_id, [semantic_qid])


if __name__ == "__main__":
    main()
