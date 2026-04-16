from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.core.container import container
from app.core.database import engine
from app.domain.models import (
    AuthResponse,
    AdminDashboard,
    AnnouncementCreate,
    AnnouncementDraftView,
    AnnouncementView,
    ChatMessageSend,
    ChatMessageView,
    ChatSessionCreate,
    ChatSessionView,
    ChatTurnResponse,
    ClassroomCreate,
    ClassroomView,
    CsvImportResponse,
    DiagnosisRequest,
    DiagnosisResponse,
    DiagnosisRunRequest,
    HealthResponse,
    KnowledgeDirectoryImportRequest,
    KnowledgeDirectoryImportResponse,
    KnowledgeDocumentImportRequest,
    KnowledgeDocumentView,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeTreeNode,
    LoginRequest,
    MasteryUpsertRequest,
    MistakeAnalysisRequest,
    MistakeAnalysisResponse,
    MistakeRunRequest,
    MistakeRecordView,
    PracticeAnalyticsSummary,
    PracticeCoachCard,
    PracticeCoachRequest,
    PracticeReviewResolveRequest,
    PracticeReviewView,
    PracticeRequest,
    PracticeResponse,
    PracticeRunRequest,
    PracticeSubmissionRequest,
    PracticeSubmissionResponse,
    Question,
    QuestionBankImportRequest,
    QuestionBankItemView,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    QuestionReviewRequest,
    QuestionReviewResponse,
    ReadinessCheck,
    ReadinessResponse,
    RegisterRequest,
    ReportRecordView,
    ReportRequest,
    ReportRunRequest,
    SchoolCreate,
    SchoolView,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResponse,
    RetrievalCaseCreate,
    RetrievalCaseRunResponse,
    RetrievalCaseView,
    RetrievalQualityDashboard,
    StudentDashboard,
    StudentProfileCreate,
    StudentProfileDetail,
    StudentProfileSummary,
    StudentRegisterRequest,
    StudyReportResponse,
    TeacherDashboard,
    TeacherCreateRequest,
    TeacherImportResponse,
    TeacherManageItem,
    TeacherOption,
    TextbookView,
    Topic,
    TutorRequest,
    TutorResponse,
    UserSummary,
    KnowledgeNodeView,
)

router = APIRouter()


def current_user(token: str | None) -> UserSummary:
    if not token:
        raise HTTPException(status_code=401, detail="missing session token")
    user = container.auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid session token")
    return user


def current_teacher(token: str | None) -> UserSummary:
    user = current_user(token)
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="teacher role required")
    return user


def current_admin(token: str | None) -> UserSummary:
    user = current_user(token)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user


def require_student_profile(student_profile_id: int, user: UserSummary) -> StudentProfileDetail:
    try:
        return container.student_service.get_profile(student_profile_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def require_chat_session(session_id: int, user: UserSummary) -> None:
    if not container.chat_service.user_can_access_session(session_id, user.id):
        raise HTTPException(status_code=404, detail="chat session not found")


def _topics_for_context(user: UserSummary | None = None, textbook_id: int | None = None) -> list[Topic]:
    if user and user.school_id:
        try:
            resolved_textbook_id = textbook_id
            if resolved_textbook_id is None:
                resolved_textbook_id = container.knowledge_config_service.resolve_user_textbook_id(user.id, user.school_id)
            return container.knowledge_config_service.list_topics_for_school(user.school_id, resolved_textbook_id)
        except Exception:
            pass
    return container.repository.list_topics()


def require_topic(topic_id: str, user: UserSummary | None = None, textbook_id: int | None = None) -> None:
    if any(topic.id == topic_id for topic in _topics_for_context(user, textbook_id)):
        return
    if container.repository.has_topic(topic_id):
        return
    raise HTTPException(status_code=404, detail="topic not found")


def require_optional_topic(
    topic_id: str | None,
    field_name: str = "topic_id",
    user: UserSummary | None = None,
    textbook_id: int | None = None,
) -> None:
    if topic_id:
        try:
            require_topic(topic_id, user=user, textbook_id=textbook_id)
        except HTTPException:
            raise HTTPException(status_code=400, detail=f"{field_name} not found")


def require_mastery_topics(mastery_map: dict, user: UserSummary | None = None, textbook_id: int | None = None) -> None:
    for topic_id, mastery in mastery_map.items():
        require_optional_topic(topic_id, user=user, textbook_id=textbook_id)
        if mastery.topic_id != topic_id:
            raise HTTPException(status_code=400, detail="mastery topic_id must match the map key")


def _leaf_topics(topics: list[Topic]) -> list[Topic]:
    parent_ids = {item.parent_id for item in topics if item.parent_id}
    return [item for item in topics if item.id not in parent_ids]


def _default_topic_for_grade(
    grade_level: str,
    subject: str,
    school_id: int | None = None,
    textbook_id: int | None = None,
) -> str:
    topics_source = container.repository.list_topics()
    if school_id:
        try:
            topics_source = container.knowledge_config_service.list_topics_for_school(school_id, textbook_id)
        except Exception:
            topics_source = container.repository.list_topics()
    leaf_topics = _leaf_topics(topics_source)
    leaf_topic_ids = {item.id for item in leaf_topics}
    topics = [
        topic for topic in topics_source
        if topic.id in leaf_topic_ids
        if topic.subject == subject and (not topic.grade_level or topic.grade_level == grade_level)
    ]
    if not topics:
        topics = [topic for topic in leaf_topics if topic.subject == subject]
    if not topics:
        topics = leaf_topics
    if not topics:
        topics = _leaf_topics(container.repository.list_topics())
    topics.sort(key=lambda item: (item.sort_order, item.difficulty, item.id))
    return topics[0].id


def _knowledge_tree(school_id: int | None = None, textbook_id: int | None = None) -> list[KnowledgeTreeNode]:
    topics_source = container.repository.list_topics()
    if school_id:
        try:
            topics_source = container.knowledge_config_service.list_topics_for_school(school_id, textbook_id)
        except Exception:
            topics_source = container.repository.list_topics()
    topics = sorted(topics_source, key=lambda item: (item.sort_order, item.id))
    question_counts = {topic.id: 0 for topic in topics}
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT COALESCE(NULLIF(knowledge_l2_id, ''), topic_id) AS topic_key, COUNT(*) AS cnt "
                    "FROM question_bank GROUP BY topic_key"
                )
            ).fetchall()
            for row in rows:
                if row[0] in question_counts:
                    question_counts[row[0]] = int(row[1])
    except Exception:
        pass
    direct_children: dict[str | None, list] = {}
    topic_ids = {topic.id for topic in topics}
    for topic in topics:
        direct_children.setdefault(topic.parent_id, []).append(topic)

    def build_topic_node(topic) -> KnowledgeTreeNode:
        return KnowledgeTreeNode(
            id=topic.id,
            name=topic.name,
            subject=topic.subject,
            level=topic.level,
            grade_level=topic.grade_level,
            question_count=question_counts.get(topic.id, 0),
            children=[build_topic_node(child) for child in direct_children.get(topic.id, [])],
        )

    root_topics = [
        topic for topic in topics
        if not topic.parent_id or topic.parent_id not in topic_ids
    ]
    return [build_topic_node(topic) for topic in root_topics]


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        modules=[
            "knowledge_graph",
            "auth",
            "teacher_dashboard",
            "student_profiles",
            "question_bank",
            "practice_analytics",
            "adaptive_practice",
            "mistake_notebook",
            "chat_history",
            "rag_llm_tutor",
            "document_search",
            "study_report",
        ],
    )


@router.get("/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    checks: list[ReadinessCheck] = []
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks.append(ReadinessCheck(name="database", status="ok"))
    except Exception as exc:
        checks.append(ReadinessCheck(name="database", status="fail", detail=exc.__class__.__name__))

    try:
        topic_count = len(container.repository.list_topics())
        if topic_count:
            checks.append(ReadinessCheck(name="knowledge_graph", status="ok", detail=f"{topic_count} topics"))
        else:
            checks.append(ReadinessCheck(name="knowledge_graph", status="fail", detail="no topics loaded"))
    except Exception as exc:
        checks.append(ReadinessCheck(name="knowledge_graph", status="fail", detail=exc.__class__.__name__))

    checks.append(
        ReadinessCheck(
            name="llm",
            status="ok" if container.llm_service.api_key else "disabled",
            detail=container.llm_service.model,
        )
    )
    checks.append(
        ReadinessCheck(
            name="dashscope",
            status="ok" if container.dashscope_service.enabled else "disabled",
            detail=container.dashscope_service.embedding_model,
        )
    )

    blocking = [item for item in checks if item.status == "fail"]
    return ReadinessResponse(status="ok" if not blocking else "fail", checks=checks)


@router.post("/auth/register", response_model=AuthResponse)
def register(request: RegisterRequest) -> AuthResponse:
    try:
        return container.auth_service.register(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/auth/register/student", response_model=AuthResponse)
def register_student(request: StudentRegisterRequest) -> AuthResponse:
    try:
        classroom = container.teacher_service.find_classroom_by_invite_code(request.invite_code)
        auth = container.auth_service.register(request)
        target_topic_id = request.target_topic_id or _default_topic_for_grade(
            classroom.grade_level,
            request.target_subject,
            school_id=classroom.school_id,
            textbook_id=classroom.textbook_id,
        )
        container.student_service.create_profile(
            auth.user.id,
            StudentProfileCreate(
                name=request.full_name,
                grade_level=classroom.grade_level,
                target_subject=request.target_subject,
                target_topic_id=target_topic_id,
                school_id=classroom.school_id,
                classroom_id=classroom.id,
                teacher_user_id=classroom.teacher_user_id,
                textbook_id=classroom.textbook_id,
            ),
        )
        return auth
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest) -> AuthResponse:
    try:
        return container.auth_service.login(request)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/admin/dashboard", response_model=AdminDashboard)
def admin_dashboard(x_session_token: str | None = Header(default=None)) -> AdminDashboard:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.dashboard(user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/admin/teachers", response_model=list[TeacherOption])
def admin_list_teachers(x_session_token: str | None = Header(default=None)) -> list[TeacherOption]:
    user = current_admin(x_session_token)
    return container.admin_service.list_teachers(user.id)


@router.get("/admin/teachers/manage", response_model=dict)
def admin_manage_teachers(
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    x_session_token: str | None = Header(default=None),
) -> dict:
    user = current_admin(x_session_token)
    return container.admin_service.list_teachers_manage(user.id, q=q, page=page, page_size=page_size)


@router.post("/admin/teachers", response_model=TeacherOption)
def admin_create_teacher(
    request: TeacherCreateRequest,
    x_session_token: str | None = Header(default=None),
) -> TeacherOption:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.create_teacher(user.id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/admin/teachers/import-csv", response_model=TeacherImportResponse)
def admin_import_teachers_csv(
    csv_content: str = Body(..., media_type="text/plain"),
    x_session_token: str | None = Header(default=None),
) -> TeacherImportResponse:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.import_teachers_by_csv(user.id, csv_content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/admin/teachers/{teacher_id}/reset-password", response_model=dict)
def admin_reset_teacher_password(teacher_id: int, x_session_token: str | None = Header(default=None)) -> dict:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.reset_teacher_password(user.id, teacher_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/admin/teachers/{teacher_id}", response_model=dict[str, str])
def admin_delete_teacher(teacher_id: int, x_session_token: str | None = Header(default=None)) -> dict[str, str]:
    user = current_admin(x_session_token)
    try:
        container.admin_service.delete_teacher(user.id, teacher_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.get("/admin/announcements", response_model=list[AnnouncementView])
def admin_list_announcements(x_session_token: str | None = Header(default=None)) -> list[AnnouncementView]:
    user = current_admin(x_session_token)
    return container.admin_service.list_announcements(user.id)


@router.get("/admin/announcements/manage", response_model=dict)
def admin_manage_announcements(
    q: str = "",
    page: int = 1,
    page_size: int = 12,
    x_session_token: str | None = Header(default=None),
) -> dict:
    user = current_admin(x_session_token)
    return container.admin_service.list_announcements_manage(user.id, q=q, page=page, page_size=page_size)


@router.post("/admin/announcements", response_model=AnnouncementView)
def admin_create_announcement(
    request: AnnouncementCreate,
    x_session_token: str | None = Header(default=None),
) -> AnnouncementView:
    user = current_admin(x_session_token)
    return container.admin_service.create_announcement(user.id, request)


@router.get("/admin/announcements/{announcement_id}", response_model=AnnouncementView)
def admin_get_announcement(announcement_id: int, x_session_token: str | None = Header(default=None)) -> AnnouncementView:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.get_announcement(user.id, announcement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/admin/announcements/{announcement_id}", response_model=AnnouncementView)
def admin_update_announcement(
    announcement_id: int,
    request: AnnouncementCreate,
    x_session_token: str | None = Header(default=None),
) -> AnnouncementView:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.update_announcement(user.id, announcement_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/admin/announcements/{announcement_id}", response_model=dict[str, str])
def admin_delete_announcement(announcement_id: int, x_session_token: str | None = Header(default=None)) -> dict[str, str]:
    user = current_admin(x_session_token)
    try:
        container.admin_service.delete_announcement(user.id, announcement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "ok"}


@router.get("/admin/announcement-draft", response_model=AnnouncementDraftView | None)
def admin_get_announcement_draft(x_session_token: str | None = Header(default=None)) -> AnnouncementDraftView | None:
    user = current_admin(x_session_token)
    return container.admin_service.get_announcement_draft(user.id)


@router.put("/admin/announcement-draft", response_model=AnnouncementDraftView)
def admin_save_announcement_draft(
    payload: dict,
    x_session_token: str | None = Header(default=None),
) -> AnnouncementDraftView:
    user = current_admin(x_session_token)
    return container.admin_service.save_announcement_draft(
        user.id,
        payload.get("title", ""),
        payload.get("content_html", ""),
    )


@router.get("/admin/question-bank", response_model=list[QuestionBankItemView])
def admin_question_bank(x_session_token: str | None = Header(default=None)) -> list[QuestionBankItemView]:
    current_admin(x_session_token)
    return container.question_bank_service.list_questions()


@router.get("/admin/question-bank/manage", response_model=dict)
def admin_manage_question_bank(
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
    x_session_token: str | None = Header(default=None),
) -> dict:
    user = current_admin(x_session_token)
    return container.admin_service.list_question_bank_manage(
        admin_user_id=user.id,
        q=q,
        knowledge_l1_id=knowledge_l1_id,
        knowledge_l2_id=knowledge_l2_id,
        topic_id=topic_id,
        subject=subject,
        grade_level=grade_level,
        status=status,
        question_type=question_type,
        difficulty_level_min=difficulty_level_min,
        difficulty_level_max=difficulty_level_max,
        page=page,
        page_size=page_size,
        textbook_id=textbook_id,
    )


@router.post("/admin/question-bank/batch", response_model=dict)
def admin_batch_question_bank(
    payload: dict,
    x_session_token: str | None = Header(default=None),
) -> dict:
    current_admin(x_session_token)
    question_ids = payload.get("question_ids") or []
    action = payload.get("action") or ""
    try:
        updated = container.admin_service.update_question_bank_status(question_ids, action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"updated_count": updated}


@router.post("/admin/question-bank/export", response_class=PlainTextResponse)
def admin_export_question_bank(
    payload: dict,
    x_session_token: str | None = Header(default=None),
) -> PlainTextResponse:
    user = current_admin(x_session_token)
    csv_content = container.admin_service.export_question_bank(user.id, payload or {})
    return PlainTextResponse(
        content="\ufeff" + csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=question_bank_export.csv"},
    )


@router.get("/admin/knowledge-tree", response_model=list[KnowledgeTreeNode])
def admin_knowledge_tree(x_session_token: str | None = Header(default=None)) -> list[KnowledgeTreeNode]:
    user = current_admin(x_session_token)
    return _knowledge_tree(school_id=user.school_id)


@router.get("/admin/textbooks", response_model=list[TextbookView])
def admin_list_textbooks(x_session_token: str | None = Header(default=None)) -> list[TextbookView]:
    user = current_admin(x_session_token)
    return container.admin_service.list_textbooks(user.id)


@router.post("/admin/textbooks", response_model=TextbookView)
def admin_create_textbook(payload: dict, x_session_token: str | None = Header(default=None)) -> TextbookView:
    user = current_admin(x_session_token)
    try:
        return container.admin_service.create_textbook(
            user.id,
            name=payload.get("name", ""),
            grade_level=payload.get("grade_level", ""),
            subject=payload.get("subject", ""),
            set_default=bool(payload.get("is_default", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin/knowledge/tree", response_model=list[KnowledgeNodeView])
def admin_list_knowledge_tree(
    textbook_id: int | None = None,
    x_session_token: str | None = Header(default=None),
) -> list[KnowledgeNodeView]:
    user = current_admin(x_session_token)
    return container.admin_service.list_knowledge_tree(user.id, textbook_id)


@router.get("/admin/knowledge/topic-options", response_model=list[Topic])
def admin_knowledge_topic_options(x_session_token: str | None = Header(default=None)) -> list[Topic]:
    current_admin(x_session_token)
    return container.admin_service.topic_ref_options()


@router.post("/admin/knowledge/nodes", response_model=KnowledgeNodeView)
def admin_create_knowledge_node(payload: dict, x_session_token: str | None = Header(default=None)) -> KnowledgeNodeView:
    user = current_admin(x_session_token)
    textbook_id = payload.get("textbook_id")
    if textbook_id is None:
        raise HTTPException(status_code=400, detail="textbook_id is required")
    try:
        return container.admin_service.create_knowledge_node(
            admin_user_id=user.id,
            textbook_id=int(textbook_id),
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/admin/knowledge/nodes/{node_key}", response_model=KnowledgeNodeView)
def admin_update_knowledge_node(
    node_key: str,
    payload: dict,
    x_session_token: str | None = Header(default=None),
) -> KnowledgeNodeView:
    user = current_admin(x_session_token)
    textbook_id = payload.get("textbook_id")
    if textbook_id is None:
        raise HTTPException(status_code=400, detail="textbook_id is required")
    try:
        return container.admin_service.update_knowledge_node(
            admin_user_id=user.id,
            textbook_id=int(textbook_id),
            node_key=node_key,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/admin/knowledge/nodes/{node_key}", response_model=dict)
def admin_delete_knowledge_node(
    node_key: str,
    textbook_id: int,
    x_session_token: str | None = Header(default=None),
) -> dict:
    user = current_admin(x_session_token)
    deleted_count = container.admin_service.delete_knowledge_node(user.id, textbook_id, node_key)
    return {"deleted_count": deleted_count}


@router.post("/admin/knowledge/nodes/batch-delete", response_model=dict)
def admin_batch_delete_knowledge_nodes(payload: dict, x_session_token: str | None = Header(default=None)) -> dict:
    user = current_admin(x_session_token)
    textbook_id = payload.get("textbook_id")
    if textbook_id is None:
        raise HTTPException(status_code=400, detail="textbook_id is required")
    deleted_count = container.admin_service.batch_delete_knowledge_nodes(
        user.id,
        int(textbook_id),
        payload.get("node_keys") or [],
    )
    return {"deleted_count": deleted_count}


@router.post("/admin/knowledge/nodes/reorder", response_model=dict)
def admin_reorder_knowledge_nodes(payload: dict, x_session_token: str | None = Header(default=None)) -> dict:
    user = current_admin(x_session_token)
    textbook_id = payload.get("textbook_id")
    if textbook_id is None:
        raise HTTPException(status_code=400, detail="textbook_id is required")
    updated = container.admin_service.reorder_knowledge_nodes(
        admin_user_id=user.id,
        textbook_id=int(textbook_id),
        parent_node_key=payload.get("parent_node_key"),
        ordered_node_keys=payload.get("ordered_node_keys") or [],
    )
    return {"updated_count": updated}


@router.get("/auth/me", response_model=UserSummary)
def me(x_session_token: str | None = Header(default=None)) -> UserSummary:
    return current_user(x_session_token)


@router.post("/auth/logout", response_model=dict[str, str])
def logout(x_session_token: str | None = Header(default=None)) -> dict[str, str]:
    current_user(x_session_token)
    container.auth_service.logout(x_session_token or "")
    return {"status": "ok"}


@router.get("/teacher/dashboard", response_model=TeacherDashboard)
def teacher_dashboard(x_session_token: str | None = Header(default=None)) -> TeacherDashboard:
    user = current_teacher(x_session_token)
    return container.teacher_service.dashboard(user.id)


@router.get("/schools", response_model=list[SchoolView])
def list_schools() -> list[SchoolView]:
    return container.teacher_service.list_schools()


@router.get("/teachers", response_model=list[TeacherOption])
def list_teachers() -> list[TeacherOption]:
    return container.teacher_service.list_teachers()


@router.get("/classrooms", response_model=list[ClassroomView])
def list_public_classrooms(school_id: int | None = None) -> list[ClassroomView]:
    return container.teacher_service.list_classrooms(school_id=school_id)


@router.post("/teacher/schools", response_model=SchoolView)
def create_school(request: SchoolCreate, x_session_token: str | None = Header(default=None)) -> SchoolView:
    raise HTTPException(status_code=403, detail="school is managed by admin")


@router.get("/teacher/schools", response_model=list[SchoolView])
def list_teacher_schools(x_session_token: str | None = Header(default=None)) -> list[SchoolView]:
    user = current_teacher(x_session_token)
    return container.teacher_service.list_schools(school_id=user.school_id)


@router.get("/teacher/classrooms", response_model=list[ClassroomView])
def list_teacher_classrooms(x_session_token: str | None = Header(default=None)) -> list[ClassroomView]:
    user = current_teacher(x_session_token)
    return container.teacher_service.list_classrooms(teacher_user_id=user.id)


@router.post("/teacher/classrooms", response_model=ClassroomView)
def create_classroom(request: ClassroomCreate, x_session_token: str | None = Header(default=None)) -> ClassroomView:
    user = current_teacher(x_session_token)
    return container.teacher_service.create_classroom(user.id, request)


@router.post("/teacher/classrooms/{classroom_id}/refresh-invite-code", response_model=ClassroomView)
def refresh_classroom_invite_code(classroom_id: int, x_session_token: str | None = Header(default=None)) -> ClassroomView:
    user = current_teacher(x_session_token)
    try:
        return container.teacher_service.refresh_invite_code(user.id, classroom_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/teacher/question-bank/import", response_model=list[QuestionBankItemView])
def import_question_bank(
    request: QuestionBankImportRequest,
    x_session_token: str | None = Header(default=None),
) -> list[QuestionBankItemView]:
    user = current_teacher(x_session_token)
    try:
        for question in request.questions:
            require_optional_topic(question.knowledge_l2_id, user=user)
            require_optional_topic(question.knowledge_l1_id, user=user)
        return container.question_bank_service.import_questions(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/teacher/question-bank", response_model=list[QuestionBankItemView])
def list_question_bank(x_session_token: str | None = Header(default=None)) -> list[QuestionBankItemView]:
    current_teacher(x_session_token)
    return container.question_bank_service.list_questions()


@router.post("/teacher/question-bank/generate", response_model=QuestionGenerateResponse)
def generate_questions(
    request: QuestionGenerateRequest,
    x_session_token: str | None = Header(default=None),
) -> QuestionGenerateResponse:
    user = current_teacher(x_session_token)
    try:
        require_topic(request.knowledge_l2_id, user=user)
        require_optional_topic(request.knowledge_l1_id, field_name="knowledge_l1_id", user=user)
        if request.difficulty_level_min > request.difficulty_level_max:
            raise HTTPException(status_code=400, detail="difficulty_level_min must be <= difficulty_level_max")
        return container.question_bank_service.generate_questions(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/teacher/question-bank/pending", response_model=list[QuestionBankItemView])
def list_pending_questions(x_session_token: str | None = Header(default=None)) -> list[QuestionBankItemView]:
    current_teacher(x_session_token)
    return container.question_bank_service.list_pending_questions()


@router.post("/teacher/question-bank/review", response_model=QuestionReviewResponse)
def review_questions(
    request: QuestionReviewRequest,
    x_session_token: str | None = Header(default=None),
) -> QuestionReviewResponse:
    current_teacher(x_session_token)
    return container.question_bank_service.review_questions(request)


@router.post("/teacher/question-bank/import-csv", response_model=CsvImportResponse)
def import_csv_questions(
    csv_content: str = Body(..., media_type="text/plain"),
    x_session_token: str | None = Header(default=None),
) -> CsvImportResponse:
    current_teacher(x_session_token)
    try:
        return container.question_bank_service.import_csv(csv_content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/teacher/question-bank/csv-template", response_class=PlainTextResponse)
def download_csv_template(x_session_token: str | None = Header(default=None)) -> PlainTextResponse:
    current_teacher(x_session_token)
    template = "\ufeff题目,答案,一级知识点ID,二级知识点ID,难度级别,知识点层级标签,解析,题型,选项,空数,得分点,标签\n"
    template += "解方程 3x=12,x=4,tb5_l1_数与代数,tb5_l2_方程与不等式,2,基础知识点,两边除以3,blank,,1,,方程\n"
    template += "一次函数 y=2x+1 的斜率是多少？,2,tb5_l1_数与代数,tb5_l2_函数初步,3,核心知识点,与y=kx+b对照k=2,blank,,1,斜率:1:2,斜率\n"
    template += "一次函数 y=2x+3 的图像与 y 轴交点是多少？,3,tb5_l1_数与代数,tb5_l2_函数初步,3,核心知识点,截距由 b 决定,choice,A:1|B:2|C:3|D:5,1,,选择题\n"
    template += "判断：一次函数 y=kx+b 中 k 表示斜率。,正确,tb5_l1_数与代数,tb5_l2_函数初步,2,基础知识点,k 决定图像倾斜程度,judgment,,1,,判断题\n"
    return PlainTextResponse(content=template, media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=question_template.csv"
    })


@router.get("/teacher/analytics/practice", response_model=PracticeAnalyticsSummary)
def teacher_practice_analytics(x_session_token: str | None = Header(default=None)) -> PracticeAnalyticsSummary:
    user = current_teacher(x_session_token)
    student_ids = container.teacher_service.student_ids_for_teacher(user.id)
    return container.question_bank_service.analytics_for_students(student_ids)


@router.get("/teacher/practice-reviews", response_model=list[PracticeReviewView])
def list_practice_reviews(
    status: str = "pending",
    x_session_token: str | None = Header(default=None),
) -> list[PracticeReviewView]:
    user = current_teacher(x_session_token)
    normalized_status = status if status in {"pending", "reviewed", "all"} else "pending"
    return container.question_bank_service.list_practice_reviews(user.id, normalized_status)


@router.post("/teacher/practice-reviews/{record_id}", response_model=PracticeReviewView)
def resolve_practice_review(
    record_id: int,
    request: PracticeReviewResolveRequest,
    x_session_token: str | None = Header(default=None),
) -> PracticeReviewView:
    user = current_teacher(x_session_token)
    try:
        return container.question_bank_service.resolve_practice_review(record_id, user.id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/teacher/documents/import", response_model=list[KnowledgeDocumentView])
def import_documents(
    request: KnowledgeDocumentImportRequest,
    x_session_token: str | None = Header(default=None),
) -> list[KnowledgeDocumentView]:
    user = current_teacher(x_session_token)
    for document in request.documents:
        require_optional_topic(document.topic_id, user=user)
    return container.document_service.import_documents(request, user.id)


@router.post("/teacher/documents/upload", response_model=KnowledgeDocumentView)
async def upload_document(
    file: UploadFile = File(...),
    topic_id: str | None = Form(default=None),
    doc_type: str = Form(default="reference"),
    title: str | None = Form(default=None),
    source_name: str | None = Form(default=None),
    x_session_token: str | None = Header(default=None),
) -> KnowledgeDocumentView:
    user = current_teacher(x_session_token)
    topic_id = topic_id or None
    require_optional_topic(topic_id, user=user)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="uploaded file is larger than 10MB")
    try:
        return container.document_service.import_uploaded_document(
            filename=file.filename or "uploaded.txt",
            content=content,
            title=title,
            topic_id=topic_id,
            doc_type=doc_type or "reference",
            source_name=source_name,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/teacher/documents/import-directory", response_model=KnowledgeDirectoryImportResponse)
def import_documents_from_directory(
    request: KnowledgeDirectoryImportRequest,
    x_session_token: str | None = Header(default=None),
) -> KnowledgeDirectoryImportResponse:
    user = current_teacher(x_session_token)
    require_optional_topic(request.topic_id, user=user)
    try:
        return container.document_service.import_directory(request, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/teacher/documents", response_model=list[KnowledgeDocumentView])
def list_documents(x_session_token: str | None = Header(default=None)) -> list[KnowledgeDocumentView]:
    user = current_teacher(x_session_token)
    return container.document_service.list_documents(user.id)


@router.delete("/teacher/documents/{document_id}", response_model=dict[str, str])
def delete_document(document_id: int, x_session_token: str | None = Header(default=None)) -> dict[str, str]:
    user = current_teacher(x_session_token)
    try:
        container.document_service.delete_document(document_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "ok"}


@router.post("/teacher/documents/rebuild-embeddings", response_model=int)
def rebuild_document_embeddings(x_session_token: str | None = Header(default=None)) -> int:
    user = current_teacher(x_session_token)
    return container.document_service.rebuild_embeddings(user.id)


@router.post("/teacher/documents/search", response_model=list[KnowledgeSearchHit])
def search_documents(
    request: KnowledgeSearchRequest,
    x_session_token: str | None = Header(default=None),
) -> list[KnowledgeSearchHit]:
    user = current_teacher(x_session_token)
    require_optional_topic(request.topic_id, user=user)
    return container.document_service.search(request, user.id)


@router.post("/teacher/documents/evaluate", response_model=RetrievalEvaluationResponse)
def evaluate_documents(
    request: RetrievalEvaluationRequest,
    x_session_token: str | None = Header(default=None),
) -> RetrievalEvaluationResponse:
    user = current_teacher(x_session_token)
    require_optional_topic(request.topic_id, user=user)
    require_optional_topic(request.expected_topic_id, "expected_topic_id", user=user)
    return container.document_service.evaluate_retrieval(request, user.id)


@router.get("/teacher/retrieval-quality", response_model=RetrievalQualityDashboard)
def retrieval_quality_dashboard(
    x_session_token: str | None = Header(default=None),
) -> RetrievalQualityDashboard:
    user = current_teacher(x_session_token)
    return container.document_service.retrieval_quality_dashboard(user.id)


@router.get("/teacher/retrieval-cases", response_model=list[RetrievalCaseView])
def list_retrieval_cases(x_session_token: str | None = Header(default=None)) -> list[RetrievalCaseView]:
    user = current_teacher(x_session_token)
    return container.document_service.list_retrieval_cases(user.id)


@router.post("/teacher/retrieval-cases", response_model=RetrievalCaseView)
def create_retrieval_case(
    request: RetrievalCaseCreate,
    x_session_token: str | None = Header(default=None),
) -> RetrievalCaseView:
    user = current_teacher(x_session_token)
    require_optional_topic(request.expected_topic_id, "expected_topic_id", user=user)
    return container.document_service.create_retrieval_case(user.id, request)


@router.delete("/teacher/retrieval-cases/{case_id}", response_model=dict[str, str])
def delete_retrieval_case(case_id: int, x_session_token: str | None = Header(default=None)) -> dict[str, str]:
    user = current_teacher(x_session_token)
    try:
        container.document_service.delete_retrieval_case(user.id, case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "ok"}


@router.post("/teacher/retrieval-cases/run", response_model=RetrievalCaseRunResponse)
def run_retrieval_cases(x_session_token: str | None = Header(default=None)) -> RetrievalCaseRunResponse:
    user = current_teacher(x_session_token)
    return container.document_service.run_retrieval_cases(user.id)


@router.get("/graph/topics", response_model=list[Topic])
def list_topics(
    textbook_id: int | None = None,
    x_session_token: str | None = Header(default=None),
) -> list[Topic]:
    if x_session_token:
        try:
            user = current_user(x_session_token)
            return _topics_for_context(user, textbook_id)
        except HTTPException:
            pass
    return container.repository.list_topics()


@router.get("/graph/topics/{topic_id}", response_model=Topic)
def get_topic(topic_id: str, x_session_token: str | None = Header(default=None)) -> Topic:
    if x_session_token:
        try:
            user = current_user(x_session_token)
            topic = next((item for item in _topics_for_context(user) if item.id == topic_id), None)
            if topic:
                return topic
        except HTTPException:
            pass
    require_topic(topic_id)
    return container.graph_service.get_topic(topic_id)


@router.get("/questions/{question_id}", response_model=Question)
def get_question(question_id: str, x_session_token: str | None = Header(default=None)) -> Question:
    current_user(x_session_token)
    question = container.question_bank_service.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="question not found")
    return question


@router.get("/students", response_model=list[StudentProfileSummary])
def list_students(x_session_token: str | None = Header(default=None)) -> list[StudentProfileSummary]:
    user = current_user(x_session_token)
    return container.student_service.list_profiles(user.id)


@router.post("/students", response_model=StudentProfileSummary)
def create_student(
    request: StudentProfileCreate,
    x_session_token: str | None = Header(default=None),
) -> StudentProfileSummary:
    user = current_user(x_session_token)
    require_topic(request.target_topic_id, user=user, textbook_id=request.textbook_id)
    if request.textbook_id is None and user.school_id:
        request.textbook_id = container.knowledge_config_service.resolve_user_textbook_id(user.id, user.school_id)
    return container.student_service.create_profile(user.id, request)


@router.get("/students/{student_profile_id}", response_model=StudentProfileDetail)
def get_student(student_profile_id: int, x_session_token: str | None = Header(default=None)) -> StudentProfileDetail:
    user = current_user(x_session_token)
    return require_student_profile(student_profile_id, user)


@router.put("/students/{student_profile_id}/mastery", response_model=StudentProfileDetail)
def save_mastery(
    student_profile_id: int,
    request: MasteryUpsertRequest,
    x_session_token: str | None = Header(default=None),
) -> StudentProfileDetail:
    user = current_user(x_session_token)
    profile = require_student_profile(student_profile_id, user)
    require_mastery_topics(request.mastery, user=user, textbook_id=profile.textbook_id)
    try:
        return container.student_service.save_mastery(student_profile_id, request, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/students/{student_profile_id}/dashboard", response_model=StudentDashboard)
def student_dashboard(
    student_profile_id: int,
    x_session_token: str | None = Header(default=None),
) -> StudentDashboard:
    user = current_user(x_session_token)
    profile = require_student_profile(student_profile_id, user)
    return StudentDashboard(
        profile=profile,
        latest_report=container.report_service.latest(student_profile_id),
        recent_mistakes=container.mistake_service.list_records(student_profile_id)[:6],
        recent_sessions=container.chat_service.list_sessions(student_profile_id)[:6],
        available_topics=_topics_for_context(user, profile.textbook_id),
    )


@router.post("/students/{student_profile_id}/diagnosis", response_model=DiagnosisResponse)
def run_diagnosis(
    student_profile_id: int,
    request: DiagnosisRunRequest,
    x_session_token: str | None = Header(default=None),
) -> DiagnosisResponse:
    user = current_user(x_session_token)
    profile = require_student_profile(student_profile_id, user)
    require_topic(request.target_topic_id, user=user, textbook_id=profile.textbook_id)
    diagnosis = DiagnosisRequest(
        student_id=str(student_profile_id),
        target_topic_id=request.target_topic_id,
        current_mastery=profile.mastery,
    )
    return container.diagnosis_service.evaluate(diagnosis)


@router.post("/students/{student_profile_id}/practice", response_model=PracticeResponse)
def run_practice(
    student_profile_id: int,
    request: PracticeRunRequest,
    x_session_token: str | None = Header(default=None),
) -> PracticeResponse:
    user = current_user(x_session_token)
    profile = require_student_profile(student_profile_id, user)
    require_topic(request.topic_id, user=user, textbook_id=profile.textbook_id)
    practice = PracticeRequest(
        student_id=str(student_profile_id),
        topic_id=request.topic_id,
        current_mastery=profile.mastery,
        recent_question_ids=[],
    )
    try:
        return container.practice_service.recommend_next_question(practice)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/students/{student_profile_id}/practice/submit", response_model=PracticeSubmissionResponse)
def submit_practice(
    student_profile_id: int,
    request: PracticeSubmissionRequest,
    x_session_token: str | None = Header(default=None),
) -> PracticeSubmissionResponse:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    try:
        return container.question_bank_service.submit_practice(
            student_profile_id=student_profile_id,
            recommended_band="standard",
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/students/{student_profile_id}/practice/coach-card", response_model=PracticeCoachCard)
def practice_coach_card(
    student_profile_id: int,
    request: PracticeCoachRequest,
    x_session_token: str | None = Header(default=None),
) -> PracticeCoachCard:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    try:
        return container.question_bank_service.build_coach_card(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/students/{student_profile_id}/mistakes/analyze", response_model=MistakeRecordView)
def analyze_student_mistake(
    student_profile_id: int,
    request: MistakeRunRequest,
    x_session_token: str | None = Header(default=None),
) -> MistakeRecordView:
    user = current_user(x_session_token)
    profile = require_student_profile(student_profile_id, user)
    question = container.question_bank_service.get_question(request.question_id)
    if question is None:
        question = next((item for item in container.repository.list_questions_by_topic(profile.target_topic_id) if item.id == request.question_id), None)
    if question is None:
        for topic in container.repository.list_topics():
            for item in container.repository.list_questions_by_topic(topic.id):
                if item.id == request.question_id:
                    question = item
                    break
            if question:
                break
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")

    result = container.mistake_service.analyze(
        MistakeAnalysisRequest(
            student_id=str(student_profile_id),
            topic_id=question.topic_id,
            question_id=question.id,
            student_answer=request.student_answer,
            correct_answer=question.answer,
            problem_text=question.stem,
            scratchpad=request.scratchpad,
        )
    )
    return container.mistake_service.save_record(
        student_profile_id=student_profile_id,
        question_stem=question.stem,
        result=result,
        student_answer=request.student_answer,
        correct_answer=question.answer,
        question_id=question.id,
    )


@router.get("/students/{student_profile_id}/mistakes", response_model=list[MistakeRecordView])
def list_student_mistakes(
    student_profile_id: int,
    x_session_token: str | None = Header(default=None),
) -> list[MistakeRecordView]:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    return container.mistake_service.list_records(student_profile_id)


@router.post("/students/{student_profile_id}/reports/generate", response_model=ReportRecordView)
def generate_student_report(
    student_profile_id: int,
    request: ReportRunRequest,
    x_session_token: str | None = Header(default=None),
) -> ReportRecordView:
    user = current_user(x_session_token)
    profile = require_student_profile(student_profile_id, user)
    require_topic(request.target_topic_id, user=user, textbook_id=profile.textbook_id)
    report = container.report_service.generate(
        ReportRequest(
            student_id=str(student_profile_id),
            student_name=profile.name,
            target_topic_id=request.target_topic_id,
            current_mastery=profile.mastery,
            recent_mistakes=[],
        )
    )
    return container.report_service.save_report(student_profile_id, report)


@router.get("/students/{student_profile_id}/reports", response_model=list[ReportRecordView])
def list_student_reports(
    student_profile_id: int,
    limit: int = 20,
    x_session_token: str | None = Header(default=None),
) -> list[ReportRecordView]:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    safe_limit = min(max(limit, 1), 100)
    return container.report_service.list_reports(student_profile_id, limit=safe_limit)


@router.get("/students/{student_profile_id}/reports/latest", response_model=ReportRecordView | None)
def latest_student_report(
    student_profile_id: int,
    x_session_token: str | None = Header(default=None),
) -> ReportRecordView | None:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    return container.report_service.latest(student_profile_id)


@router.post("/students/{student_profile_id}/chat/sessions", response_model=ChatSessionView)
def create_chat_session(
    student_profile_id: int,
    request: ChatSessionCreate,
    x_session_token: str | None = Header(default=None),
) -> ChatSessionView:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    try:
        return container.chat_service.create_session(student_profile_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/students/{student_profile_id}/chat/sessions", response_model=list[ChatSessionView])
def list_chat_sessions(
    student_profile_id: int,
    x_session_token: str | None = Header(default=None),
) -> list[ChatSessionView]:
    user = current_user(x_session_token)
    require_student_profile(student_profile_id, user)
    return container.chat_service.list_sessions(student_profile_id)


@router.get("/chat/sessions/{session_id}", response_model=list[ChatMessageView])
def session_history(session_id: int, x_session_token: str | None = Header(default=None)) -> list[ChatMessageView]:
    user = current_user(x_session_token)
    require_chat_session(session_id, user)
    return container.chat_service.session_history(session_id)


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatTurnResponse)
def send_chat_message(
    session_id: int,
    request: ChatMessageSend,
    x_session_token: str | None = Header(default=None),
) -> ChatTurnResponse:
    user = current_user(x_session_token)
    require_chat_session(session_id, user)
    require_topic(request.topic_id, user=user)
    try:
        return container.chat_service.send_message(session_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/diagnosis/evaluate", response_model=DiagnosisResponse)
def evaluate_diagnosis(request: DiagnosisRequest) -> DiagnosisResponse:
    require_topic(request.target_topic_id)
    require_mastery_topics(request.current_mastery)
    return container.diagnosis_service.evaluate(request)


@router.post("/practice/next", response_model=PracticeResponse)
def next_practice(request: PracticeRequest) -> PracticeResponse:
    require_topic(request.topic_id)
    require_mastery_topics(request.current_mastery)
    try:
        return container.practice_service.recommend_next_question(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/mistakes/analyze", response_model=MistakeAnalysisResponse)
def analyze_mistake(request: MistakeAnalysisRequest) -> MistakeAnalysisResponse:
    require_topic(request.topic_id)
    return container.mistake_service.analyze(request)


@router.post("/tutor/respond", response_model=TutorResponse)
def tutor_respond(request: TutorRequest) -> TutorResponse:
    require_topic(request.topic_id)
    require_mastery_topics(request.current_mastery)
    return container.tutor_service.respond(request)


@router.post("/reports/generate", response_model=StudyReportResponse)
def generate_report(request: ReportRequest) -> StudyReportResponse:
    require_topic(request.target_topic_id)
    require_mastery_topics(request.current_mastery)
    return container.report_service.generate(request)
