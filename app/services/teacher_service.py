from __future__ import annotations

from collections import defaultdict
import secrets

from sqlalchemy import func, select

from app.core.database import (
    ClassroomEnrollmentORM,
    ClassroomORM,
    KnowledgeNodeORM,
    MistakeRecordORM,
    PracticeRecordORM,
    ReportRecordORM,
    SchoolORM,
    StudentMasteryORM,
    StudentProfileORM,
    TextbookORM,
    UserORM,
)
from app.domain.models import (
    ClassroomCreate,
    ClassroomView,
    SchoolCreate,
    SchoolView,
    TeacherDashboard,
    TeacherOption,
    TeacherStudentSubjectSummary,
    TeacherStudentSummary,
)
from app.repositories.sql_repository import sql_repository


class TeacherService:
    def student_ids_for_teacher(self, teacher_user_id: int) -> list[int]:
        with sql_repository.session() as session:
            rows = session.execute(
                select(StudentProfileORM.id).where(
                    (StudentProfileORM.teacher_user_id == teacher_user_id) | (StudentProfileORM.user_id == teacher_user_id)
                )
            ).scalars().all()
            return list(rows)

    def dashboard(self, teacher_user_id: int) -> TeacherDashboard:
        with sql_repository.session() as session:
            teacher = session.execute(select(UserORM).where(UserORM.id == teacher_user_id)).scalars().first()
            students = session.execute(
                select(StudentProfileORM).where(
                    (StudentProfileORM.teacher_user_id == teacher_user_id) | (StudentProfileORM.user_id == teacher_user_id)
                )
            ).scalars().all()
            student_ids = [item.id for item in students]

            classroom_ids = [item.classroom_id for item in students if item.classroom_id]
            classroom_map = {}
            if classroom_ids:
                classroom_rows = session.execute(
                    select(ClassroomORM).where(ClassroomORM.id.in_(set(classroom_ids)))
                ).scalars().all()
                classroom_map = {row.id: row.name for row in classroom_rows}

            mastery_rows = session.execute(
                select(StudentMasteryORM).where(StudentMasteryORM.student_profile_id.in_(student_ids))
            ).scalars().all() if student_ids else []
            practice_rows = session.execute(
                select(PracticeRecordORM).where(
                    PracticeRecordORM.student_profile_id.in_(student_ids),
                    PracticeRecordORM.evaluation_status != "pending_review",
                )
            ).scalars().all() if student_ids else []
            mistake_rows = session.execute(
                select(MistakeRecordORM).where(MistakeRecordORM.student_profile_id.in_(student_ids))
            ).scalars().all() if student_ids else []
            report_rows = session.execute(
                select(ReportRecordORM).where(ReportRecordORM.student_profile_id.in_(student_ids))
            ).scalars().all() if student_ids else []
            topic_meta, grade_subjects = self._knowledge_meta_for_school(session, teacher.school_id if teacher else None)

        mastery_map = defaultdict(list)
        for row in mastery_rows:
            mastery_map[row.student_profile_id].append(row.mastery)

        mastery_subject_map = defaultdict(lambda: defaultdict(list))
        for row in mastery_rows:
            subject = (topic_meta.get(row.topic_id, {}).get("subject") or "").strip()
            if subject:
                mastery_subject_map[row.student_profile_id][subject].append(row.mastery)

        practice_map = defaultdict(list)
        for row in practice_rows:
            practice_map[row.student_profile_id].append(row)

        practice_subject_map = defaultdict(lambda: defaultdict(list))
        for row in practice_rows:
            subject = (topic_meta.get(row.topic_id, {}).get("subject") or "").strip()
            if subject:
                practice_subject_map[row.student_profile_id][subject].append(row)

        mistake_count = defaultdict(int)
        for row in mistake_rows:
            mistake_count[row.student_profile_id] += 1

        latest_report = {}
        for row in sorted(report_rows, key=lambda item: item.created_at, reverse=True):
            latest_report.setdefault(row.student_profile_id, row.created_at)

        summaries = []
        for student in students:
            mastery_values = mastery_map.get(student.id, [])
            student_practice = practice_map.get(student.id, [])
            accuracy = (
                sum(1 for item in student_practice if item.is_correct) / len(student_practice)
                if student_practice
                else 0.0
            )
            raw_subject = student.target_subject or ""
            resolved_subject = (topic_meta.get(student.target_topic_id, {}).get("subject") or raw_subject).strip()
            student_subjects = list(grade_subjects.get(student.grade_level, []))
            for subject in mastery_subject_map.get(student.id, {}):
                if subject and subject not in student_subjects:
                    student_subjects.append(subject)
            for subject in practice_subject_map.get(student.id, {}):
                if subject and subject not in student_subjects:
                    student_subjects.append(subject)
            if resolved_subject and resolved_subject not in student_subjects:
                student_subjects.append(resolved_subject)
            subject_summaries = []
            for subject in student_subjects:
                subject_mastery = mastery_subject_map.get(student.id, {}).get(subject, [])
                subject_practice = practice_subject_map.get(student.id, {}).get(subject, [])
                subject_accuracy = (
                    sum(1 for item in subject_practice if item.is_correct) / len(subject_practice)
                    if subject_practice
                    else None
                )
                subject_summaries.append(
                    TeacherStudentSubjectSummary(
                        subject=subject,
                        mastery=round(sum(subject_mastery) / len(subject_mastery), 2) if subject_mastery else None,
                        accuracy=round(subject_accuracy, 2) if subject_accuracy is not None else None,
                        practice_count=len(subject_practice),
                    )
                )
            summaries.append(
                TeacherStudentSummary(
                    student_profile_id=student.id,
                    name=student.name,
                    grade_level=student.grade_level,
                    classroom_name=classroom_map.get(student.classroom_id, "") if student.classroom_id else "未分班",
                    target_subject=resolved_subject,
                    target_topic_id=student.target_topic_id,
                    overall_mastery=round(sum(mastery_values) / len(mastery_values), 2) if mastery_values else 0.0,
                    latest_report_at=latest_report.get(student.id),
                    recent_mistake_count=mistake_count.get(student.id, 0),
                    recent_practice_accuracy=round(accuracy, 2),
                    subject_summaries=subject_summaries,
                )
            )

        avg_mastery = (
            round(sum(item.overall_mastery for item in summaries) / len(summaries), 2)
            if summaries
            else 0.0
        )
        avg_accuracy = (
            round(sum(item.recent_practice_accuracy for item in summaries) / len(summaries), 2)
            if summaries
            else 0.0
        )
        active_students = sum(1 for item in summaries if item.recent_practice_accuracy > 0 or item.recent_mistake_count > 0)
        return TeacherDashboard(
            teacher_name=teacher.full_name if teacher else "教师",
            total_students=len(summaries),
            active_students=active_students,
            average_mastery=avg_mastery,
            average_accuracy=avg_accuracy,
            students=summaries,
        )

    def _knowledge_meta_for_school(self, session, school_id: int | None) -> tuple[dict[str, dict], dict[str, list[str]]]:
        stmt = select(KnowledgeNodeORM).where(KnowledgeNodeORM.is_deleted == 0)
        if school_id is not None:
            stmt = stmt.where(KnowledgeNodeORM.school_id == school_id)
        rows = session.execute(
            stmt.order_by(KnowledgeNodeORM.grade_level.asc(), KnowledgeNodeORM.subject.asc(), KnowledgeNodeORM.sort_order.asc())
        ).scalars().all()
        topic_meta: dict[str, dict] = {}
        grade_subjects = defaultdict(set)
        for row in rows:
            meta = {
                "name": row.name,
                "subject": row.subject or "",
                "grade_level": row.grade_level or "",
                "parent_id": row.parent_node_key or "",
                "level": row.level,
            }
            topic_meta[row.node_key] = meta
            if row.topic_ref_id:
                topic_meta[row.topic_ref_id] = meta
            if row.subject and row.grade_level:
                grade_subjects[row.grade_level].add(row.subject)
        ordered_grade_subjects = {
            grade: sorted(subjects, key=lambda item: item)
            for grade, subjects in grade_subjects.items()
        }
        return topic_meta, ordered_grade_subjects

    def list_schools(self, school_id: int | None = None) -> list[SchoolView]:
        with sql_repository.session() as session:
            stmt = select(SchoolORM)
            if school_id is not None:
                stmt = stmt.where(SchoolORM.id == school_id)
            rows = session.execute(stmt.order_by(SchoolORM.name)).scalars().all()
            return [SchoolView(id=row.id, name=row.name, region=row.region or "") for row in rows]

    def create_school(self, request: SchoolCreate) -> SchoolView:
        with sql_repository.session() as session:
            existing = session.execute(select(SchoolORM).where(SchoolORM.name == request.name)).scalars().first()
            if existing:
                return SchoolView(id=existing.id, name=existing.name, region=existing.region or "")
            row = SchoolORM(name=request.name, region=request.region)
            session.add(row)
            session.flush()
            return SchoolView(id=row.id, name=row.name, region=row.region or "")

    def get_or_create_school(self, name: str, region: str = "") -> SchoolView:
        return self.create_school(SchoolCreate(name=name, region=region))

    def list_teachers(self) -> list[TeacherOption]:
        with sql_repository.session() as session:
            rows = session.execute(select(UserORM).where(UserORM.role == "teacher").order_by(UserORM.full_name)).scalars().all()
            return [TeacherOption(id=row.id, full_name=row.full_name, email=row.email, school_id=row.school_id) for row in rows]

    def list_classrooms(self, teacher_user_id: int | None = None, school_id: int | None = None) -> list[ClassroomView]:
        with sql_repository.session() as session:
            stmt = select(ClassroomORM)
            if teacher_user_id is not None:
                stmt = stmt.where(ClassroomORM.teacher_user_id == teacher_user_id)
            if school_id is not None:
                stmt = stmt.where(ClassroomORM.school_id == school_id)
            rows = session.execute(stmt.order_by(ClassroomORM.grade_level, ClassroomORM.name)).scalars().all()
            school_ids = [row.school_id for row in rows if row.school_id]
            teacher_ids = [row.teacher_user_id for row in rows]
            schools = {
                row.id: row
                for row in session.execute(select(SchoolORM).where(SchoolORM.id.in_(school_ids))).scalars().all()
            } if school_ids else {}
            teachers = {
                row.id: row
                for row in session.execute(select(UserORM).where(UserORM.id.in_(teacher_ids))).scalars().all()
            } if teacher_ids else {}
            counts = defaultdict(int)
            if rows:
                classroom_ids = [row.id for row in rows]
                enrollments = session.execute(
                    select(ClassroomEnrollmentORM.classroom_id).where(ClassroomEnrollmentORM.classroom_id.in_(classroom_ids))
                ).scalars().all()
                for classroom_id in enrollments:
                    counts[classroom_id] += 1
            return [
                ClassroomView(
                    id=row.id,
                    school_id=row.school_id,
                    school_name=schools[row.school_id].name if row.school_id in schools else "",
                    teacher_user_id=row.teacher_user_id,
                    teacher_name=teachers[row.teacher_user_id].full_name if row.teacher_user_id in teachers else "",
                    textbook_id=row.textbook_id,
                    name=row.name,
                    grade_level=row.grade_level or "",
                    invite_code=row.invite_code or "",
                    description=row.description or "",
                    student_count=counts.get(row.id, 0),
                )
                for row in rows
            ]

    def create_classroom(self, teacher_user_id: int, request: ClassroomCreate) -> ClassroomView:
        with sql_repository.session() as session:
            teacher = session.execute(select(UserORM).where(UserORM.id == teacher_user_id)).scalars().first()
            if not teacher:
                raise ValueError("teacher not found")
            school_id = request.school_id or teacher.school_id
            if not school_id:
                raise ValueError("teacher school not found")
            if teacher.school_id and school_id != teacher.school_id:
                raise ValueError("school is outside current teacher")
            textbook_id = request.textbook_id
            if textbook_id is None:
                stmt = select(TextbookORM).where(TextbookORM.school_id == school_id)
                if request.grade_level:
                    grade_rows = session.execute(
                        stmt.where(TextbookORM.grade_level == request.grade_level).order_by(TextbookORM.id.asc())
                    ).scalars().all()
                    if grade_rows:
                        textbook_row = next((item for item in grade_rows if (item.subject or "") == "数学"), grade_rows[0])
                    else:
                        textbook_row = session.execute(
                            stmt.order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
                        ).scalars().first()
                else:
                    textbook_row = session.execute(
                        stmt.order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
                    ).scalars().first()
                textbook_id = textbook_row.id if textbook_row else None
            row = ClassroomORM(
                school_id=school_id,
                teacher_user_id=teacher_user_id,
                textbook_id=textbook_id,
                name=request.name,
                grade_level=request.grade_level,
                description=request.description,
                invite_code=self._new_invite_code(session),
            )
            session.add(row)
            session.flush()
            row_id = row.id
        return next(item for item in self.list_classrooms(teacher_user_id=teacher_user_id) if item.id == row_id)

    def find_classroom_by_invite_code(self, invite_code: str) -> ClassroomView:
        normalized = invite_code.strip().upper()
        classroom_id = None
        school_id = None
        with sql_repository.session() as session:
            row = session.execute(select(ClassroomORM).where(ClassroomORM.invite_code == normalized)).scalars().first()
            if not row:
                raise ValueError("invalid invite code")
            classroom_id = row.id
            school_id = row.school_id
        return next(item for item in self.list_classrooms(school_id=school_id) if item.id == classroom_id)

    def refresh_invite_code(self, teacher_user_id: int, classroom_id: int) -> ClassroomView:
        with sql_repository.session() as session:
            row = session.execute(
                select(ClassroomORM).where(
                    ClassroomORM.id == classroom_id,
                    ClassroomORM.teacher_user_id == teacher_user_id,
                )
            ).scalars().first()
            if not row:
                raise ValueError("classroom not found")
            row.invite_code = self._new_invite_code(session)
            row_id = row.id
        return next(item for item in self.list_classrooms(teacher_user_id=teacher_user_id) if item.id == row_id)

    def _new_invite_code(self, session) -> str:
        while True:
            code = f"ZYU-{secrets.token_hex(3).upper()}"
            exists = session.execute(select(ClassroomORM).where(ClassroomORM.invite_code == code)).scalars().first()
            if not exists:
                return code
