from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy import delete, select

from app.core.database import AuthSessionORM, UserORM
from app.domain.models import AuthResponse, LoginRequest, RegisterRequest, UserSummary
from app.repositories.sql_repository import sql_repository


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class AuthService:
    def register(self, request: RegisterRequest) -> AuthResponse:
        return self.create_user(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            role="student",
            school_id=None,
            issue_token=True,
        )

    def create_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: str = "student",
        school_id: int | None = None,
        issue_token: bool = False,
    ) -> AuthResponse:
        with sql_repository.session() as session:
            existing = session.execute(select(UserORM).where(UserORM.email == email)).scalars().first()
            if existing:
                raise ValueError("email already exists")

            user = UserORM(
                email=email,
                password_hash=pwd_context.hash(password),
                full_name=full_name,
                role=role,
                school_id=school_id,
            )
            session.add(user)
            session.flush()
            token = secrets.token_urlsafe(24) if issue_token else ""
            if issue_token:
                auth_session = AuthSessionORM(user_id=user.id, token=token)
                session.add(auth_session)
            return AuthResponse(
                token=token,
                user=UserSummary(id=user.id, email=user.email, full_name=user.full_name, role=user.role, school_id=user.school_id),
            )

    def login(self, request: LoginRequest) -> AuthResponse:
        with sql_repository.session() as session:
            user = session.execute(select(UserORM).where(UserORM.email == request.email)).scalars().first()
            if not user or not pwd_context.verify(request.password, user.password_hash):
                raise ValueError("invalid credentials")

            token = secrets.token_urlsafe(24)
            session.add(AuthSessionORM(user_id=user.id, token=token))
            return AuthResponse(
                token=token,
                user=UserSummary(id=user.id, email=user.email, full_name=user.full_name, role=user.role, school_id=user.school_id),
            )

    def get_user_by_token(self, token: str) -> UserSummary | None:
        with sql_repository.session() as session:
            auth = session.execute(select(AuthSessionORM).where(AuthSessionORM.token == token)).scalars().first()
            if not auth:
                return None
            if self._is_expired(auth.created_at):
                session.delete(auth)
                return None
            user = session.execute(select(UserORM).where(UserORM.id == auth.user_id)).scalars().first()
            if not user:
                return None
            return UserSummary(id=user.id, email=user.email, full_name=user.full_name, role=user.role, school_id=user.school_id)

    def logout(self, token: str) -> None:
        with sql_repository.session() as session:
            session.execute(delete(AuthSessionORM).where(AuthSessionORM.token == token))

    def set_password(self, user_id: int, new_password: str) -> None:
        if len(new_password or "") < 8:
            raise ValueError("password length must be at least 8")
        with sql_repository.session() as session:
            user = session.execute(select(UserORM).where(UserORM.id == user_id)).scalars().first()
            if not user:
                raise ValueError("user not found")
            user.password_hash = pwd_context.hash(new_password)
            session.execute(delete(AuthSessionORM).where(AuthSessionORM.user_id == user_id))

    def _is_expired(self, created_at: datetime) -> bool:
        try:
            ttl_hours = float(os.getenv("SESSION_TTL_HOURS", "168"))
        except ValueError:
            ttl_hours = 168.0
        if ttl_hours <= 0:
            return False
        return created_at < datetime.utcnow() - timedelta(hours=ttl_hours)

    def ensure_demo_user(self) -> None:
        with sql_repository.session() as session:
            existing = session.execute(select(UserORM).where(UserORM.email == "demo@zhuyu.local")).scalars().first()
            if existing:
                existing.password_hash = pwd_context.hash("demo123456")
                existing.full_name = "祝余演示账号"
                existing.role = "teacher"
                return
            session.add(
                UserORM(
                    email="demo@zhuyu.local",
                    password_hash=pwd_context.hash("demo123456"),
                    full_name="祝余演示账号",
                    role="teacher",
                )
            )
