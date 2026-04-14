from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.database import ChatMessageORM, ChatSessionORM, StudentProfileORM
from app.domain.models import (
    ChatMessageSend,
    ChatMessageView,
    ChatSessionCreate,
    ChatSessionView,
    ChatTurnResponse,
    CitationEvidence,
    TutorMode,
)
from app.repositories.sql_repository import sql_repository
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.llm_service import LLMService
from app.services.rag_service import RagService


class ChatService:
    def __init__(
        self,
        graph_service: KnowledgeGraphService,
        rag_service: RagService,
        llm_service: LLMService,
    ) -> None:
        self.graph_service = graph_service
        self.rag_service = rag_service
        self.llm_service = llm_service

    def create_session(self, student_profile_id: int, request: ChatSessionCreate) -> ChatSessionView:
        with sql_repository.session() as session:
            profile = session.execute(
                select(StudentProfileORM).where(StudentProfileORM.id == student_profile_id)
            ).scalars().first()
            if not profile:
                raise ValueError("student profile not found")
            title = request.title or f"{profile.name} 的新对话"
            now = datetime.utcnow()
            chat = ChatSessionORM(
                student_profile_id=student_profile_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
            session.add(chat)
            session.flush()
            return ChatSessionView(
                id=chat.id,
                student_profile_id=chat.student_profile_id,
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )

    def list_sessions(self, student_profile_id: int) -> list[ChatSessionView]:
        with sql_repository.session() as session:
            sessions = sql_repository.recent_sessions(session, student_profile_id, limit=20)
            return [self._session_view(item) for item in sessions]

    def user_can_access_session(self, session_id: int, user_id: int) -> bool:
        with sql_repository.session() as session:
            row = session.execute(
                select(ChatSessionORM.id)
                .join(StudentProfileORM, ChatSessionORM.student_profile_id == StudentProfileORM.id)
                .where(ChatSessionORM.id == session_id, StudentProfileORM.user_id == user_id)
            ).scalars().first()
            return row is not None

    def session_history(self, session_id: int) -> list[ChatMessageView]:
        with sql_repository.session() as session:
            rows = session.execute(
                select(ChatMessageORM).where(ChatMessageORM.session_id == session_id).order_by(ChatMessageORM.created_at)
            ).scalars().all()
            return [self._message_view(item) for item in rows]

    def send_message(self, session_id: int, request: ChatMessageSend) -> ChatTurnResponse:
        topic = self.graph_service.get_topic(request.topic_id)
        mode = TutorMode.example_based if request.difficulty_signal > 0.75 else TutorMode.socratic
        fallback_text = (
            f"你可以先回到“{topic.name}”的核心目标：{topic.learning_objectives[0]}。"
            f" 常见误区是：{topic.common_mistakes[0]}。"
        )
        with sql_repository.session() as session:
            owner_id = session.execute(
                select(StudentProfileORM.user_id)
                .join(ChatSessionORM, ChatSessionORM.student_profile_id == StudentProfileORM.id)
                .where(ChatSessionORM.id == session_id)
            ).scalars().first()
        if owner_id is None:
            raise ValueError("chat session not found")

        evidence_docs = self.rag_service.retrieve(request.topic_id, request.content, limit=3, user_id=owner_id)
        assistant_text = self.llm_service.generate_tutor_reply(
            topic_name=topic.name,
            mode=mode,
            user_message=request.content,
            evidence=evidence_docs,
            fallback_text=fallback_text,
        )

        with sql_repository.session() as session:
            chat = session.execute(select(ChatSessionORM).where(ChatSessionORM.id == session_id)).scalars().first()
            if not chat:
                raise ValueError("chat session not found")
            user_message = ChatMessageORM(session_id=session_id, role="user", content=request.content, citations=[])
            session.add(user_message)
            assistant_message = ChatMessageORM(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
                citations=[self._citation_payload(doc) for doc in evidence_docs],
            )
            session.add(assistant_message)
            chat.updated_at = datetime.utcnow()
            session.flush()

            history = session.execute(
                select(ChatMessageORM).where(ChatMessageORM.session_id == session_id).order_by(ChatMessageORM.created_at)
            ).scalars().all()

            return ChatTurnResponse(
                session=self._session_view(chat),
                assistant=self._message_view(assistant_message),
                history=[self._message_view(item) for item in history],
            )

    def _session_view(self, row: ChatSessionORM) -> ChatSessionView:
        return ChatSessionView(
            id=row.id,
            student_profile_id=row.student_profile_id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _message_view(self, row: ChatMessageORM) -> ChatMessageView:
        return ChatMessageView(
            id=row.id,
            role=row.role,
            content=row.content,
            created_at=row.created_at,
            citations=[self._citation_view(item) for item in (row.citations or [])],
        )

    def _citation_payload(self, doc) -> dict:
        return {
            "document_title": doc.title,
            "source_name": doc.source_name,
            "doc_type": doc.doc_type,
            "topic_id": doc.topic_id,
            "snippet": doc.snippet,
            "score": round(doc.score, 4),
        }

    def _citation_view(self, item) -> CitationEvidence:
        if isinstance(item, str):
            return CitationEvidence(document_title=item)
        return CitationEvidence(
            document_title=item.get("document_title") or item.get("title") or "引用资料",
            source_name=item.get("source_name", ""),
            doc_type=item.get("doc_type", ""),
            topic_id=item.get("topic_id"),
            snippet=item.get("snippet", ""),
            score=float(item.get("score", 0.0) or 0.0),
        )
