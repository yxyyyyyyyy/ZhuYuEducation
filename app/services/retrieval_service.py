from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[\s，。；、,.!?：:（）()\[\]\-_/]+", text.lower()) if token]


@dataclass
class RetrievalDocument:
    identifier: int
    title: str
    content: str
    topic_id: str | None = None
    doc_type: str | None = None
    source_name: str | None = None


@dataclass
class RetrievalHit:
    identifier: int
    title: str
    content: str
    topic_id: str | None
    doc_type: str | None
    source_name: str | None
    vector_score: float
    lexical_score: float
    final_score: float
    dense_score: float = 0.0
    rerank_score: float = 0.0


class HybridRetrievalService:
    """Hybrid retrieval with dense-like TF-IDF vectors + lexical/rule reranking."""

    def rank(
        self,
        query: str,
        documents: Iterable[RetrievalDocument],
        topic_id: str | None = None,
        preferred_doc_type: str | None = None,
        dense_scores: dict[int, float] | None = None,
        rerank_scores: dict[int, float] | None = None,
        limit: int = 5,
    ) -> list[RetrievalHit]:
        return self.rank_with_strategy(
            strategy="hybrid",
            query=query,
            documents=documents,
            topic_id=topic_id,
            preferred_doc_type=preferred_doc_type,
            dense_scores=dense_scores,
            rerank_scores=rerank_scores,
            limit=limit,
        )

    def rank_with_strategy(
        self,
        strategy: str,
        query: str,
        documents: Iterable[RetrievalDocument],
        topic_id: str | None = None,
        preferred_doc_type: str | None = None,
        dense_scores: dict[int, float] | None = None,
        rerank_scores: dict[int, float] | None = None,
        limit: int = 5,
    ) -> list[RetrievalHit]:
        docs = list(documents)
        if not docs:
            return []

        corpus = [doc.content for doc in docs]
        word_vectorizer = TfidfVectorizer(ngram_range=(1, 2), lowercase=True)
        char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)

        word_matrix = word_vectorizer.fit_transform(corpus)
        char_matrix = char_vectorizer.fit_transform(corpus)
        query_word = word_vectorizer.transform([query])
        query_char = char_vectorizer.transform([query])

        word_scores = cosine_similarity(query_word, word_matrix).flatten()
        char_scores = cosine_similarity(query_char, char_matrix).flatten()
        query_tokens = set(_tokenize(query))
        query_lower = query.lower()

        hits: list[RetrievalHit] = []
        for index, doc in enumerate(docs):
            lexical_score = self._lexical_score(query_tokens, query_lower, doc)
            vector_score = float(0.65 * word_scores[index] + 0.35 * char_scores[index])
            dense_score = dense_scores.get(doc.identifier, 0.0) if dense_scores else 0.0
            rerank_score = rerank_scores.get(doc.identifier, 0.0) if rerank_scores else 0.0
            topic_boost = 0.12 if topic_id and doc.topic_id == topic_id else 0.0
            type_boost = 0.08 if preferred_doc_type and doc.doc_type == preferred_doc_type else 0.0
            title_boost = 0.04 if any(token in doc.title.lower() for token in query_tokens) else 0.0
            final_score = float(
                self._strategy_score(
                    strategy=strategy,
                    vector_score=vector_score,
                    lexical_score=lexical_score,
                    dense_score=dense_score,
                    rerank_score=rerank_score,
                    topic_boost=topic_boost,
                    type_boost=type_boost,
                    title_boost=title_boost,
                )
            )
            if final_score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    identifier=doc.identifier,
                    title=doc.title,
                    content=doc.content,
                    topic_id=doc.topic_id,
                    doc_type=doc.doc_type,
                    source_name=doc.source_name,
                    vector_score=round(vector_score, 4),
                    lexical_score=round(lexical_score, 4),
                    dense_score=round(dense_score, 4),
                    rerank_score=round(rerank_score, 4),
                    final_score=round(final_score, 4),
                )
            )

        hits.sort(key=lambda item: item.final_score, reverse=True)
        return hits[:limit]

    def _strategy_score(
        self,
        strategy: str,
        vector_score: float,
        lexical_score: float,
        dense_score: float,
        rerank_score: float,
        topic_boost: float,
        type_boost: float,
        title_boost: float,
    ) -> float:
        if strategy == "keyword":
            return 0.82 * lexical_score + 0.06 * vector_score + topic_boost + type_boost + title_boost
        if strategy == "dense":
            return 0.18 * lexical_score + 0.18 * vector_score + 0.42 * dense_score + topic_boost + type_boost + title_boost
        if strategy == "rerank":
            return (
                0.18 * lexical_score
                + 0.18 * vector_score
                + 0.2 * dense_score
                + 0.22 * rerank_score
                + topic_boost
                + type_boost
                + title_boost
            )
        return (
            0.36 * vector_score
            + 0.22 * lexical_score
            + 0.22 * dense_score
            + 0.12 * rerank_score
            + topic_boost
            + type_boost
            + title_boost
        )

    def _lexical_score(self, query_tokens: set[str], query_lower: str, doc: RetrievalDocument) -> float:
        if not query_tokens:
            return 0.0
        doc_tokens = set(_tokenize(f"{doc.title} {doc.content}"))
        overlap = len(query_tokens & doc_tokens) / max(len(query_tokens), 1)
        substring_bonus = 0.2 if query_lower[: min(len(query_lower), 8)] in doc.content.lower() else 0.0
        return round(overlap + substring_bonus, 4)
