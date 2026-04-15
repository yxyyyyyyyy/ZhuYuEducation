from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    inspect,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), default="student", index=True)
    school_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthSessionORM(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StudentProfileORM(Base):
    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    school_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    classroom_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    teacher_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    textbook_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    grade_level: Mapped[str] = mapped_column(String(80))
    target_subject: Mapped[str] = mapped_column(String(80))
    target_topic_id: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StudentMasteryORM(Base):
    __tablename__ = "student_mastery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    topic_id: Mapped[str] = mapped_column(String(120), index=True)
    mastery: Mapped[float] = mapped_column(Float)
    practice_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    last_practiced_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recent_errors: Mapped[list] = mapped_column(JSON, default=list)


class ChatSessionORM(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessageORM(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MistakeRecordORM(Base):
    __tablename__ = "mistake_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    topic_id: Mapped[str] = mapped_column(String(120), index=True)
    question_id: Mapped[str] = mapped_column(String(120))
    question_stem: Mapped[str] = mapped_column(Text)
    student_answer: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80))
    explanation: Mapped[str] = mapped_column(Text)
    correction_advice: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReportRecordORM(Base):
    __tablename__ = "report_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    overall_mastery: Mapped[float] = mapped_column(Float)
    diagnostic_summary: Mapped[str] = mapped_column(Text)
    strong_topics: Mapped[list] = mapped_column(JSON, default=list)
    weak_topics: Mapped[list] = mapped_column(JSON, default=list)
    next_actions: Mapped[list] = mapped_column(JSON, default=list)
    review_plan: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RagDocumentORM(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)


class ClassroomORM(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    textbook_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    grade_level: Mapped[str] = mapped_column(String(80), default="")
    invite_code: Mapped[str] = mapped_column(String(40), default=lambda: f"ZYU-{secrets.token_hex(3).upper()}", unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SchoolORM(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    region: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnnouncementORM(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    content_html: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    is_pinned: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnnouncementDraftORM(Base):
    __tablename__ = "announcement_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    school_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TextbookORM(Base):
    __tablename__ = "textbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_default: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeNodeORM(Base):
    __tablename__ = "knowledge_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(Integer, index=True)
    textbook_id: Mapped[int] = mapped_column(Integer, index=True)
    node_key: Mapped[str] = mapped_column(String(120), index=True)
    parent_node_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    level: Mapped[int] = mapped_column(Integer, index=True)
    subject: Mapped[str] = mapped_column(String(80), default="", index=True)
    grade_level: Mapped[str] = mapped_column(String(80), default="", index=True)
    topic_ref_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClassroomEnrollmentORM(Base):
    __tablename__ = "classroom_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), index=True)
    student_profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)


class QuestionBankORM(Base):
    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    topic_id: Mapped[str] = mapped_column(String(120), index=True)
    stem: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[float] = mapped_column(Float)
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(40), default="blank")
    options: Mapped[list] = mapped_column(JSON, default=list)
    blank_count: Mapped[int] = mapped_column(Integer, default=1)
    score_points: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    source: Mapped[str] = mapped_column(String(40), default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PracticeRecordORM(Base):
    __tablename__ = "practice_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    question_external_id: Mapped[str] = mapped_column(String(120), index=True)
    topic_id: Mapped[str] = mapped_column(String(120), index=True)
    recommended_band: Mapped[str] = mapped_column(String(40))
    student_answer: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    earned_points: Mapped[float] = mapped_column(Float, default=0.0)
    total_points: Mapped[float] = mapped_column(Float, default=1.0)
    evaluation_method: Mapped[str] = mapped_column(String(80), default="exact")
    feedback: Mapped[str] = mapped_column(Text, default="")
    evaluation_status: Mapped[str] = mapped_column(String(40), default="graded", index=True)
    review_reason: Mapped[str] = mapped_column(Text, default="")
    mastery_applied: Mapped[bool] = mapped_column(Integer, default=1)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeDocumentORM(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeChunkORM(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    teacher_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    topic_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(255))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RetrievalCaseORM(Base):
    __tablename__ = "retrieval_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(255))
    query: Mapped[str] = mapped_column(Text)
    expected_topic_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_doc_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "zhuyu_phase2.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_database() -> None:
    Base.metadata.create_all(engine)
    _migrate_sqlite_schema()


def _migrate_sqlite_schema() -> None:
    inspector = inspect(engine)
    migration_sql = []
    existing_tables = set(inspector.get_table_names())

    if "knowledge_chunks" in existing_tables:
        chunk_columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
        if "teacher_user_id" not in chunk_columns:
            migration_sql.append("ALTER TABLE knowledge_chunks ADD COLUMN teacher_user_id INTEGER")
        if "embedding" not in chunk_columns:
            migration_sql.append("ALTER TABLE knowledge_chunks ADD COLUMN embedding JSON")
        if "embedding_model" not in chunk_columns:
            migration_sql.append("ALTER TABLE knowledge_chunks ADD COLUMN embedding_model VARCHAR(120)")
        if "embedding_dim" not in chunk_columns:
            migration_sql.append("ALTER TABLE knowledge_chunks ADD COLUMN embedding_dim INTEGER")

    if "knowledge_documents" in existing_tables:
        document_columns = {column["name"] for column in inspector.get_columns("knowledge_documents")}
        if "teacher_user_id" not in document_columns:
            migration_sql.append("ALTER TABLE knowledge_documents ADD COLUMN teacher_user_id INTEGER")

    if "users" in existing_tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in user_columns:
            migration_sql.append("ALTER TABLE users ADD COLUMN role VARCHAR(40) DEFAULT 'student'")
        if "school_id" not in user_columns:
            migration_sql.append("ALTER TABLE users ADD COLUMN school_id INTEGER")

    if "student_profiles" in existing_tables:
        profile_columns = {column["name"] for column in inspector.get_columns("student_profiles")}
        if "school_id" not in profile_columns:
            migration_sql.append("ALTER TABLE student_profiles ADD COLUMN school_id INTEGER")
        if "classroom_id" not in profile_columns:
            migration_sql.append("ALTER TABLE student_profiles ADD COLUMN classroom_id INTEGER")
        if "teacher_user_id" not in profile_columns:
            migration_sql.append("ALTER TABLE student_profiles ADD COLUMN teacher_user_id INTEGER")
        if "textbook_id" not in profile_columns:
            migration_sql.append("ALTER TABLE student_profiles ADD COLUMN textbook_id INTEGER")

    if "classrooms" in existing_tables:
        classroom_columns = {column["name"] for column in inspector.get_columns("classrooms")}
        if "school_id" not in classroom_columns:
            migration_sql.append("ALTER TABLE classrooms ADD COLUMN school_id INTEGER")
        if "grade_level" not in classroom_columns:
            migration_sql.append("ALTER TABLE classrooms ADD COLUMN grade_level VARCHAR(80) DEFAULT ''")
        if "invite_code" not in classroom_columns:
            migration_sql.append("ALTER TABLE classrooms ADD COLUMN invite_code VARCHAR(40)")
        if "textbook_id" not in classroom_columns:
            migration_sql.append("ALTER TABLE classrooms ADD COLUMN textbook_id INTEGER")

    if "announcements" in existing_tables:
        announcement_columns = {column["name"] for column in inspector.get_columns("announcements")}
        if "content_html" not in announcement_columns:
            migration_sql.append("ALTER TABLE announcements ADD COLUMN content_html TEXT")
        if "summary" not in announcement_columns:
            migration_sql.append("ALTER TABLE announcements ADD COLUMN summary TEXT DEFAULT ''")
        if "is_pinned" not in announcement_columns:
            migration_sql.append("ALTER TABLE announcements ADD COLUMN is_pinned INTEGER DEFAULT 0")
        if "updated_at" not in announcement_columns:
            migration_sql.append("ALTER TABLE announcements ADD COLUMN updated_at DATETIME")

    if "question_bank" in existing_tables:
        question_columns = {column["name"] for column in inspector.get_columns("question_bank")}
        if "question_type" not in question_columns:
            migration_sql.append("ALTER TABLE question_bank ADD COLUMN question_type VARCHAR(40) DEFAULT 'blank'")
        if "options" not in question_columns:
            migration_sql.append("ALTER TABLE question_bank ADD COLUMN options JSON")
        if "blank_count" not in question_columns:
            migration_sql.append("ALTER TABLE question_bank ADD COLUMN blank_count INTEGER DEFAULT 1")
        if "score_points" not in question_columns:
            migration_sql.append("ALTER TABLE question_bank ADD COLUMN score_points JSON")
        if "status" not in question_columns:
            migration_sql.append("ALTER TABLE question_bank ADD COLUMN status VARCHAR(20) DEFAULT 'approved'")
        if "source" not in question_columns:
            migration_sql.append("ALTER TABLE question_bank ADD COLUMN source VARCHAR(40) DEFAULT 'seed'")

    if "practice_records" in existing_tables:
        practice_columns = {column["name"] for column in inspector.get_columns("practice_records")}
        if "score" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN score FLOAT DEFAULT 0.0")
        if "earned_points" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN earned_points FLOAT DEFAULT 0.0")
        if "total_points" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN total_points FLOAT DEFAULT 1.0")
        if "evaluation_method" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN evaluation_method VARCHAR(80) DEFAULT 'exact'")
        if "feedback" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN feedback TEXT DEFAULT ''")
        if "evaluation_status" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN evaluation_status VARCHAR(40) DEFAULT 'graded'")
        if "review_reason" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN review_reason TEXT DEFAULT ''")
        if "mastery_applied" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN mastery_applied INTEGER DEFAULT 1")
        if "reviewed_at" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN reviewed_at DATETIME")
        if "reviewed_by_user_id" not in practice_columns:
            migration_sql.append("ALTER TABLE practice_records ADD COLUMN reviewed_by_user_id INTEGER")

    if not migration_sql:
        return
    with engine.begin() as connection:
        for statement in migration_sql:
            connection.exec_driver_sql(statement)
        if "question_bank" in existing_tables:
            connection.exec_driver_sql("UPDATE question_bank SET question_type = 'blank' WHERE question_type IS NULL OR question_type = ''")
            connection.exec_driver_sql("UPDATE question_bank SET blank_count = 1 WHERE blank_count IS NULL OR blank_count <= 0")
            connection.exec_driver_sql("UPDATE question_bank SET options = '[]' WHERE options IS NULL")
            connection.exec_driver_sql("UPDATE question_bank SET score_points = '[]' WHERE score_points IS NULL")
        if "users" in existing_tables:
            connection.exec_driver_sql("UPDATE users SET role = 'student' WHERE role IS NULL OR role = ''")
            connection.exec_driver_sql("UPDATE users SET role = 'teacher' WHERE email = 'demo@zhuyu.local'")
        if "classrooms" in existing_tables:
            rows = connection.exec_driver_sql("SELECT id FROM classrooms WHERE invite_code IS NULL OR invite_code = ''").fetchall()
            for row in rows:
                connection.exec_driver_sql(
                    "UPDATE classrooms SET invite_code = ? WHERE id = ?",
                    (f"ZYU-{secrets.token_hex(3).upper()}", row[0]),
                )
        if "practice_records" in existing_tables:
            connection.exec_driver_sql("UPDATE practice_records SET score = CASE WHEN is_correct = 1 THEN 1.0 ELSE 0.0 END WHERE score IS NULL")
            connection.exec_driver_sql("UPDATE practice_records SET earned_points = CASE WHEN is_correct = 1 THEN 1.0 ELSE 0.0 END WHERE earned_points IS NULL")
            connection.exec_driver_sql("UPDATE practice_records SET total_points = 1.0 WHERE total_points IS NULL OR total_points <= 0")
            connection.exec_driver_sql("UPDATE practice_records SET evaluation_method = 'exact' WHERE evaluation_method IS NULL OR evaluation_method = ''")
            connection.exec_driver_sql("UPDATE practice_records SET feedback = '' WHERE feedback IS NULL")
            connection.exec_driver_sql("UPDATE practice_records SET evaluation_status = 'graded' WHERE evaluation_status IS NULL OR evaluation_status = ''")
            connection.exec_driver_sql("UPDATE practice_records SET review_reason = '' WHERE review_reason IS NULL")
            connection.exec_driver_sql("UPDATE practice_records SET mastery_applied = 1 WHERE mastery_applied IS NULL")
        if "announcements" in existing_tables:
            connection.exec_driver_sql("UPDATE announcements SET content_html = content WHERE content_html IS NULL OR content_html = ''")
            connection.exec_driver_sql("UPDATE announcements SET summary = substr(content, 1, 160) WHERE summary IS NULL OR summary = ''")
            connection.exec_driver_sql("UPDATE announcements SET is_pinned = 0 WHERE is_pinned IS NULL")
            connection.exec_driver_sql("UPDATE announcements SET updated_at = created_at WHERE updated_at IS NULL")
