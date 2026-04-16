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
    token = login.json()["token"]
    headers = {"X-Session-Token": token}

    teacher = client.get("/teacher/dashboard", headers=headers)
    assert teacher.status_code == 200
    assert teacher.json()["total_students"] >= 1
    print("teacher dashboard ok")

    topics = client.get("/graph/topics", headers=headers)
    assert topics.status_code == 200
    l2_topic = next((item for item in topics.json() if item.get("level") == 2 and item.get("parent_id")), None)
    assert l2_topic, "no level-2 topic found"

    imported = client.post(
        "/teacher/question-bank/import",
        headers=headers,
        json={
            "questions": [
                {
                    "id": "verify_q_01",
                    "knowledge_l1_id": l2_topic["parent_id"],
                    "knowledge_l2_id": l2_topic["id"],
                    "stem": "自变量先确定还是因变量先确定？",
                    "difficulty_level": 2,
                    "knowledge_tiers": ["基础知识点"],
                    "answer": "先确定自变量",
                    "explanation": "自变量决定因变量的取值。",
                    "tags": ["概念"],
                }
            ]
        },
    )
    assert imported.status_code == 200
    print("question import ok")

    students = client.get("/students", headers=headers).json()
    student_id = students[0]["id"]

    submit = client.post(
        f"/students/{student_id}/practice/submit",
        headers=headers,
        json={
            "question_id": "verify_q_01",
            "student_answer": "先确定自变量",
            "duration_seconds": 42,
        },
    )
    assert submit.status_code == 200
    assert submit.json()["is_correct"] is True
    print("practice submit ok")

    analytics = client.get("/teacher/analytics/practice", headers=headers)
    assert analytics.status_code == 200
    assert analytics.json()["total_attempts"] >= 1
    print("practice analytics ok")

    docs = client.post(
        "/teacher/documents/import",
        headers=headers,
        json={
            "documents": [
                {
                    "title": "一次函数教师讲义",
                    "topic_id": l2_topic["id"],
                    "doc_type": "handout",
                    "source_name": "教师讲义 C1",
                    "content": "一次函数图像教学时，先引导学生理解斜率与截距，再把解析式映射到图像。",
                }
            ]
        },
    )
    assert docs.status_code == 200
    print("document import ok")

    search = client.post(
        "/teacher/documents/search",
        headers=headers,
        json={
            "query": "一次函数的斜率和截距",
            "topic_id": l2_topic["id"],
            "limit": 5,
        },
    )
    assert search.status_code == 200
    assert len(search.json()) >= 1
    print("document search ok")
    print("phase 3 verification passed")


if __name__ == "__main__":
    main()
