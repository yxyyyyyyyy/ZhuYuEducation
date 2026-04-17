from __future__ import annotations

from pathlib import Path
import os
import random

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
                            topic_id=None,
                            title="函数概念卡片",
                            content="函数描述的是输入和输出之间的唯一对应关系。先明确自变量，再观察因变量怎样随之变化。",
                        ),
                        RagDocumentORM(
                            topic_id=None,
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

            if not session.execute(select(KnowledgeDocumentORM)).scalars().first():
                from app.domain.models import KnowledgeDocumentImportItem, KnowledgeDocumentImportRequest

                self.document_service.import_documents(
                    KnowledgeDocumentImportRequest(
                        documents=[
                            KnowledgeDocumentImportItem(
                                title="函数教材导学",
                                topic_id=None,
                                doc_type="textbook",
                                source_name="数学教材七年级下",
                                content="函数的核心是对应关系。先确定输入量，再判断输出量如何随之变化。自变量决定因变量。",
                            ),
                            KnowledgeDocumentImportItem(
                                title="一次函数讲义提要",
                                topic_id=None,
                                doc_type="handout",
                                source_name="课堂讲义 A1",
                                content="一次函数 y=kx+b 中，k 是斜率，b 是截距。学图像时先看 b 的位置，再看 k 的变化方向。",
                            ),
                            KnowledgeDocumentImportItem(
                                title="函数题解示例",
                                topic_id=None,
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
            self.knowledge_config_service.ensure_seeded(demo_school.id)
            default_textbook = session.execute(
                select(TextbookORM)
                .where(TextbookORM.school_id == demo_school.id)
                .order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().first()
            if not default_textbook:
                default_textbook = TextbookORM(
                    school_id=demo_school.id,
                    grade_level="初二",
                    subject="数学",
                    name="初二数学教材",
                    is_default=1,
                )
                session.add(default_textbook)
                session.flush()
            default_textbook_id = default_textbook.id
            extra_subjects = [
                ("语文", "初二语文教材", "初二"),
                ("英语", "初二英语教材", "初二"),
                ("物理", "初三物理教材", "初三"),
                ("化学", "初三化学教材", "初三"),
                ("生物", "初一生物教材", "初一"),
                ("历史", "初二历史教材", "初二"),
                ("地理", "初一地理教材", "初一"),
            ]
            for sub, tname, glevel in extra_subjects:
                existing_tb = session.execute(
                    select(TextbookORM).where(
                        TextbookORM.school_id == demo_school.id,
                        TextbookORM.subject == sub,
                    )
                ).scalars().first()
                if not existing_tb:
                    tb = TextbookORM(
                        school_id=demo_school.id,
                        grade_level=glevel,
                        subject=sub,
                        name=tname,
                        is_default=0,
                    )
                    session.add(tb)
                    session.flush()
                    self.knowledge_config_service.seed_textbook_nodes(demo_school.id, tb.id)
            available_topics = self.knowledge_config_service.list_topics_for_school(demo_school.id, None)
            default_topic = next((item for item in available_topics if item.level == 2), None)
            default_topic_id = default_topic.id if default_topic else ""
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
                    target_topic_id=default_topic_id,
                )
                session.add(demo_profile)
                session.flush()
                session.add(ClassroomEnrollmentORM(classroom_id=demo_classroom.id, student_profile_id=demo_profile.id))
                for topic in available_topics:
                    if topic.level != 2:
                        continue
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
                if not demo_profile.target_topic_id:
                    demo_profile.target_topic_id = default_topic_id
                existing_enrollment = session.execute(
                    select(ClassroomEnrollmentORM).where(
                        ClassroomEnrollmentORM.classroom_id == demo_classroom.id,
                        ClassroomEnrollmentORM.student_profile_id == demo_profile.id,
                    )
                ).scalars().first()
                if not existing_enrollment:
                    session.add(ClassroomEnrollmentORM(classroom_id=demo_classroom.id, student_profile_id=demo_profile.id))

            demo_classroom2 = session.execute(
                select(ClassroomORM).where(
                    ClassroomORM.teacher_user_id == demo_user.id,
                    ClassroomORM.name == "八年级2班",
                )
            ).scalars().first()
            if not demo_classroom2:
                demo_classroom2 = ClassroomORM(
                    school_id=demo_school.id,
                    teacher_user_id=demo_user.id,
                    textbook_id=default_textbook_id,
                    name="八年级2班",
                    grade_level="初二",
                    invite_code="ZYU-DEMO02",
                    description="演示班级2",
                )
                session.add(demo_classroom2)
                session.flush()
            else:
                demo_classroom2.invite_code = "ZYU-DEMO02"
                demo_classroom2.textbook_id = demo_classroom2.textbook_id or default_textbook_id

            demo_student_names = [
                ("张明轩", "初二", "数学", demo_classroom.id),
                ("李思涵", "初二", "语文", demo_classroom.id),
                ("王子涵", "初二", "英语", demo_classroom.id),
                ("赵雨萱", "初二", "数学", demo_classroom.id),
                ("刘浩然", "初二", "物理", demo_classroom.id),
                ("周雅婷", "初二", "语文", demo_classroom.id),
                ("陈诗琪", "初二", "数学", demo_classroom2.id),
                ("杨博文", "初二", "英语", demo_classroom2.id),
                ("孙晓峰", "初二", "物理", demo_classroom2.id),
                ("吴佳怡", "初二", "语文", demo_classroom2.id),
                ("黄子轩", "初二", "数学", demo_classroom2.id),
                ("林雨彤", "初二", "英语", demo_classroom2.id),
            ]
            for sname, sgrade, ssubject, sclassroom_id in demo_student_names:
                existing = session.execute(
                    select(StudentProfileORM).where(
                        StudentProfileORM.name == sname,
                        StudentProfileORM.teacher_user_id == demo_user.id,
                    )
                ).scalars().first()
                if existing:
                    continue
                subject_topic = next((t for t in available_topics if t.level == 2 and t.subject == ssubject), None)
                s_topic_id = subject_topic.id if subject_topic else default_topic_id
                s_textbook_id = default_textbook_id
                if subject_topic:
                    subject_tb = session.execute(
                        select(TextbookORM).where(
                            TextbookORM.school_id == demo_school.id,
                            TextbookORM.subject == ssubject,
                        )
                    ).scalars().first()
                    if subject_tb:
                        s_textbook_id = subject_tb.id
                s_profile = StudentProfileORM(
                    user_id=demo_user.id,
                    school_id=demo_school.id,
                    classroom_id=sclassroom_id,
                    teacher_user_id=demo_user.id,
                    textbook_id=s_textbook_id,
                    name=sname,
                    grade_level=sgrade,
                    target_subject=ssubject,
                    target_topic_id=s_topic_id,
                )
                session.add(s_profile)
                session.flush()
                session.add(ClassroomEnrollmentORM(classroom_id=sclassroom_id, student_profile_id=s_profile.id))
                for topic in available_topics:
                    if topic.level != 2:
                        continue
                    session.add(
                        StudentMasteryORM(
                            student_profile_id=s_profile.id,
                            topic_id=topic.id,
                            mastery=round(random.uniform(0.1, 0.9), 2),
                            practice_count=random.randint(2, 20),
                            correct_count=random.randint(1, 15),
                            last_practiced_at=None,
                            recent_errors=[],
                        )
                    )

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
