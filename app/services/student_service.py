from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.database import ClassroomEnrollmentORM, ClassroomORM, StudentMasteryORM, StudentProfileORM
from app.domain.models import (
    MasteryUpsertRequest,
    StudentDashboard,
    StudentProfileCreate,
    StudentProfileDetail,
    StudentProfileSummary,
    TopicMastery,
)
from app.repositories.sql_repository import sql_repository


class StudentService:
    def list_profiles(self, user_id: int) -> list[StudentProfileSummary]:
        with sql_repository.session() as session:
            profiles = session.execute(
                select(StudentProfileORM).where(StudentProfileORM.user_id == user_id)
            ).scalars().all()
            return [
                StudentProfileSummary(
                    id=item.id,
                    user_id=item.user_id,
                    school_id=item.school_id,
                    classroom_id=item.classroom_id,
                    teacher_user_id=item.teacher_user_id,
                    textbook_id=item.textbook_id,
                    name=item.name,
                    grade_level=item.grade_level,
                    target_subject=item.target_subject,
                    target_topic_id=item.target_topic_id,
                )
                for item in profiles
            ]

    def create_profile(self, user_id: int, request: StudentProfileCreate) -> StudentProfileSummary:
        with sql_repository.session() as session:
            textbook_id = request.textbook_id
            if request.classroom_id and textbook_id is None:
                classroom = session.execute(
                    select(ClassroomORM).where(ClassroomORM.id == request.classroom_id)
                ).scalars().first()
                if classroom:
                    textbook_id = classroom.textbook_id
            profile = StudentProfileORM(
                user_id=user_id,
                school_id=request.school_id,
                classroom_id=request.classroom_id,
                teacher_user_id=request.teacher_user_id,
                textbook_id=textbook_id,
                name=request.name,
                grade_level=request.grade_level,
                target_subject=request.target_subject,
                target_topic_id=request.target_topic_id,
            )
            session.add(profile)
            session.flush()
            if request.classroom_id:
                session.add(ClassroomEnrollmentORM(classroom_id=request.classroom_id, student_profile_id=profile.id))
            return StudentProfileSummary(
                id=profile.id,
                user_id=profile.user_id,
                school_id=profile.school_id,
                classroom_id=profile.classroom_id,
                teacher_user_id=profile.teacher_user_id,
                textbook_id=textbook_id,
                name=profile.name,
                grade_level=profile.grade_level,
                target_subject=profile.target_subject,
                target_topic_id=profile.target_topic_id,
            )

    def get_profile(self, student_profile_id: int, user_id: int | None = None) -> StudentProfileDetail:
        with sql_repository.session() as session:
            stmt = select(StudentProfileORM).where(StudentProfileORM.id == student_profile_id)
            if user_id is not None:
                stmt = stmt.where(StudentProfileORM.user_id == user_id)
            profile = session.execute(
                stmt
            ).scalars().first()
            if not profile:
                raise ValueError("student profile not found")
            mastery = self._load_mastery(session, student_profile_id)
            return StudentProfileDetail(
                id=profile.id,
                user_id=profile.user_id,
                school_id=profile.school_id,
                classroom_id=profile.classroom_id,
                teacher_user_id=profile.teacher_user_id,
                textbook_id=profile.textbook_id,
                name=profile.name,
                grade_level=profile.grade_level,
                target_subject=profile.target_subject,
                target_topic_id=profile.target_topic_id,
                mastery=mastery,
            )

    def save_mastery(
        self,
        student_profile_id: int,
        request: MasteryUpsertRequest,
        user_id: int | None = None,
    ) -> StudentProfileDetail:
        with sql_repository.session() as session:
            stmt = select(StudentProfileORM).where(StudentProfileORM.id == student_profile_id)
            if user_id is not None:
                stmt = stmt.where(StudentProfileORM.user_id == user_id)
            profile = session.execute(
                stmt
            ).scalars().first()
            if not profile:
                raise ValueError("student profile not found")

            existing_rows = {
                row.topic_id: row
                for row in session.execute(
                    select(StudentMasteryORM).where(StudentMasteryORM.student_profile_id == student_profile_id)
                ).scalars().all()
            }

            for topic_id, mastery in request.mastery.items():
                row = existing_rows.get(topic_id)
                if row is None:
                    row = StudentMasteryORM(student_profile_id=student_profile_id, topic_id=topic_id, mastery=0.0)
                    session.add(row)
                row.mastery = mastery.mastery
                row.practice_count = mastery.practice_count
                row.correct_count = mastery.correct_count
                row.last_practiced_at = mastery.last_practiced_at.isoformat() if mastery.last_practiced_at else None
                row.recent_errors = mastery.recent_errors

            session.flush()
            mastery_map = self._load_mastery(session, student_profile_id)
            return StudentProfileDetail(
                id=profile.id,
                user_id=profile.user_id,
                school_id=profile.school_id,
                classroom_id=profile.classroom_id,
                teacher_user_id=profile.teacher_user_id,
                textbook_id=profile.textbook_id,
                name=profile.name,
                grade_level=profile.grade_level,
                target_subject=profile.target_subject,
                target_topic_id=profile.target_topic_id,
                mastery=mastery_map,
            )

    def _load_mastery(self, session, student_profile_id: int) -> dict[str, TopicMastery]:
        rows = session.execute(
            select(StudentMasteryORM).where(StudentMasteryORM.student_profile_id == student_profile_id)
        ).scalars().all()
        mastery = {}
        for row in rows:
            mastery[row.topic_id] = TopicMastery(
                topic_id=row.topic_id,
                mastery=row.mastery,
                practice_count=row.practice_count,
                correct_count=row.correct_count,
                last_practiced_at=date.fromisoformat(row.last_practiced_at) if row.last_practiced_at else None,
                recent_errors=row.recent_errors or [],
            )
        return mastery
