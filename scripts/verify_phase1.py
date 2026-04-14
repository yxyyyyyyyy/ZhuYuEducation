from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


client = TestClient(app)


def sample_mastery() -> dict:
    return {
        "arithmetic": {
            "topic_id": "arithmetic",
            "mastery": 0.82,
            "practice_count": 12,
            "correct_count": 10,
            "last_practiced_at": "2026-04-03",
            "recent_errors": []
        },
        "equations": {
            "topic_id": "equations",
            "mastery": 0.52,
            "practice_count": 8,
            "correct_count": 4,
            "last_practiced_at": "2026-04-04",
            "recent_errors": ["移项符号错误"]
        },
        "functions": {
            "topic_id": "functions",
            "mastery": 0.43,
            "practice_count": 5,
            "correct_count": 2,
            "last_practiced_at": "2026-04-05",
            "recent_errors": ["不理解自变量和因变量"]
        },
        "linear_functions": {
            "topic_id": "linear_functions",
            "mastery": 0.2,
            "practice_count": 1,
            "correct_count": 0,
            "last_practiced_at": "2026-04-05",
            "recent_errors": ["不会判断斜率和截距"]
        }
    }


def main() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    print("health ok")

    topic = client.get("/graph/topics/functions")
    assert topic.status_code == 200
    assert topic.json()["name"] == "函数"
    print("graph ok")

    diagnosis = client.post(
        "/diagnosis/evaluate",
        json={
            "student_id": "stu_001",
            "target_topic_id": "linear_functions",
            "current_mastery": sample_mastery(),
        },
    )
    assert diagnosis.status_code == 200
    diagnosis_body = diagnosis.json()
    assert diagnosis_body["learning_path"]
    print("diagnosis ok")

    practice = client.post(
        "/practice/next",
        json={
            "student_id": "stu_001",
            "topic_id": "functions",
            "current_mastery": sample_mastery(),
            "recent_question_ids": ["q_fun_01"],
        },
    )
    assert practice.status_code == 200
    assert practice.json()["question"]["topic_id"] == "functions"
    print("practice ok")

    mistake = client.post(
        "/mistakes/analyze",
        json={
            "student_id": "stu_001",
            "topic_id": "functions",
            "question_id": "q_fun_02",
            "student_answer": "y 是自变量",
            "correct_answer": "自变量是 x，因变量是 y",
            "problem_text": "函数 y = x + 5 中，自变量和因变量分别是什么？",
            "scratchpad": "我觉得 y 在左边所以是自变量"
        },
    )
    assert mistake.status_code == 200
    print("mistake analysis ok")

    tutor = client.post(
        "/tutor/respond",
        json={
            "student_id": "stu_001",
            "topic_id": "functions",
            "question": "我总是分不清自变量和因变量",
            "current_mastery": sample_mastery(),
            "difficulty_signal": 0.4
        },
    )
    assert tutor.status_code == 200
    print("tutor ok")

    report = client.post(
        "/reports/generate",
        json={
            "student_id": "stu_001",
            "student_name": "小余",
            "target_topic_id": "linear_functions",
            "current_mastery": sample_mastery(),
            "recent_mistakes": [mistake.json()],
        },
    )
    assert report.status_code == 200
    assert len(report.json()["review_plan"]) == 4
    print("report ok")
    print("phase 1 verification passed")


if __name__ == "__main__":
    main()
