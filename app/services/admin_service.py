from __future__ import annotations

from collections import defaultdict
import csv
import io
import math
import re
import secrets
import string
from datetime import datetime

from sqlalchemy import func, or_, select

from app.core.database import (
    AnnouncementDraftORM,
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
    AnnouncementDraftView,
    AnnouncementView,
    SchoolView,
    TeacherCreateRequest,
    TeacherImportResponse,
    TeacherImportResult,
    TeacherManageItem,
    TeacherOption,
    Topic,
)
from app.repositories.sql_repository import sql_repository
from app.services.auth_service import AuthService
from app.services.knowledge_config_service import KnowledgeConfigService


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminService:
    def __init__(self, auth_service: AuthService, knowledge_config_service: KnowledgeConfigService) -> None:
        self.auth_service = auth_service
        self.knowledge_config_service = knowledge_config_service

    def dashboard(self, admin_user_id: int) -> AdminDashboard:
        with sql_repository.session() as session:
            admin, school = self._admin_and_school(session, admin_user_id)
            school_id = school.id
            teacher_count = session.scalar(
                select(func.count()).select_from(UserORM).where(UserORM.role == "teacher", UserORM.school_id == school_id)
            ) or 0
            classroom_count = session.scalar(
                select(func.count()).select_from(ClassroomORM).where(ClassroomORM.school_id == school_id)
            ) or 0
            student_count = session.scalar(
                select(func.count()).select_from(StudentProfileORM).where(StudentProfileORM.school_id == school_id)
            ) or 0
            question_count = session.scalar(select(func.count()).select_from(QuestionBankORM)) or 0
            announcement_count = session.scalar(
                select(func.count()).select_from(AnnouncementORM).where(AnnouncementORM.school_id == school_id)
            ) or 0
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
        payload = self.list_teachers_manage(admin_user_id, page=1, page_size=2000)
        return [
            TeacherOption(
                id=item.id,
                full_name=item.full_name,
                email=item.email,
                school_id=item.school_id,
                classroom_count=item.classroom_count,
                student_count=item.student_count,
            )
            for item in payload["items"]
        ]

    def list_teachers_manage(
        self,
        admin_user_id: int,
        q: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), 100)
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            stmt = select(UserORM).where(UserORM.role == "teacher", UserORM.school_id == school.id)
            keyword = (q or "").strip()
            if keyword:
                stmt = stmt.where(or_(UserORM.full_name.like(f"%{keyword}%"), UserORM.email.like(f"%{keyword}%")))
            total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            rows = session.execute(
                stmt.order_by(UserORM.created_at.desc()).offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
            ).scalars().all()
            teacher_ids = [row.id for row in rows]
            class_counts: dict[int, int] = {}
            student_counts: dict[int, int] = {}
            if teacher_ids:
                for teacher_id, count in session.execute(
                    select(ClassroomORM.teacher_user_id, func.count())
                    .where(ClassroomORM.teacher_user_id.in_(teacher_ids))
                    .group_by(ClassroomORM.teacher_user_id)
                ).all():
                    class_counts[int(teacher_id)] = int(count)
                for teacher_id, count in session.execute(
                    select(StudentProfileORM.teacher_user_id, func.count())
                    .where(StudentProfileORM.teacher_user_id.in_(teacher_ids))
                    .group_by(StudentProfileORM.teacher_user_id)
                ).all():
                    if teacher_id is None:
                        continue
                    student_counts[int(teacher_id)] = int(count)
            items = [
                TeacherManageItem(
                    id=row.id,
                    full_name=row.full_name,
                    email=row.email,
                    school_id=row.school_id,
                    classroom_count=class_counts.get(row.id, 0),
                    student_count=student_counts.get(row.id, 0),
                    created_at=row.created_at,
                )
                for row in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": math.ceil(total / safe_page_size) if total else 1,
            }

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
        return TeacherOption(
            id=auth.user.id,
            full_name=auth.user.full_name,
            email=auth.user.email,
            school_id=auth.user.school_id,
            classroom_count=0,
            student_count=0,
        )

    def import_teachers_by_csv(self, admin_user_id: int, csv_content: str) -> TeacherImportResponse:
        if not (csv_content or "").strip():
            raise ValueError("CSV 内容为空")
        rows = csv.DictReader(io.StringIO(csv_content.strip()))
        imported_count = 0
        skipped_count = 0
        results: list[TeacherImportResult] = []
        for index, row in enumerate(rows, start=2):
            full_name = (row.get("姓名") or row.get("name") or row.get("full_name") or "").strip()
            email = (row.get("邮箱") or row.get("email") or "").strip()
            password = (row.get("初始密码") or row.get("password") or "").strip()
            if not full_name or not email or not password:
                skipped_count += 1
                results.append(
                    TeacherImportResult(row_index=index, full_name=full_name, email=email, imported=False, reason="字段不完整")
                )
                continue
            if not EMAIL_PATTERN.match(email):
                skipped_count += 1
                results.append(TeacherImportResult(row_index=index, full_name=full_name, email=email, imported=False, reason="邮箱格式错误"))
                continue
            if len(password) < 8:
                skipped_count += 1
                results.append(TeacherImportResult(row_index=index, full_name=full_name, email=email, imported=False, reason="密码长度不足 8 位"))
                continue
            try:
                teacher = self.create_teacher(
                    admin_user_id,
                    TeacherCreateRequest(full_name=full_name, email=email, password=password),
                )
                imported_count += 1
                results.append(
                    TeacherImportResult(
                        row_index=index,
                        full_name=full_name,
                        email=email,
                        imported=True,
                        teacher_id=teacher.id,
                    )
                )
            except ValueError as exc:
                skipped_count += 1
                results.append(
                    TeacherImportResult(
                        row_index=index,
                        full_name=full_name,
                        email=email,
                        imported=False,
                        reason=str(exc),
                    )
                )
        return TeacherImportResponse(imported_count=imported_count, skipped_count=skipped_count, rows=results)

    def reset_teacher_password(self, admin_user_id: int, teacher_id: int) -> dict:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            teacher = session.execute(
                select(UserORM).where(
                    UserORM.id == teacher_id,
                    UserORM.role == "teacher",
                    UserORM.school_id == school.id,
                )
            ).scalars().first()
            if not teacher:
                raise ValueError("教师不存在")
            new_password = self._random_password()
            self.auth_service.set_password(teacher_id, new_password)
            return {
                "teacher_id": teacher.id,
                "full_name": teacher.full_name,
                "email": teacher.email,
                "new_password": new_password,
            }

    def delete_teacher(self, admin_user_id: int, teacher_id: int) -> None:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            teacher = session.execute(
                select(UserORM).where(
                    UserORM.id == teacher_id,
                    UserORM.role == "teacher",
                    UserORM.school_id == school.id,
                )
            ).scalars().first()
            if not teacher:
                raise ValueError("教师不存在")
            classroom_count = session.scalar(
                select(func.count()).select_from(ClassroomORM).where(ClassroomORM.teacher_user_id == teacher_id)
            ) or 0
            student_count = session.scalar(
                select(func.count()).select_from(StudentProfileORM).where(StudentProfileORM.teacher_user_id == teacher_id)
            ) or 0
            if classroom_count > 0 or student_count > 0:
                raise ValueError("该教师下仍有班级或学生，暂不允许删除")
            session.delete(teacher)

    def list_announcements(self, admin_user_id: int) -> list[AnnouncementView]:
        payload = self.list_announcements_manage(admin_user_id, page=1, page_size=100)
        return payload["items"]

    def list_announcements_manage(
        self,
        admin_user_id: int,
        q: str = "",
        page: int = 1,
        page_size: int = 12,
    ) -> dict:
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), 60)
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            stmt = select(AnnouncementORM).where(AnnouncementORM.school_id == school.id)
            keyword = (q or "").strip()
            if keyword:
                stmt = stmt.where(
                    or_(AnnouncementORM.title.like(f"%{keyword}%"), AnnouncementORM.content.like(f"%{keyword}%"))
                )
            total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            rows = session.execute(
                stmt.order_by(AnnouncementORM.is_pinned.desc(), AnnouncementORM.created_at.desc())
                .offset((safe_page - 1) * safe_page_size)
                .limit(safe_page_size)
            ).scalars().all()
            items = [self._announcement_view(row) for row in rows]
            return {
                "items": items,
                "total": total,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": math.ceil(total / safe_page_size) if total else 1,
            }

    def create_announcement(self, admin_user_id: int, request: AnnouncementCreate) -> AnnouncementView:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            row = AnnouncementORM(
                school_id=school.id,
                title=request.title.strip(),
                content=self._plain_text(request.content or request.content_html),
                content_html=(request.content_html or request.content).strip(),
                summary=self._summary_text(request.content or request.content_html),
                is_pinned=1 if request.is_pinned else 0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            return self._announcement_view(row)

    def update_announcement(self, admin_user_id: int, announcement_id: int, request: AnnouncementCreate) -> AnnouncementView:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            row = session.execute(
                select(AnnouncementORM).where(AnnouncementORM.id == announcement_id, AnnouncementORM.school_id == school.id)
            ).scalars().first()
            if not row:
                raise ValueError("公告不存在")
            row.title = request.title.strip()
            row.content = self._plain_text(request.content or request.content_html)
            row.content_html = (request.content_html or request.content).strip()
            row.summary = self._summary_text(request.content or request.content_html)
            row.is_pinned = 1 if request.is_pinned else 0
            row.updated_at = datetime.utcnow()
            session.flush()
            return self._announcement_view(row)

    def delete_announcement(self, admin_user_id: int, announcement_id: int) -> None:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            row = session.execute(
                select(AnnouncementORM).where(AnnouncementORM.id == announcement_id, AnnouncementORM.school_id == school.id)
            ).scalars().first()
            if not row:
                raise ValueError("公告不存在")
            session.delete(row)

    def get_announcement(self, admin_user_id: int, announcement_id: int) -> AnnouncementView:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            row = session.execute(
                select(AnnouncementORM).where(AnnouncementORM.id == announcement_id, AnnouncementORM.school_id == school.id)
            ).scalars().first()
            if not row:
                raise ValueError("公告不存在")
            return self._announcement_view(row)

    def save_announcement_draft(self, admin_user_id: int, title: str, content_html: str) -> AnnouncementDraftView:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            row = session.execute(
                select(AnnouncementDraftORM).where(AnnouncementDraftORM.admin_user_id == admin_user_id)
            ).scalars().first()
            if not row:
                row = AnnouncementDraftORM(
                    admin_user_id=admin_user_id,
                    school_id=school.id,
                    title=(title or "").strip(),
                    content_html=(content_html or "").strip(),
                    updated_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
            else:
                row.title = (title or "").strip()
                row.content_html = (content_html or "").strip()
                row.updated_at = datetime.utcnow()
                session.flush()
            return AnnouncementDraftView(id=row.id, title=row.title, content_html=row.content_html, updated_at=row.updated_at)

    def get_announcement_draft(self, admin_user_id: int) -> AnnouncementDraftView | None:
        with sql_repository.session() as session:
            row = session.execute(
                select(AnnouncementDraftORM).where(AnnouncementDraftORM.admin_user_id == admin_user_id)
            ).scalars().first()
            if not row:
                return None
            return AnnouncementDraftView(id=row.id, title=row.title, content_html=row.content_html, updated_at=row.updated_at)

    def list_question_bank_manage(
        self,
        admin_user_id: int,
        q: str = "",
        knowledge_l1_id: str = "",
        knowledge_l2_id: str = "",
        topic_id: str = "",
        subject: str = "",
        grade_level: str = "",
        status: str = "",
        question_type: str = "",
        difficulty_level_min: int | None = None,
        difficulty_level_max: int | None = None,
        page: int = 1,
        page_size: int = 20,
        textbook_id: int | None = None,
    ) -> dict:
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), 100)
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
            all_textbooks = self.knowledge_config_service.list_textbooks(school.id)
            topic_meta: dict[str, dict] = {}
            if textbook_id:
                topic_meta = self._topic_meta_for_school(school.id, textbook_id)
            else:
                for tb in all_textbooks:
                    extra_meta = self._topic_meta_for_school(school.id, tb.id)
                    for key, value in extra_meta.items():
                        if key not in topic_meta:
                            topic_meta[key] = value
            query = select(QuestionBankORM)
            keyword = (q or "").strip()
            if keyword:
                query = query.where(
                    or_(
                        QuestionBankORM.stem.like(f"%{keyword}%"),
                        QuestionBankORM.answer.like(f"%{keyword}%"),
                        QuestionBankORM.explanation.like(f"%{keyword}%"),
                    )
                )
            effective_l2_filter = (knowledge_l2_id or topic_id or "").strip()
            if effective_l2_filter:
                query = query.where(
                    (QuestionBankORM.knowledge_l2_id == effective_l2_filter) | (QuestionBankORM.topic_id == effective_l2_filter)
                )
            if knowledge_l1_id:
                query = query.where(QuestionBankORM.knowledge_l1_id == knowledge_l1_id)
            if status:
                query = query.where(QuestionBankORM.status == status)
            if question_type:
                query = query.where(QuestionBankORM.question_type == question_type)
            if difficulty_level_min is not None:
                query = query.where(QuestionBankORM.difficulty_level >= difficulty_level_min)
            if difficulty_level_max is not None:
                query = query.where(QuestionBankORM.difficulty_level <= difficulty_level_max)
            rows = session.execute(query.order_by(QuestionBankORM.created_at.desc())).scalars().all()

            filtered = []
            for row in rows:
                resolved_l2_id = row.knowledge_l2_id or row.topic_id
                meta = topic_meta.get(resolved_l2_id) or {}
                if textbook_id and not meta:
                    continue
                if subject and meta.get("subject") != subject:
                    continue
                if grade_level and meta.get("grade_level") != grade_level:
                    continue
                filtered.append((row, meta, resolved_l2_id))

            total = len(filtered)
            begin = (safe_page - 1) * safe_page_size
            end = begin + safe_page_size
            page_rows = filtered[begin:end]
            items = [
                {
                    "id": row.id,
                    "external_id": row.external_id,
                    "knowledge_l1_id": row.knowledge_l1_id or meta.get("l1_id") or "",
                    "knowledge_l1_name": meta.get("l1_name") or "",
                    "knowledge_l2_id": resolved_l2_id,
                    "knowledge_l2_name": meta.get("topic_name") or resolved_l2_id,
                    "topic_id": resolved_l2_id,
                    "subject": meta.get("subject") or "未分类",
                    "grade_level": meta.get("grade_level") or "未分层",
                    "topic_name": meta.get("topic_name") or resolved_l2_id,
                    "stem": row.stem,
                    "answer": row.answer,
                    "explanation": row.explanation,
                    "difficulty_level": int(row.difficulty_level or self._difficulty_level_from_float(row.difficulty)),
                    "difficulty": row.difficulty,
                    "knowledge_tiers": row.knowledge_tiers or ["基础知识点"],
                    "question_type": row.question_type,
                    "status": row.status,
                    "source": row.source,
                    "tags": row.tags or [],
                    "created_at": row.created_at,
                }
                for row, meta, resolved_l2_id in page_rows
            ]
            approved_count = sum(1 for row, _, _ in filtered if row.status == "approved")
            pending_count = sum(1 for row, _, _ in filtered if row.status == "pending")
            categories = []
            if textbook_id:
                categories = self.knowledge_config_service.list_tree(school.id, textbook_id)
            else:
                categories = self._subject_grade_categories(
                    all_textbooks,
                    filtered,
                    subject_filter=subject,
                    grade_filter=grade_level,
                )
            return {
                "items": items,
                "total": total,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": math.ceil(total / safe_page_size) if total else 1,
                "stats": {
                    "total": total,
                    "approved": approved_count,
                    "pending": pending_count,
                    "rejected": max(total - approved_count - pending_count, 0),
                },
                "categories": categories,
            }

    def update_question_bank_status(self, question_ids: list[int], action: str) -> int:
        if not question_ids:
            return 0
        with sql_repository.session() as session:
            rows = session.execute(
                select(QuestionBankORM).where(QuestionBankORM.id.in_(question_ids))
            ).scalars().all()
            if action == "delete":
                for row in rows:
                    session.delete(row)
                return len(rows)
            if action not in {"approve", "reject"}:
                raise ValueError("不支持的批量操作")
            target_status = "approved" if action == "approve" else "pending"
            for row in rows:
                row.status = target_status
            return len(rows)

    def export_question_bank(
        self,
        admin_user_id: int,
        filters: dict,
    ) -> str:
        payload = self.list_question_bank_manage(
            admin_user_id=admin_user_id,
            q=filters.get("q", ""),
            knowledge_l1_id=filters.get("knowledge_l1_id", ""),
            knowledge_l2_id=filters.get("knowledge_l2_id", ""),
            topic_id=filters.get("topic_id", ""),
            subject=filters.get("subject", ""),
            grade_level=filters.get("grade_level", ""),
            status=filters.get("status", ""),
            question_type=filters.get("question_type", ""),
            difficulty_level_min=filters.get("difficulty_level_min"),
            difficulty_level_max=filters.get("difficulty_level_max"),
            page=1,
            page_size=100000,
            textbook_id=filters.get("textbook_id"),
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "年级",
                "学科",
                "一级知识点ID",
                "一级知识点",
                "二级知识点ID",
                "二级知识点",
                "题目ID",
                "题目",
                "答案",
                "难度级别",
                "知识点层级标签",
                "状态",
                "题型",
                "来源",
            ]
        )
        for item in sorted(payload["items"], key=lambda row: (row["subject"], row["grade_level"], row["topic_name"], row["external_id"])):
            writer.writerow(
                [
                    item["grade_level"],
                    item["subject"],
                    item.get("knowledge_l1_id", ""),
                    item.get("knowledge_l1_name", ""),
                    item.get("knowledge_l2_id", ""),
                    item.get("knowledge_l2_name", ""),
                    item["external_id"],
                    item["stem"],
                    item["answer"],
                    item.get("difficulty_level", 3),
                    "、".join(item.get("knowledge_tiers", [])),
                    item["status"],
                    item["question_type"],
                    item["source"],
                ]
            )
        return output.getvalue()

    def list_textbooks(self, admin_user_id: int) -> list:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.list_textbooks(school.id)

    def create_textbook(
        self,
        admin_user_id: int,
        name: str,
        grade_level: str,
        subject: str,
        set_default: bool = False,
    ):
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.create_textbook(
            school.id,
            name,
            grade_level=grade_level,
            subject=subject,
            set_default=set_default,
        )

    def list_knowledge_tree(self, admin_user_id: int, textbook_id: int | None = None):
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.list_tree(school.id, textbook_id)

    def create_knowledge_node(self, admin_user_id: int, textbook_id: int, payload: dict):
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.create_node(
            school_id=school.id,
            textbook_id=textbook_id,
            name=payload.get("name", ""),
            level=int(payload.get("level", 2) or 2),
            parent_node_key=payload.get("parent_node_key"),
            subject=payload.get("subject", ""),
            grade_level=payload.get("grade_level", ""),
        )

    def update_knowledge_node(self, admin_user_id: int, textbook_id: int, node_key: str, payload: dict):
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.update_node(
            school_id=school.id,
            textbook_id=textbook_id,
            node_key=node_key,
            name=payload.get("name"),
        )

    def delete_knowledge_node(self, admin_user_id: int, textbook_id: int, node_key: str) -> int:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.delete_node(school.id, textbook_id, node_key)

    def batch_delete_knowledge_nodes(self, admin_user_id: int, textbook_id: int, node_keys: list[str]) -> int:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.batch_delete_nodes(school.id, textbook_id, node_keys)

    def reorder_knowledge_nodes(
        self,
        admin_user_id: int,
        textbook_id: int,
        parent_node_key: str | None,
        ordered_node_keys: list[str],
    ) -> int:
        with sql_repository.session() as session:
            _, school = self._admin_and_school(session, admin_user_id)
        return self.knowledge_config_service.reorder_siblings(
            school_id=school.id,
            textbook_id=textbook_id,
            parent_node_key=parent_node_key,
            ordered_node_keys=ordered_node_keys,
        )

    def topic_ref_options(self) -> list[Topic]:
        return self.knowledge_config_service.topic_ref_options()

    def _admin_and_school(self, session, admin_user_id: int) -> tuple[UserORM, SchoolORM]:
        admin = session.execute(
            select(UserORM).where(UserORM.id == admin_user_id, UserORM.role == "admin")
        ).scalars().first()
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
            content_html=row.content_html or row.content,
            summary=row.summary or self._summary_text(row.content),
            is_pinned=bool(row.is_pinned),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _summary_text(self, content: str, limit: int = 120) -> str:
        plain = self._plain_text(content)
        return plain[:limit]

    def _plain_text(self, content: str) -> str:
        if not content:
            return ""
        text = re.sub(r"<[^>]+>", "", content)
        return re.sub(r"\s+", " ", text).strip()

    def _random_password(self, length: int = 10) -> str:
        charset = string.ascii_letters + string.digits
        return "".join(secrets.choice(charset) for _ in range(length))

    def _topic_meta_for_school(self, school_id: int, textbook_id: int) -> dict[str, dict]:
        topic_meta = {}
        topics = self.knowledge_config_service.list_topics_for_school(school_id, textbook_id)
        topic_by_id = {item.id: item for item in topics}
        for topic in topics:
            if topic.level != 2:
                continue
            parent_id = topic.parent_id or ""
            parent = topic_by_id.get(parent_id)
            topic_meta[topic.id] = {
                "subject": topic.subject,
                "grade_level": topic.grade_level,
                "topic_name": topic.name,
                "parent_id": parent_id,
                "l1_id": parent_id,
                "l1_name": parent.name if parent else "",
            }
        return topic_meta

    def _subject_grade_categories(
        self,
        textbooks: list,
        filtered_rows: list[tuple],
        subject_filter: str = "",
        grade_filter: str = "",
    ) -> list[dict]:
        subject_totals: dict[str, int] = defaultdict(int)
        grade_totals: dict[tuple[str, str], int] = defaultdict(int)
        for _, meta, _ in filtered_rows:
            subject = (meta.get("subject") or "未分类").strip() or "未分类"
            grade = (meta.get("grade_level") or "未分层").strip() or "未分层"
            subject_totals[subject] += 1
            grade_totals[(subject, grade)] += 1

        normalized_subject = (subject_filter or "").strip()
        normalized_grade = (grade_filter or "").strip()
        visible_textbooks = [
            item
            for item in textbooks
            if (not normalized_subject or (item.subject or "").strip() == normalized_subject)
            and (not normalized_grade or (item.grade_level or "").strip() == normalized_grade)
        ]
        textbook_subjects = {(item.subject or "").strip() for item in visible_textbooks if (item.subject or "").strip()}
        if normalized_subject:
            textbook_subjects.add(normalized_subject)
        subjects = sorted(textbook_subjects | set(subject_totals.keys()))
        categories: list[dict] = []
        for subject in subjects:
            textbook_grades = {
                (item.grade_level or "").strip()
                for item in visible_textbooks
                if (item.subject or "").strip() == subject and (item.grade_level or "").strip()
            }
            grades_from_questions = {grade for (subj, grade), count in grade_totals.items() if subj == subject and count > 0}
            if normalized_grade:
                textbook_grades.add(normalized_grade)
            grades = sorted(textbook_grades | grades_from_questions)
            grade_children = [
                {
                    "id": f"grade::{subject}::{grade}",
                    "node_key": f"grade::{subject}::{grade}",
                    "name": grade,
                    "subject": subject,
                    "grade_level": grade,
                    "question_count": int(grade_totals.get((subject, grade), 0)),
                    "children": [],
                }
                for grade in grades
            ]
            categories.append(
                {
                    "id": f"subject::{subject}",
                    "node_key": f"subject::{subject}",
                    "name": subject,
                    "subject": subject,
                    "grade_level": "",
                    "question_count": int(subject_totals.get(subject, 0)),
                    "children": grade_children,
                }
            )
        return categories

    def _difficulty_level_from_float(self, difficulty: float | None) -> int:
        if difficulty is None:
            return 3
        value = float(difficulty)
        if value < 0.2:
            return 1
        if value < 0.4:
            return 2
        if value < 0.6:
            return 3
        if value < 0.8:
            return 4
        return 5
