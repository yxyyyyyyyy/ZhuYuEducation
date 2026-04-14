from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import (
    AnnouncementORM,
    ClassroomORM,
    QuestionBankORM,
    SchoolORM,
    StudentProfileORM,
    UserORM,
)
from app.domain.models import (
    AdminDashboard,
    AnnouncementCreate,
    AnnouncementView,
    SchoolView,
    TeacherCreateRequest,
    TeacherOption,
)
from app.repositories.sql_repository import sql_repository
from app.services.auth_service import AuthService


class AdminService:
    def __init__(self, auth_service: AuthService) -> None:
        self.auth_service = auth_service

    def dashboard(self, admin_user_id: int) -> AdminDashboard:
        with sql_repository.session() as session:
            admin, school = self._admin_and_school(session, admin_user_id)
            school_id = school.id
            teacher_count = session.scalar(select(func.count()).select_from(UserORM).where(UserORM.role == "teacher", UserORM.school_id == school_id)) or 0
            classroom_count = session.scalar(select(func.count()).select_from(ClassroomORM).where(ClassroomORM.school_id == school_id)) or 0
            student_count = session.scalar(select(func.count()).select_from(StudentProfileORM).where(StudentProfileORM.school_id == school_id)) or 0
            question_count = session.scalar(select(func.count()).select_from(QuestionBankORM)) or 0
            announcement_count = session.scalar(select(func.count()).select_from(AnnouncementORM).where(AnnouncementORM.school_id == school_id)) or 0
            return AdminDashboard(
                admin_name=admin.full_name,
                school=SchoolView(id=school.id, name=school.name, region=school.region or ""),
                teacher_count=teacher_count,
                classroom_count=classroom_count,
                student_count=student_count,
                question_count=question_count,
                announcement_count=announcement_count,
            )

    def list_teachers(self, admin_user_id: int) -> list[TeacherOption]:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            rows = session.execute(
                select(UserORM)
                .where(UserORM.role == "teacher", UserORM.school_id == school.id)
                .order_by(UserORM.full_name)
            ).scalars().all()
            return [TeacherOption(id=row.id, full_name=row.full_name, email=row.email, school_id=row.school_id) for row in rows]

    def create_teacher(self, admin_user_id: int, request: TeacherCreateRequest) -> TeacherOption:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            school_id = school.id
        auth = self.auth_service.create_user(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            role="teacher",
            school_id=school_id,
            issue_token=False,
        )
        return TeacherOption(id=auth.user.id, full_name=auth.user.full_name, email=auth.user.email, school_id=auth.user.school_id)

    def list_announcements(self, admin_user_id: int) -> list[AnnouncementView]:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            rows = session.execute(
                select(AnnouncementORM)
                .where(AnnouncementORM.school_id == school.id)
                .order_by(AnnouncementORM.created_at.desc())
            ).scalars().all()
            return [self._announcement_view(row) for row in rows]

    def create_announcement(self, admin_user_id: int, request: AnnouncementCreate) -> AnnouncementView:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            row = AnnouncementORM(school_id=school.id, title=request.title, content=request.content)
            session.add(row)
            session.flush()
            return self._announcement_view(row)

    def _admin_and_school(self, session, admin_user_id: int) -> tuple[UserORM, SchoolORM]:
        admin = session.execute(select(UserORM).where(UserORM.id == admin_user_id, UserORM.role == "admin")).scalars().first()
        if not admin:
            raise ValueError("admin user not found")
        school = session.execute(select(SchoolORM).where(SchoolORM.id == admin.school_id)).scalars().first()
        if not school:
            raise ValueError("admin school not found")
        return admin, school

    def _announcement_view(self, row: AnnouncementORM) -> AnnouncementView:
        return AnnouncementView(
            id=row.id,
            school_id=row.school_id,
            title=row.title,
            content=row.content,
            created_at=row.created_at,
        )
