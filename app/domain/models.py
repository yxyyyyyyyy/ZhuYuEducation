from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DifficultyBand(str, Enum):
    foundation = "foundation"
    standard = "standard"
    challenge = "challenge"


class QuestionType(str, Enum):
    choice = "choice"
    judgment = "judgment"
    blank = "blank"
    solution = "solution"
    steps = "steps"


KNOWLEDGE_TIERS = ["基础知识点", "核心知识点", "扩展知识点"]


class Topic(BaseModel):
    id: str
    name: str
    subject: str
    parent_id: Optional[str] = None
    level: int = 3
    grade_level: str = ""
    term: str = ""
    sort_order: int = 0
    prerequisites: List[str] = Field(default_factory=list)
    subtopics: List[str] = Field(default_factory=list)
    difficulty: float
    learning_objectives: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    tutoring_tips: List[str] = Field(default_factory=list)


class Question(BaseModel):
    id: str
    topic_id: str
    knowledge_l1_id: str = ""
    knowledge_l2_id: str = ""
    stem: str
    difficulty_level: int = Field(default=3, ge=1, le=5)
    difficulty: float
    answer: str
    explanation: str
    question_type: QuestionType = QuestionType.blank
    options: List[QuestionOption] = Field(default_factory=list)
    blank_count: int = Field(default=1, ge=1)
    score_points: List[ScorePoint] = Field(default_factory=list)
    knowledge_tiers: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class QuestionOption(BaseModel):
    key: str
    content: str


class ScorePoint(BaseModel):
    title: str
    points: float = Field(default=1.0, ge=0.0)
    keywords: List[str] = Field(default_factory=list)


class TopicMastery(BaseModel):
    topic_id: str
    mastery: float = Field(ge=0.0, le=1.0)
    practice_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    last_practiced_at: Optional[date] = None
    recent_errors: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    modules: List[str]


class ReadinessCheck(BaseModel):
    name: str
    status: str
    detail: Optional[str] = None


class ReadinessResponse(BaseModel):
    status: str
    checks: List[ReadinessCheck]


class UserSummary(BaseModel):
    id: int
    email: str
    full_name: str
    role: str = "student"
    school_id: Optional[int] = None


class RegisterRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=120)
    role: str = "student"
    school_id: Optional[int] = None


class StudentRegisterRequest(RegisterRequest):
    invite_code: str = Field(min_length=1, max_length=40)
    target_subject: str = Field(default="数学", min_length=1, max_length=80)
    target_topic_id: Optional[str] = Field(default=None, max_length=120)


class TeacherCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: str
    user: UserSummary


class StudentProfileSummary(BaseModel):
    id: int
    user_id: int
    school_id: Optional[int] = None
    classroom_id: Optional[int] = None
    teacher_user_id: Optional[int] = None
    textbook_id: Optional[int] = None
    name: str
    grade_level: str
    target_subject: str
    target_topic_id: str


class StudentProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grade_level: str = Field(min_length=1, max_length=80)
    target_subject: str = Field(min_length=1, max_length=80)
    target_topic_id: str = Field(min_length=1, max_length=120)
    school_id: Optional[int] = None
    classroom_id: Optional[int] = None
    teacher_user_id: Optional[int] = None
    textbook_id: Optional[int] = None


class StudentProfileDetail(StudentProfileSummary):
    mastery: Dict[str, TopicMastery]


class MasteryUpsertRequest(BaseModel):
    mastery: Dict[str, TopicMastery]


class LearningStep(BaseModel):
    topic_id: str
    topic_name: str
    reason: str
    recommended_action: str


class DiagnosisRequest(BaseModel):
    student_id: str
    target_topic_id: str
    current_mastery: Dict[str, TopicMastery]


class DiagnosisResponse(BaseModel):
    student_id: str
    target_topic_id: str
    readiness_score: float
    weak_topics: List[str]
    strengths: List[str]
    learning_path: List[LearningStep]
    summary: str


class DiagnosisRunRequest(BaseModel):
    target_topic_id: str = Field(min_length=1, max_length=120)


class PracticeRequest(BaseModel):
    student_id: str
    topic_id: str
    current_mastery: Dict[str, TopicMastery]
    recent_question_ids: List[str] = Field(default_factory=list)


class PracticeResponse(BaseModel):
    question: Question
    recommended_band: DifficultyBand
    selection_reason: str


class PracticeRunRequest(BaseModel):
    topic_id: str = Field(min_length=1, max_length=120)


class MistakeCategory(str, Enum):
    concept_confusion = "concept_confusion"
    calculation_error = "calculation_error"
    misread_question = "misread_question"
    incomplete_strategy = "incomplete_strategy"


class MistakeAnalysisRequest(BaseModel):
    student_id: str
    topic_id: str
    question_id: str
    student_answer: str
    correct_answer: str
    problem_text: str
    scratchpad: Optional[str] = None


class MistakeRunRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=120)
    student_answer: str = Field(min_length=1, max_length=4000)
    scratchpad: Optional[str] = None


class MistakeAnalysisResponse(BaseModel):
    student_id: str
    topic_id: str
    category: MistakeCategory
    confidence: float
    explanation: str
    correction_advice: List[str]
    follow_up_topics: List[str]


class MistakeRecordView(BaseModel):
    id: int
    created_at: datetime
    question_stem: str
    topic_name: str
    student_answer: str
    correct_answer: str
    category: MistakeCategory
    explanation: str
    correction_advice: List[str]


class TutorMode(str, Enum):
    socratic = "socratic"
    direct = "direct"
    example_based = "example_based"


class TutorRequest(BaseModel):
    student_id: str
    topic_id: str
    question: str
    current_mastery: Dict[str, TopicMastery]
    difficulty_signal: float = Field(ge=0.0, le=1.0, default=0.5)


class CitationEvidence(BaseModel):
    document_title: str
    source_name: str = ""
    doc_type: str = ""
    topic_id: Optional[str] = None
    snippet: str = ""
    score: float = 0.0


class TutorResponse(BaseModel):
    mode: TutorMode
    response: str
    next_step: str
    evidence: List[CitationEvidence] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)


class ChatSessionView(BaseModel):
    id: int
    student_profile_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageSend(BaseModel):
    topic_id: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)
    difficulty_signal: float = Field(ge=0.0, le=1.0, default=0.5)


class ChatMessageView(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    citations: List[CitationEvidence] = Field(default_factory=list)


class ChatTurnResponse(BaseModel):
    session: ChatSessionView
    assistant: ChatMessageView
    history: List[ChatMessageView]


class ReportRequest(BaseModel):
    student_id: str
    student_name: str
    target_topic_id: str
    current_mastery: Dict[str, TopicMastery]
    recent_mistakes: List[MistakeAnalysisResponse] = Field(default_factory=list)


class ReportRunRequest(BaseModel):
    target_topic_id: str


class ReviewTask(BaseModel):
    review_date: date
    topic_id: str
    activity: str


class StudyReportResponse(BaseModel):
    student_id: str
    overall_mastery: float
    strong_topics: List[str]
    weak_topics: List[str]
    diagnostic_summary: str
    next_actions: List[str]
    review_plan: List[ReviewTask]


class ReportRecordView(BaseModel):
    id: int
    created_at: datetime
    overall_mastery: float
    diagnostic_summary: str
    strong_topics: List[str]
    weak_topics: List[str]
    next_actions: List[str]
    review_plan: List[ReviewTask]


class StudentDashboard(BaseModel):
    profile: StudentProfileDetail
    latest_report: Optional[ReportRecordView] = None
    recent_mistakes: List[MistakeRecordView] = Field(default_factory=list)
    recent_sessions: List[ChatSessionView] = Field(default_factory=list)
    available_topics: List[Topic] = Field(default_factory=list)


class RagDocument(BaseModel):
    id: int
    topic_id: Optional[str] = None
    title: str
    source_name: str = ""
    doc_type: str = ""
    snippet: str
    score: float


class ClassroomCreate(BaseModel):
    school_id: Optional[int] = None
    textbook_id: Optional[int] = None
    name: str
    grade_level: str = ""
    description: str = ""


class ClassroomView(BaseModel):
    id: int
    school_id: Optional[int] = None
    school_name: str = ""
    teacher_user_id: int
    teacher_name: str = ""
    textbook_id: Optional[int] = None
    name: str
    grade_level: str = ""
    invite_code: str = ""
    description: str
    student_count: int


class SchoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    region: str = Field(default="", max_length=255)


class SchoolView(BaseModel):
    id: int
    name: str
    region: str = ""


class TeacherOption(BaseModel):
    id: int
    full_name: str
    email: str
    school_id: Optional[int] = None
    classroom_count: int = 0
    student_count: int = 0


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=12000)
    content_html: str = Field(default="", max_length=24000)
    is_pinned: bool = False


class AnnouncementView(BaseModel):
    id: int
    school_id: Optional[int] = None
    title: str
    content: str
    content_html: str = ""
    summary: str = ""
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class TeacherManageItem(TeacherOption):
    created_at: datetime | None = None


class TeacherImportResult(BaseModel):
    row_index: int
    full_name: str = ""
    email: str = ""
    imported: bool
    reason: str = ""
    teacher_id: Optional[int] = None


class TeacherImportResponse(BaseModel):
    imported_count: int
    skipped_count: int
    rows: List[TeacherImportResult] = Field(default_factory=list)


class AnnouncementDraftView(BaseModel):
    id: int
    title: str = ""
    content_html: str = ""
    updated_at: datetime


class TextbookView(BaseModel):
    id: int
    school_id: int
    grade_level: str = ""
    subject: str = ""
    name: str
    is_default: bool = False


class KnowledgeNodeView(BaseModel):
    id: int
    node_key: str
    parent_node_key: Optional[str] = None
    name: str
    level: int
    subject: str = ""
    grade_level: str = ""
    topic_ref_id: Optional[str] = None
    sort_order: int = 0
    question_count: int = 0
    children: List["KnowledgeNodeView"] = Field(default_factory=list)


KnowledgeNodeView.model_rebuild()


class AdminDashboard(BaseModel):
    admin_name: str
    school: SchoolView
    teacher_count: int
    classroom_count: int
    student_count: int
    question_count: int
    announcement_count: int


class KnowledgeTreeNode(BaseModel):
    id: str
    name: str
    subject: str
    level: int
    grade_level: str = ""
    mastery: float = 0.0
    question_count: int = 0
    children: List["KnowledgeTreeNode"] = Field(default_factory=list)


KnowledgeTreeNode.model_rebuild()


class TeacherStudentSummary(BaseModel):
    student_profile_id: int
    name: str
    grade_level: str
    target_topic_id: str
    overall_mastery: float
    latest_report_at: Optional[datetime] = None
    recent_mistake_count: int = 0
    recent_practice_accuracy: float = 0.0


class TeacherDashboard(BaseModel):
    teacher_name: str
    total_students: int
    active_students: int
    average_mastery: float
    average_accuracy: float
    students: List[TeacherStudentSummary]


class QuestionBankImportItem(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    knowledge_l1_id: str = Field(min_length=1, max_length=120)
    knowledge_l2_id: str = Field(min_length=1, max_length=120)
    stem: str = Field(min_length=1, max_length=4000)
    difficulty_level: int = Field(ge=1, le=5)
    answer: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(default="", max_length=8000)
    knowledge_tiers: List[str] = Field(min_length=1)
    topic_id: Optional[str] = Field(default=None, max_length=120)
    difficulty: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    question_type: QuestionType = QuestionType.blank
    options: List[QuestionOption] = Field(default_factory=list)
    blank_count: int = Field(default=1, ge=1)
    score_points: List[ScorePoint] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class QuestionBankImportRequest(BaseModel):
    questions: List[QuestionBankImportItem]


class QuestionBankItemView(BaseModel):
    id: int
    external_id: str
    knowledge_l1_id: str
    knowledge_l2_id: str
    topic_id: str
    stem: str
    difficulty_level: int = Field(ge=1, le=5)
    difficulty: float
    answer: str
    explanation: str
    knowledge_tiers: List[str] = Field(default_factory=list)
    question_type: QuestionType = QuestionType.blank
    options: List[QuestionOption] = Field(default_factory=list)
    blank_count: int = Field(default=1, ge=1)
    score_points: List[ScorePoint] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    status: str = "approved"
    source: str = "seed"


class QuestionGenerateRequest(BaseModel):
    knowledge_l2_id: str = Field(min_length=1, max_length=120)
    knowledge_l1_id: Optional[str] = Field(default=None, max_length=120)
    count: int = Field(default=5, ge=1, le=20)
    difficulty_level_min: int = Field(default=2, ge=1, le=5)
    difficulty_level_max: int = Field(default=4, ge=1, le=5)
    question_type: QuestionType = QuestionType.blank


class QuestionGenerateResponse(BaseModel):
    generated_count: int
    questions: List[QuestionBankItemView]


class QuestionReviewRequest(BaseModel):
    question_ids: List[int] = Field(min_length=1)
    action: str = Field(pattern="^(approve|reject)$")


class QuestionReviewResponse(BaseModel):
    reviewed_count: int
    questions: List[QuestionBankItemView]


class CsvImportResponse(BaseModel):
    imported_count: int
    skipped_count: int
    questions: List[QuestionBankItemView]


class PracticeSubmissionRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=120)
    student_answer: str = Field(min_length=1, max_length=4000)
    blank_answers: Optional[List[str]] = None
    duration_seconds: int = Field(default=0, ge=0, le=7200)


class ScorePointResult(BaseModel):
    title: str
    points: float = Field(default=0.0, ge=0.0)
    earned_points: float = Field(default=0.0, ge=0.0)
    status: str = ""
    evidence: str = ""


class PracticeSubmissionResponse(BaseModel):
    question_id: str
    is_correct: bool
    correct_answer: str
    explanation: str
    mastery_delta: float
    answer_type: QuestionType = QuestionType.blank
    earned_points: float = 0.0
    total_points: float = 0.0
    score: float = 0.0
    score_label: str = ""
    evaluation_method: str = "exact"
    feedback: str = ""
    breakdown: List[ScorePointResult] = Field(default_factory=list)
    review_status: str = "graded"
    review_record_id: Optional[int] = None
    review_reason: str = ""


class PracticeReviewView(BaseModel):
    record_id: int
    student_profile_id: int
    student_name: str
    question_id: str
    topic_id: str
    question_stem: str
    correct_answer: str
    explanation: str = ""
    student_answer: str
    score: float = 0.0
    is_correct: bool = False
    evaluation_method: str = "pending_teacher_review"
    feedback: str = ""
    evaluation_status: str = "pending_review"
    review_reason: str = ""
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class PracticeReviewResolveRequest(BaseModel):
    is_correct: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str = Field(default="", max_length=4000)


class PracticeCoachRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=120)
    student_answer: Optional[str] = Field(default=None, max_length=4000)


class WorkedStep(BaseModel):
    title: str
    content: str


class SimilarQuestionView(BaseModel):
    question_id: str
    topic_id: str
    stem: str
    difficulty: float
    question_type: QuestionType = QuestionType.blank
    recommendation_reason: str


class PracticeCoachCard(BaseModel):
    question_id: str
    topic_id: str
    topic_name: str
    strategy_summary: str
    step_cards: List[WorkedStep] = Field(default_factory=list)
    misconception_alerts: List[str] = Field(default_factory=list)
    next_drills: List[str] = Field(default_factory=list)
    similar_questions: List[SimilarQuestionView] = Field(default_factory=list)


class PracticeAnalyticsTopic(BaseModel):
    topic_id: str
    attempt_count: int
    accuracy: float
    avg_duration_seconds: float


class PracticeAnalyticsSummary(BaseModel):
    total_attempts: int
    correct_attempts: int
    accuracy: float
    topics: List[PracticeAnalyticsTopic]


class KnowledgeDocumentImportItem(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    topic_id: Optional[str] = None
    doc_type: str = Field(min_length=1, max_length=80)
    source_name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class KnowledgeDocumentImportRequest(BaseModel):
    documents: List[KnowledgeDocumentImportItem]


class KnowledgeChunkPreview(BaseModel):
    id: int
    chunk_index: int
    content: str
    embedding_ready: bool = False


class KnowledgeDocumentView(BaseModel):
    id: int
    title: str
    topic_id: Optional[str] = None
    doc_type: str
    source_name: str
    chunk_count: int
    embedding_ready_count: int = 0
    created_at: Optional[datetime] = None
    content_preview: str = ""
    chunk_previews: List[KnowledgeChunkPreview] = Field(default_factory=list)
    can_delete: bool = False


class ImportedDocumentFile(BaseModel):
    file_path: str
    title: str
    topic_id: Optional[str] = None
    doc_type: str
    imported: bool
    reason: str = ""


class KnowledgeDirectoryImportRequest(BaseModel):
    directory_path: str = Field(min_length=1)
    topic_id: Optional[str] = None
    doc_type: Optional[str] = None
    recursive: bool = True
    limit: int = Field(default=50, ge=1, le=500)


class KnowledgeDirectoryImportResponse(BaseModel):
    imported_count: int
    skipped_count: int
    files: List[ImportedDocumentFile] = Field(default_factory=list)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    topic_id: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=50)
    strategy: str = "hybrid"


class KnowledgeSearchHit(BaseModel):
    document_title: str
    doc_type: str
    source_name: str
    topic_id: Optional[str] = None
    snippet: str
    score: float
    lexical_score: Optional[float] = None
    vector_score: Optional[float] = None
    dense_score: Optional[float] = None
    rerank_score: Optional[float] = None


class RetrievalEvaluationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    topic_id: Optional[str] = None
    expected_topic_id: Optional[str] = None
    expected_doc_type: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=50)


class RetrievalStrategyEvaluation(BaseModel):
    strategy: str
    hit_at_1: bool
    hit_at_3: bool
    mrr: float
    hits: List[KnowledgeSearchHit] = Field(default_factory=list)


class RetrievalEvaluationResponse(BaseModel):
    query: str
    expected_topic_id: Optional[str] = None
    expected_doc_type: Optional[str] = None
    best_strategy: str
    strategies: List[RetrievalStrategyEvaluation] = Field(default_factory=list)


class RetrievalQualityStrategyMetric(BaseModel):
    strategy: str
    hit_at_1: float
    hit_at_3: float
    mrr: float


class RetrievalQualityCase(BaseModel):
    label: str
    query: str
    expected_topic_id: Optional[str] = None
    expected_doc_type: Optional[str] = None
    best_strategy: str
    strategies: List[RetrievalStrategyEvaluation] = Field(default_factory=list)


class RetrievalQualityDashboard(BaseModel):
    total_cases: int
    strategies: List[RetrievalQualityStrategyMetric] = Field(default_factory=list)
    cases: List[RetrievalQualityCase] = Field(default_factory=list)


class RetrievalCaseCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=1000)
    expected_topic_id: Optional[str] = None
    expected_doc_type: Optional[str] = None


class RetrievalCaseView(RetrievalCaseCreate):
    id: int
    created_at: datetime


class RetrievalCaseRunResponse(BaseModel):
    total_cases: int
    hit_at_1: float = 0.0
    hit_at_3: float = 0.0
    mrr: float = 0.0
    cases: List[RetrievalQualityCase] = Field(default_factory=list)
