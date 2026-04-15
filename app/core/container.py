from __future__ import annotations

from pathlib import Path
import os

from sqlalchemy import select

from app.core.database import (
    AnnouncementORM,
    ClassroomEnrollmentORM,
    ClassroomORM,
    KnowledgeDocumentORM,
    QuestionBankORM,
    RagDocumentORM,
    SchoolORM,
    StudentMasteryORM,
    StudentProfileORM,
    TextbookORM,
    UserORM,
    init_database,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.sql_repository import sql_repository
from app.services.auth_service import AuthService
from app.services.admin_service import AdminService
from app.services.chat_service import ChatService
from app.services.dashscope_service import DashScopeEmbeddingService
from app.services.diagnosis_service import DiagnosisService
from app.services.document_service import DocumentService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.knowledge_config_service import KnowledgeConfigService
from app.services.llm_service import LLMService
from app.services.mistake_service import MistakeService
from app.services.practice_service import PracticeService
from app.services.question_bank_service import QuestionBankService
from app.services.retrieval_service import HybridRetrievalService
from app.services.rag_service import RagService
from app.services.report_service import ReportService
from app.services.student_service import StudentService
from app.services.teacher_service import TeacherService
from app.services.tutor_service import TutorService


def dump_model(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class ServiceContainer:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        repository = KnowledgeRepository(root / "data" / "knowledge_graph.json")
        graph_service = KnowledgeGraphService(repository)
        dashscope_service = DashScopeEmbeddingService()
        retrieval_service = HybridRetrievalService()
        rag_service = RagService(retrieval_service, dashscope_service)
        llm_service = LLMService()

        self.repository = repository
        self.graph_service = graph_service
        self.dashscope_service = dashscope_service
        self.retrieval_service = retrieval_service
        self.auth_service = AuthService()
        self.knowledge_config_service = KnowledgeConfigService(repository)
        self.admin_service = AdminService(self.auth_service, self.knowledge_config_service)
        self.student_service = StudentService()
        self.diagnosis_service = DiagnosisService(graph_service)
        self.practice_service = PracticeService(repository)
        self.question_bank_service = QuestionBankService(repository, llm_service)
        self.mistake_service = MistakeService(graph_service)
        self.report_service = ReportService(graph_service)
        self.tutor_service = TutorService(graph_service, rag_service, llm_service)
        self.chat_service = ChatService(graph_service, rag_service, llm_service)
        self.teacher_service = TeacherService()
        self.document_service = DocumentService(retrieval_service, dashscope_service)
        self.rag_service = rag_service
        self.llm_service = llm_service

        init_database()
        self._seed_database()

    def _seed_database(self) -> None:
        self._seed_admin()
        self.auth_service.ensure_demo_user()
        with sql_repository.session() as session:
            if not session.execute(select(RagDocumentORM)).scalars().first():
                session.add_all(
                    [
                        RagDocumentORM(
                            topic_id="functions",
                            title="函数概念卡片",
                            content="函数描述的是输入和输出之间的唯一对应关系。先明确自变量，再观察因变量怎样随之变化。",
                        ),
                        RagDocumentORM(
                            topic_id="linear_functions",
                            title="一次函数图像要点",
                            content="一次函数 y=kx+b 中，k 决定倾斜方向和陡峭程度，b 决定图像与 y 轴的交点。",
                        ),
                        RagDocumentORM(
                            topic_id=None,
                            title="苏格拉底式提问模板",
                            content="先让学生复述已知条件，再追问目标量、可用规则和第一步操作，避免直接给答案。",
                        ),
                    ]
                )

            if not session.execute(select(QuestionBankORM)).scalars().first():
                for topic in self.repository.list_topics():
                    for question in self.repository.list_questions_by_topic(topic.id):
                        session.add(
                            QuestionBankORM(
                                external_id=question.id,
                                topic_id=question.topic_id,
                                stem=question.stem,
                                difficulty=question.difficulty,
                                answer=question.answer,
                                explanation=question.explanation,
                                question_type=question.question_type.value,
                                options=[dump_model(option) for option in question.options],
                                blank_count=question.blank_count,
                                score_points=[dump_model(point) for point in question.score_points],
                                tags=question.tags,
                            )
                        )

            for topic in self.repository.list_topics():
                for question in self.repository.list_questions_by_topic(topic.id):
                    row = session.execute(
                        select(QuestionBankORM).where(QuestionBankORM.external_id == question.id)
                    ).scalars().first()
                    if row is None:
                        row = QuestionBankORM(external_id=question.id, source="seed")
                        session.add(row)
                    if row and (row.source or "seed") == "seed":
                        row.topic_id = question.topic_id
                        row.stem = question.stem
                        row.difficulty = question.difficulty
                        row.answer = question.answer
                        row.explanation = question.explanation
                        row.question_type = question.question_type.value
                        row.options = [dump_model(option) for option in question.options]
                        row.blank_count = question.blank_count
                        row.score_points = [dump_model(point) for point in question.score_points]
                        row.tags = question.tags

            if not session.execute(select(KnowledgeDocumentORM)).scalars().first():
                from app.domain.models import KnowledgeDocumentImportItem, KnowledgeDocumentImportRequest

                self.document_service.import_documents(
                    KnowledgeDocumentImportRequest(
                        documents=[
                            KnowledgeDocumentImportItem(
                                title="函数教材导学",
                                topic_id="functions",
                                doc_type="textbook",
                                source_name="数学教材七年级下",
                                content="函数的核心是对应关系。先确定输入量，再判断输出量如何随之变化。自变量决定因变量。",
                            ),
                            KnowledgeDocumentImportItem(
                                title="一次函数讲义提要",
                                topic_id="linear_functions",
                                doc_type="handout",
                                source_name="课堂讲义 A1",
                                content="一次函数 y=kx+b 中，k 是斜率，b 是截距。学图像时先看 b 的位置，再看 k 的变化方向。",
                            ),
                            KnowledgeDocumentImportItem(
                                title="函数题解示例",
                                topic_id="functions",
                                doc_type="solution",
                                source_name="题解集 01",
                                content="遇到函数概念题，先判断谁是输入，谁是输出，再把数量关系翻译成生活场景中的含义。",
                            ),
                        ]
                    )
                )

            demo_user = session.execute(select(UserORM).where(UserORM.email == "demo@zhuyu.local")).scalars().first()
            if not demo_user:
                return
            demo_school = session.execute(select(SchoolORM).where(SchoolORM.name == "祝余实验学校")).scalars().first()
            if not demo_school:
                demo_school = SchoolORM(name="祝余实验学校", region="通用课标示范区")
                session.add(demo_school)
                session.flush()
            if demo_user and demo_user.school_id is None:
                demo_user.school_id = demo_school.id
            default_textbook = session.execute(
                select(TextbookORM).where(TextbookORM.school_id == demo_school.id).order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().first()
            if not default_textbook:
                default_textbook = TextbookORM(school_id=demo_school.id, name="通用教材", is_default=1)
                session.add(default_textbook)
                session.flush()
            default_textbook_id = default_textbook.id
            demo_classroom = session.execute(
                select(ClassroomORM).where(
                    ClassroomORM.teacher_user_id == demo_user.id,
                    ClassroomORM.name == "八年级1班",
                )
            ).scalars().first()
            if not demo_classroom:
                demo_classroom = ClassroomORM(
                    school_id=demo_school.id,
                    teacher_user_id=demo_user.id,
                    textbook_id=default_textbook_id,
                    name="八年级1班",
                    grade_level="初二",
                    invite_code="ZYU-DEMO01",
                    description="演示班级",
                )
                session.add(demo_classroom)
                session.flush()
            else:
                demo_classroom.invite_code = "ZYU-DEMO01"
                demo_classroom.textbook_id = demo_classroom.textbook_id or default_textbook_id
            demo_profile = session.execute(
                select(StudentProfileORM).where(StudentProfileORM.user_id == demo_user.id)
            ).scalars().first()
            if not demo_profile:
                demo_profile = StudentProfileORM(
                    user_id=demo_user.id,
                    school_id=demo_school.id,
                    classroom_id=demo_classroom.id,
                    teacher_user_id=demo_user.id,
                    textbook_id=default_textbook_id,
                    name="小余",
                    grade_level="初二",
                    target_subject="数学",
                    target_topic_id="linear_functions",
                )
                session.add(demo_profile)
                session.flush()
                session.add(ClassroomEnrollmentORM(classroom_id=demo_classroom.id, student_profile_id=demo_profile.id))
                for topic in self.repository.list_topics():
                    session.add(
                        StudentMasteryORM(
                            student_profile_id=demo_profile.id,
                            topic_id=topic.id,
                            mastery=0.0,
                            practice_count=0,
                            correct_count=0,
                            last_practiced_at=None,
                            recent_errors=[],
                        )
                    )
            else:
                demo_profile.school_id = demo_profile.school_id or demo_school.id
                demo_profile.classroom_id = demo_profile.classroom_id or demo_classroom.id
                demo_profile.teacher_user_id = demo_profile.teacher_user_id or demo_user.id
                demo_profile.textbook_id = demo_profile.textbook_id or default_textbook_id
                existing_enrollment = session.execute(
                    select(ClassroomEnrollmentORM).where(
                        ClassroomEnrollmentORM.classroom_id == demo_classroom.id,
                        ClassroomEnrollmentORM.student_profile_id == demo_profile.id,
                    )
                ).scalars().first()
                if not existing_enrollment:
                    session.add(ClassroomEnrollmentORM(classroom_id=demo_classroom.id, student_profile_id=demo_profile.id))

    def _seed_admin(self) -> None:
        email = os.getenv("ADMIN_EMAIL", "admin@zhuyu.local").strip()
        password = os.getenv("ADMIN_PASSWORD", "admin123456").strip()
        name = os.getenv("ADMIN_NAME", "学校管理员").strip() or "学校管理员"
        school_name = os.getenv("ADMIN_SCHOOL_NAME", "祝余实验学校").strip() or "祝余实验学校"
        school_region = os.getenv("ADMIN_SCHOOL_REGION", "").strip()
        if not email or not password:
            return
        with sql_repository.session() as session:
            school = session.execute(select(SchoolORM).where(SchoolORM.name == school_name)).scalars().first()
            if not school:
                school = SchoolORM(name=school_name, region=school_region)
                session.add(school)
                session.flush()
            admin = session.execute(select(UserORM).where(UserORM.email == email)).scalars().first()
            if admin:
                admin.role = "admin"
                admin.school_id = school.id
                admin.full_name = admin.full_name or name
                return
        try:
            self.auth_service.create_user(
                email=email,
                password=password,
                full_name=name,
                role="admin",
                school_id=school.id,
                issue_token=False,
            )
        except ValueError:
            pass


container = ServiceContainer()
