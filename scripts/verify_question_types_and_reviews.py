from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.container import container  # noqa: E402
from app.core.database import PracticeRecordORM, QuestionBankORM, StudentMasteryORM, StudentProfileORM  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.sql_repository import sql_repository  # noqa: E402


client = TestClient(app)


def cleanup(student_id: int | None, question_ids: list[str]) -> None:
    with sql_repository.session() as session:
        if student_id:
            session.execute(delete(PracticeRecordORM).where(PracticeRecordORM.student_profile_id == student_id))
            session.execute(delete(StudentMasteryORM).where(StudentMasteryORM.student_profile_id == student_id))
            session.execute(delete(StudentProfileORM).where(StudentProfileORM.id == student_id))
        if question_ids:
            session.execute(delete(QuestionBankORM).where(QuestionBankORM.external_id.in_(question_ids)))


def main() -> None:
    login = client.post("/auth/login", json={"email": "demo@zhuyu.local", "password": "demo123456"})
    assert login.status_code == 200
    headers = {"X-Session-Token": login.json()["token"]}

    created = client.post(
        "/students",
        headers=headers,
        json={
            "name": f"题型复核验证{uuid.uuid4().hex[:6]}",
            "grade_level": "七年级",
            "target_subject": "数学",
            "target_topic_id": "functions",
        },
    )
    assert created.status_code == 200
    student_id = created.json()["id"]

    suffix = uuid.uuid4().hex[:8]
    choice_id = f"verify_choice_{suffix}"
    judgment_id = f"verify_judgment_{suffix}"
    pending_id = f"verify_pending_{suffix}"
    original_api_key = container.llm_service.api_key

    try:
        imported = client.post(
            "/teacher/question-bank/import",
            headers=headers,
            json={
                "questions": [
                    {
                        "id": choice_id,
                        "topic_id": "functions",
                        "stem": "在函数 y = 2x + 1 中，哪个量通常作为自变量？",
                        "difficulty": 0.3,
                        "answer": "A",
                        "explanation": "x 是输入量，y 随 x 变化。",
                        "question_type": "choice",
                        "options": [
                            {"key": "A", "content": "x"},
                            {"key": "B", "content": "y"},
                            {"key": "C", "content": "2"},
                            {"key": "D", "content": "1"},
                        ],
                        "tags": ["选择题"],
                    },
                    {
                        "id": judgment_id,
                        "topic_id": "linear_functions",
                        "stem": "判断：一次函数 y=kx+b 中，k 表示斜率。",
                        "difficulty": 0.35,
                        "answer": "正确",
                        "explanation": "k 是斜率，b 是截距。",
                        "question_type": "judgment",
                        "tags": ["判断题"],
                    },
                    {
                        "id": pending_id,
                        "topic_id": "functions",
                        "stem": "某出租车收费规则可表示为 y = 2x + 8，这里的 8 表示什么？",
                        "difficulty": 0.6,
                        "answer": "8 表示起步价（固定费用）",
                        "explanation": "当 x=0 时仍需支付 8 元。",
                        "question_type": "blank",
                        "tags": ["复核验证"],
                    },
                ]
            },
        )
        assert imported.status_code == 200

        choice = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={"question_id": choice_id, "student_answer": "A", "duration_seconds": 8},
        )
        assert choice.status_code == 200
        assert choice.json()["is_correct"] is True
        assert choice.json()["evaluation_method"] == "choice"
        assert choice.json()["review_status"] == "graded"
        print("choice grading ok")

        judgment = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={"question_id": judgment_id, "student_answer": "对", "duration_seconds": 8},
        )
        assert judgment.status_code == 200
        assert judgment.json()["is_correct"] is True
        assert judgment.json()["evaluation_method"] == "judgment"
        assert judgment.json()["review_status"] == "graded"
        print("judgment grading ok")

        container.llm_service.api_key = ""
        pending = client.post(
            f"/students/{student_id}/practice/submit",
            headers=headers,
            json={"question_id": pending_id, "student_answer": "起步价", "duration_seconds": 8},
        )
        assert pending.status_code == 200
        pending_payload = pending.json()
        assert pending_payload["review_status"] == "pending_review"
        assert pending_payload["review_record_id"]
        assert pending_payload["mastery_delta"] == 0
        print("pending teacher review creation ok")

        reviews = client.get("/teacher/practice-reviews?status=pending", headers=headers)
        assert reviews.status_code == 200
        review_items = [item for item in reviews.json() if item["record_id"] == pending_payload["review_record_id"]]
        assert review_items
        assert review_items[0]["student_answer"] == "起步价"
        print("teacher review list ok")

        resolved = client.post(
            f"/teacher/practice-reviews/{pending_payload['review_record_id']}",
            headers=headers,
            json={"is_correct": True, "score": 1.0, "feedback": "核心含义正确。"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["evaluation_status"] == "reviewed"
        assert resolved.json()["evaluation_method"] == "teacher_review"
        assert resolved.json()["score"] == 1.0
        print("teacher review resolve ok")

        template = client.get("/teacher/question-bank/csv-template", headers=headers)
        assert template.status_code == 200
        assert "选项" in template.text
        assert "judgment" in template.text
        assert "score_points" not in template.text or "得分点" in template.text
        unauthorized_template = client.get("/teacher/question-bank/csv-template")
        assert unauthorized_template.status_code == 401
        print("authenticated csv template ok")

        teacher_page = client.get("/teacher")
        assert teacher_page.status_code == 200
        html = teacher_page.text
        assert 'data-page="practice-review"' in html
        assert "downloadTemplateButton" in html
        assert "tdesign-web-components@1.2.5" in html
        print("teacher markup ok")

        student_page = client.get("/student")
        assert student_page.status_code == 200
        assert "tdesign-web-components@1.2.5" in student_page.text
        student_js = client.get("/static/student.js")
        assert student_js.status_code == 200
        assert "studentJudgmentOption" in student_js.text
        print("question type review verification passed")
    finally:
        container.llm_service.api_key = original_api_key
        cleanup(student_id, [choice_id, judgment_id, pending_id])


if __name__ == "__main__":
    main()
