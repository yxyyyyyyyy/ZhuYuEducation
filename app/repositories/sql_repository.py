from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager

from sqlalchemy import desc, select

from app.core.database import (
    AuthSessionORM,
    ChatMessageORM,
    ChatSessionORM,
    MistakeRecordORM,
    RagDocumentORM,
    ReportRecordORM,
    SessionLocal,
    StudentMasteryORM,
    StudentProfileORM,
    UserORM,
)


class SqlRepository:
    @contextmanager
    def session(self):
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def first(self, session, stmt):
        return session.execute(stmt).scalars().first()

    def list(self, session, stmt):
        return list(session.execute(stmt).scalars().all())

    def latest_report(self, session, student_profile_id: int):
        stmt = (
            select(ReportRecordORM)
            .where(ReportRecordORM.student_profile_id == student_profile_id)
            .order_by(desc(ReportRecordORM.created_at))
            .limit(1)
        )
        return self.first(session, stmt)

    def recent_mistakes(self, session, student_profile_id: int, limit: int = 8):
        stmt = (
            select(MistakeRecordORM)
            .where(MistakeRecordORM.student_profile_id == student_profile_id)
            .order_by(desc(MistakeRecordORM.created_at))
            .limit(limit)
        )
        return self.list(session, stmt)

    def recent_sessions(self, session, student_profile_id: int, limit: int = 8):
        stmt = (
            select(ChatSessionORM)
            .where(ChatSessionORM.student_profile_id == student_profile_id)
            .order_by(desc(ChatSessionORM.updated_at))
            .limit(limit)
        )
        return self.list(session, stmt)


sql_repository = SqlRepository()
