from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import ChatMessageORM, ChatSessionORM, ClassroomEnrollmentORM, PracticeRecordORM, QuestionBankORM, ReportRecordORM, StudentMasteryORM, StudentProfileORM  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.sql_repository import sql_repository  # noqa: E402


client = TestClient(app)


def cleanup_student(student_id: int | None, question_ids: list[str] | None = None) -> None:
    with sql_repository.session() as session:
        if student_id:
            session_ids = select(ChatSessionORM.id).where(ChatSessionORM.student_profile_id == student_id)
            session.execute(delete(ChatMessageORM).where(ChatMessageORM.session_id.in_(session_ids)))
            session.execute(delete(ChatSessionORM).where(ChatSessionORM.student_profile_id == student_id))
            session.execute(delete(ClassroomEnrollmentORM).where(ClassroomEnrollmentORM.student_profile_id == student_id))
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

    classrooms = client.get("/teacher/classrooms", headers=headers)
    assert classrooms.status_code == 200
    classroom = classrooms.json()[0]
    topics = client.get("/graph/topics", headers=headers)
    assert topics.status_code == 200
    l2_topic = next(
        (
            item for item in topics.json()
            if item.get("level") == 2
            and item.get("parent_id")
            and item.get("grade_level") == classroom["grade_level"]
            and item.get("subject") == "数学"
        ),
        None,
    ) or next((item for item in topics.json() if item.get("level") == 2 and item.get("parent_id")), None)
    assert l2_topic, "no level-2 topic found"
    non_math_topic = next(
        (
            item for item in topics.json()
            if item.get("level") == 2
            and item.get("parent_id")
            and item.get("grade_level") == classroom["grade_level"]
            and item.get("subject")
            and item.get("subject") != "数学"
        ),
        None,
    )
    assert non_math_topic, "no non-math current-grade topic found"

    created = client.post(
        "/students",
        headers=headers,
        json={
            "name": f"学生体验验证{uuid.uuid4().hex[:6]}",
            "grade_level": classroom["grade_level"],
            "target_subject": l2_topic["subject"],
            "target_topic_id": l2_topic["id"],
            "school_id": classroom["school_id"],
            "classroom_id": classroom["id"],
            "teacher_user_id": classroom["teacher_user_id"],
            "textbook_id": classroom["textbook_id"],
        },
    )
    assert created.status_code == 200
    student_id = created.json()["id"]

    dashboard = client.get(f"/students/{student_id}/dashboard", headers=headers)
    assert dashboard.status_code == 200
    dashboard_subjects = {item["subject"] for item in dashboard.json()["available_topics"] if item.get("level") == 2}
    assert non_math_topic["subject"] in dashboard_subjects
    print("current-grade all-subject topic scope ok")

    non_math_practice = client.post(
        f"/students/{student_id}/practice",
        headers=headers,
        json={"topic_id": non_math_topic["id"]},
    )
    assert non_math_practice.status_code == 200, non_math_practice.text
    recommended_question = non_math_practice.json()["question"]
    assert recommended_question["grade_level"] == classroom["grade_level"]
    assert recommended_question["subject"] == non_math_topic["subject"]
    print("non-math practice recommendation ok")

    submit_recommended = client.post(
        f"/students/{student_id}/practice/submit",
        headers=headers,
        json={
            "question_id": recommended_question["id"],
            "student_answer": recommended_question["answer"],
            "duration_seconds": 12,
        },
    )
    assert submit_recommended.status_code == 200, submit_recommended.text
    with sql_repository.session() as session:
        saved_record = session.execute(
            select(PracticeRecordORM.id).where(
                PracticeRecordORM.student_profile_id == student_id,
                PracticeRecordORM.question_external_id == recommended_question["id"],
            )
        ).scalars().first()
        assert saved_record is not None
    print("recommended practice submission record ok")

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

        chat_session = client.post(
            f"/students/{student_id}/chat/sessions",
            headers=headers,
            json={"title": "收藏验证"},
        )
        assert chat_session.status_code == 200
        chat_turn = client.post(
            f"/chat/sessions/{chat_session.json()['id']}/messages",
            headers=headers,
            json={"content": "请按步骤讲解这个知识点", "difficulty_signal": 0.45},
        )
        assert chat_turn.status_code == 200
        assistant_message_id = chat_turn.json()["assistant"]["id"]
        favorite = client.put(
            f"/chat/messages/{assistant_message_id}/favorite",
            headers=headers,
            json={"is_favorite": True},
        )
        assert favorite.status_code == 200
        assert favorite.json()["is_favorite"] is True
        history = client.get(f"/chat/sessions/{chat_session.json()['id']}", headers=headers)
        assert history.status_code == 200
        assert any(item["id"] == assistant_message_id and item["is_favorite"] is True for item in history.json())
        print("chat favorite persistence ok")

        student_page = client.get("/student")
        assert student_page.status_code == 200
        html = student_page.text
        assert 'data-page="graph"' not in html
        assert "knowledgeGraphPreview" in html
        assert "knowledgeGraphView" not in html
        assert "reportHistoryView" in html
        assert "reportTopicId" in html
        assert "practiceSubjectId" in html
        assert "chatSubjectId" not in html
        assert "chatTopicId" not in html
        assert "quick-prompt-bar" in html
        assert "studentSelect" not in html
        print("student markup ok")

        print("student experience verification passed")
    finally:
        cleanup_student(student_id, [semantic_qid, multi_qid])


if __name__ == "__main__":
    main()
