from __future__ import annotations

import sys
import uuid
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
    token = login.json()["token"]
    headers = {"X-Session-Token": token}
    print("auth ok")

    students = client.get("/students", headers=headers)
    assert students.status_code == 200
    student_id = students.json()[0]["id"]
    print("student list ok")

    dashboard = client.get(f"/students/{student_id}/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["profile"]["name"]
    l2_topic = next(
        (item for item in dashboard.json().get("available_topics", []) if item.get("level") == 2 and item.get("parent_id")),
        None,
    )
    assert l2_topic, "no level-2 topic found for student"
    print("dashboard ok")

    diagnosis = client.post(
        f"/students/{student_id}/diagnosis",
        headers=headers,
        json={"target_topic_id": l2_topic["id"]},
    )
    assert diagnosis.status_code == 200
    print("diagnosis ok")

    # 先导入一题，确保错因分析可命中题库题
    custom_qid = f"verify_mistake_{uuid.uuid4().hex[:8]}"
    imported = client.post(
        "/teacher/question-bank/import",
        headers=headers,
        json={
            "questions": [
                {
                    "id": custom_qid,
                    "knowledge_l1_id": l2_topic["parent_id"],
                    "knowledge_l2_id": l2_topic["id"],
                    "stem": "已知 y=2x+1，当 x=3 时 y=？",
                    "difficulty_level": 2,
                    "knowledge_tiers": ["基础知识点"],
                    "answer": "7",
                    "explanation": "代入 x=3 即可。",
                    "question_type": "blank",
                }
            ]
        },
    )
    assert imported.status_code == 200

    practice = client.post(
        f"/students/{student_id}/practice",
        headers=headers,
        json={"topic_id": l2_topic["id"]},
    )
    assert practice.status_code == 200
    question_id = practice.json()["question"]["id"]
    assert question_id
    print("practice ok")

    mistake = client.post(
        f"/students/{student_id}/mistakes/analyze",
        headers=headers,
        json={
            "question_id": custom_qid,
            "student_answer": "6",
            "scratchpad": "测试用错误思路",
        },
    )
    assert mistake.status_code == 200
    print("mistake persistence ok")

    session = client.post(
        f"/students/{student_id}/chat/sessions",
        headers=headers,
        json={"title": "函数辅导"},
    )
    assert session.status_code == 200
    session_id = session.json()["id"]
    print("chat session ok")

    turn = client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={
            "topic_id": l2_topic["id"],
            "content": "我总是分不清自变量和因变量",
            "difficulty_signal": 0.4,
        },
    )
    assert turn.status_code == 200
    assert turn.json()["history"]
    print("chat turn ok")

    report = client.post(
        f"/students/{student_id}/reports/generate",
        headers=headers,
        json={"target_topic_id": l2_topic["id"]},
    )
    assert report.status_code == 200
    print("report persistence ok")

    latest = client.get(f"/students/{student_id}/reports/latest", headers=headers)
    assert latest.status_code == 200
    print("latest report ok")
    print("phase 2 verification passed")


if __name__ == "__main__":
    main()
