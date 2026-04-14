from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.core.database import AuthSessionORM, ChatMessageORM, ChatSessionORM, UserORM  # noqa: E402
from app.repositories.sql_repository import sql_repository  # noqa: E402


client = TestClient(app)


def cleanup(other_email: str, demo_session_id: int | None) -> None:
    with sql_repository.session() as session:
        if demo_session_id is not None:
            session.execute(delete(ChatMessageORM).where(ChatMessageORM.session_id == demo_session_id))
            session.execute(delete(ChatSessionORM).where(ChatSessionORM.id == demo_session_id))

        if other_email:
            user = session.execute(select(UserORM).where(UserORM.email == other_email)).scalars().first()
            if user:
                session.execute(delete(AuthSessionORM).where(AuthSessionORM.user_id == user.id))
                session.delete(user)


def main() -> None:
    other_email = ""
    demo_session_id = None
    try:
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ok"
        print("readiness ok")

        homepage = client.get("/")
        assert homepage.status_code == 200
        assert homepage.headers["x-content-type-options"] == "nosniff"
        assert homepage.headers["x-frame-options"] == "DENY"
        print("security headers ok")

        demo_login = client.post(
            "/auth/login",
            json={"email": "demo@zhuyu.local", "password": "demo123456"},
        )
        assert demo_login.status_code == 200
        demo_headers = {"X-Session-Token": demo_login.json()["token"]}

        students = client.get("/students", headers=demo_headers)
        assert students.status_code == 200
        demo_student_id = students.json()[0]["id"]

        chat_session = client.post(
            f"/students/{demo_student_id}/chat/sessions",
            headers=demo_headers,
            json={"title": "权限验证对话"},
        )
        assert chat_session.status_code == 200
        demo_session_id = chat_session.json()["id"]

        other_email = f"verify_{uuid.uuid4().hex[:8]}@zhuyu.local"
        other_register = client.post(
            "/auth/register",
            json={"email": other_email, "password": "verify123456", "full_name": "权限验证账号"},
        )
        assert other_register.status_code == 200
        other_headers = {"X-Session-Token": other_register.json()["token"]}

        foreign_dashboard = client.get(f"/students/{demo_student_id}/dashboard", headers=other_headers)
        assert foreign_dashboard.status_code == 404

        foreign_chat = client.get(f"/chat/sessions/{demo_session_id}", headers=other_headers)
        assert foreign_chat.status_code == 404
        print("cross-account access guard ok")

        logout = client.post("/auth/logout", headers=other_headers)
        assert logout.status_code == 200

        after_logout = client.get("/auth/me", headers=other_headers)
        assert after_logout.status_code == 401
        print("logout ok")
        print("production readiness verification passed")
    finally:
        cleanup(other_email, demo_session_id)


if __name__ == "__main__":
    main()
