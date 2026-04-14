from __future__ import annotations

import numpy as np
from sqlalchemy import select

from app.core.database import KnowledgeChunkORM, KnowledgeDocumentORM, RagDocumentORM
from app.domain.models import RagDocument
from app.repositories.sql_repository import sql_repository
from app.services.dashscope_service import DashScopeEmbeddingService
from app.services.retrieval_service import HybridRetrievalService, RetrievalDocument


class RagService:
    def __init__(
        self,
        retrieval_service: HybridRetrievalService,
        dashscope_service: DashScopeEmbeddingService,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.dashscope_service = dashscope_service

    def retrieve(
        self,
        topic_id: str,
        query: str,
        limit: int = 3,
        user_id: int | None = None,
    ) -> list[RagDocument]:
        with sql_repository.session() as session:
            chunk_stmt = select(KnowledgeChunkORM).where(
                (KnowledgeChunkORM.topic_id == topic_id) | (KnowledgeChunkORM.topic_id.is_(None))
            )
            if user_id is not None:
                chunk_stmt = chunk_stmt.where(
                    (KnowledgeChunkORM.teacher_user_id == user_id)
                    | (KnowledgeChunkORM.teacher_user_id.is_(None))
                )
            chunks = session.execute(chunk_stmt).scalars().all()

            doc_stmt = select(KnowledgeDocumentORM)
            if user_id is not None:
                doc_stmt = doc_stmt.where(
                    (KnowledgeDocumentORM.teacher_user_id == user_id)
                    | (KnowledgeDocumentORM.teacher_user_id.is_(None))
                )
            knowledge_docs = {doc.id: doc for doc in session.execute(doc_stmt).scalars().all()}
            legacy_docs = session.execute(
                select(RagDocumentORM).where(
                    (RagDocumentORM.topic_id == topic_id) | (RagDocumentORM.topic_id.is_(None))
                )
            ).scalars().all()

        retrieval_docs = [
            RetrievalDocument(
                identifier=chunk.id,
                title=(knowledge_docs.get(chunk.document_id).title if knowledge_docs.get(chunk.document_id) else "知识文档"),
                content=chunk.content,
                topic_id=chunk.topic_id,
                doc_type=chunk.doc_type,
                source_name=chunk.source_name,
            )
            for chunk in chunks
        ] + [
            RetrievalDocument(
                identifier=doc.id,
                title=doc.title,
                content=doc.content,
                topic_id=doc.topic_id,
                doc_type="legacy",
                source_name="legacy_rag",
            )
            for doc in legacy_docs
        ]
        dense_scores = self._dense_scores(query, chunks)
        ranked = self.retrieval_service.rank(
            query=query,
            documents=retrieval_docs,
            topic_id=topic_id,
            preferred_doc_type=None,
            dense_scores=dense_scores,
            limit=limit,
        )
        rerank_scores = self._rerank_scores(query, ranked)
        if rerank_scores:
            ranked = self.retrieval_service.rank(
                query=query,
                documents=[
                    RetrievalDocument(
                        identifier=item.identifier,
                        title=item.title,
                        content=item.content,
                        topic_id=item.topic_id,
                        doc_type=item.doc_type,
                        source_name=item.source_name,
                    )
                    for item in ranked
                ],
                topic_id=topic_id,
                preferred_doc_type=None,
                dense_scores={item.identifier: dense_scores.get(item.identifier, 0.0) for item in ranked},
                rerank_scores=rerank_scores,
                limit=limit,
            )
        return [
            RagDocument(
                id=item.identifier,
                topic_id=item.topic_id,
                title=item.title,
                source_name=item.source_name or "",
                doc_type=item.doc_type or "",
                snippet=item.content[:120],
                score=item.final_score,
            )
            for item in ranked
        ]

    def _dense_scores(self, query: str, chunks: list[KnowledgeChunkORM]) -> dict[int, float]:
        if not self.dashscope_service.enabled:
            return {}
        vector_chunks = [chunk for chunk in chunks if chunk.embedding]
        if not vector_chunks:
            return {}
        try:
            query_embedding = self.dashscope_service.embed_texts([query], text_type="query")[0]
        except Exception:
            return {}
        query_vector = np.array(query_embedding, dtype=float)
        query_norm = np.linalg.norm(query_vector) or 1.0
        scores = {}
        for chunk in vector_chunks:
            doc_vector = np.array(chunk.embedding, dtype=float)
            doc_norm = np.linalg.norm(doc_vector) or 1.0
            score = float(np.dot(query_vector, doc_vector) / (query_norm * doc_norm))
            scores[chunk.id] = round(max(score, 0.0), 4)
        return scores

    def _rerank_scores(self, query: str, ranked_hits) -> dict[int, float]:
        if not self.dashscope_service.enabled or not ranked_hits:
            return {}
        contents = [item.content for item in ranked_hits[:10]]
        identifiers = [item.identifier for item in ranked_hits[:10]]
        try:
            raw_scores = self.dashscope_service.rerank(query=query, documents=contents, top_n=len(contents))
        except Exception:
            return {}
        if not raw_scores:
            return {}
        max_score = max(raw_scores) or 1.0
        return {
            identifier: round(score / max_score, 4)
            for identifier, score in zip(identifiers, raw_scores)
        }
