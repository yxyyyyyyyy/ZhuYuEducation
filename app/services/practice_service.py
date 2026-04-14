from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy import select

from app.core.database import PracticeRecordORM
from app.domain.models import DifficultyBand, PracticeRequest, PracticeResponse, Question
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.sql_repository import sql_repository


class PracticeService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def recommend_next_question(self, request: PracticeRequest) -> PracticeResponse:
        mastery = request.current_mastery.get(request.topic_id)
        mastery_value = mastery.mastery if mastery else 0.0
        band = self._select_band(mastery_value)
        target_difficulty = self._band_target(band)

        prerequisite_topic = self._find_weak_prerequisite(request.topic_id, request.current_mastery)
        if prerequisite_topic:
            prereq_mastery = request.current_mastery.get(prerequisite_topic)
            prereq_value = prereq_mastery.mastery if prereq_mastery else 0.0
            prereq_questions = self._get_approved_questions(prerequisite_topic)
            if prereq_questions:
                recent_ids = self._get_recent_question_ids(request.student_id, limit=10)
                candidates = [q for q in prereq_questions if q.id not in recent_ids]
                if not candidates:
                    candidates = prereq_questions
                selected = min(candidates, key=lambda item: self._selection_key(item, 0.35))
                reason = (
                    f"前置知识点「{self.repository.get_topic(prerequisite_topic).name}」掌握度仅 {prereq_value:.0%}，"
                    f"建议先巩固前置知识再学习当前知识点。"
                )
                return PracticeResponse(
                    question=selected,
                    recommended_band=DifficultyBand.foundation,
                    selection_reason=reason,
                )

        recent_ids = self._get_recent_question_ids(request.student_id, limit=10)
        spaced_ids = self._get_spaced_repetition_ids(request.student_id, request.topic_id)

        candidates = [
            question
            for question in self._get_approved_questions(request.topic_id)
            if question.id not in recent_ids
        ]
        if not candidates:
            candidates = self._get_approved_questions(request.topic_id)
        if not candidates:
            raise ValueError("no approved question found")

        if spaced_ids and request.topic_id:
            spaced_questions = [q for q in candidates if q.id in spaced_ids]
            if spaced_questions:
                selected = min(spaced_questions, key=lambda item: self._selection_key(item, target_difficulty))
                reason = (
                    f"根据间隔复习策略，这道题之前答错过，建议重新练习。"
                    f"当前掌握度 {mastery_value:.0%}，推荐 {band.value} 难度题目。"
                )
                return PracticeResponse(
                    question=selected,
                    recommended_band=band,
                    selection_reason=reason,
                )

        consecutive_correct = self._get_consecutive_correct(request.student_id, request.topic_id)
        if consecutive_correct >= 3:
            target_difficulty = min(target_difficulty + 0.15, 0.95)
            band = DifficultyBand.challenge
        elif consecutive_correct == 0 and mastery_value > 0:
            target_difficulty = max(target_difficulty - 0.15, 0.15)
            band = DifficultyBand.foundation

        selected = min(
            candidates,
            key=lambda item: self._selection_key(item, target_difficulty),
        )
        reason = (
            f"当前掌握度 {mastery_value:.0%}，推荐 {band.value} 难度题目，"
            f"让练习强度与当前能力接近。"
        )
        return PracticeResponse(
            question=selected,
            recommended_band=band,
            selection_reason=reason,
        )

    def _select_band(self, mastery_value: float) -> DifficultyBand:
        if mastery_value < 0.45:
            return DifficultyBand.foundation
        if mastery_value < 0.75:
            return DifficultyBand.standard
        return DifficultyBand.challenge

    def _band_target(self, band: DifficultyBand) -> float:
        mapping = {
            DifficultyBand.foundation: 0.35,
            DifficultyBand.standard: 0.6,
            DifficultyBand.challenge: 0.82,
        }
        return mapping[band]

    def _find_weak_prerequisite(self, topic_id: str, current_mastery: dict) -> str | None:
        try:
            topic = self.repository.get_topic(topic_id)
        except (KeyError, Exception):
            return None
        for prereq_id in topic.prerequisites:
            prereq_mastery = current_mastery.get(prereq_id)
            if not prereq_mastery or prereq_mastery.mastery < 0.45:
                return prereq_id
        return None

    def _get_recent_question_ids(self, student_id: str, limit: int = 10) -> set[str]:
        try:
            with sql_repository.session() as session:
                rows = session.execute(
                    select(PracticeRecordORM.question_external_id)
                    .where(
                        PracticeRecordORM.student_profile_id == int(student_id),
                        PracticeRecordORM.evaluation_status != "pending_review",
                    )
                    .order_by(PracticeRecordORM.created_at.desc())
                    .limit(limit)
                ).scalars().all()
                return set(rows)
        except Exception:
            return set()

    def _get_spaced_repetition_ids(self, student_id: str, topic_id: str) -> set[str]:
        try:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            with sql_repository.session() as session:
                wrong_rows = session.execute(
                    select(PracticeRecordORM.question_external_id)
                    .where(
                        PracticeRecordORM.student_profile_id == int(student_id),
                        PracticeRecordORM.topic_id == topic_id,
                        PracticeRecordORM.is_correct == 0,
                        PracticeRecordORM.evaluation_status != "pending_review",
                        PracticeRecordORM.created_at < cutoff,
                    )
                ).scalars().all()
                recent_correct = set(session.execute(
                    select(PracticeRecordORM.question_external_id)
                    .where(
                        PracticeRecordORM.student_profile_id == int(student_id),
                        PracticeRecordORM.topic_id == topic_id,
                        PracticeRecordORM.is_correct == 1,
                        PracticeRecordORM.evaluation_status != "pending_review",
                    )
                    .order_by(PracticeRecordORM.created_at.desc())
                    .limit(5)
                ).scalars().all())
                return set(wrong_rows) - recent_correct
        except Exception:
            return set()

    def _get_approved_questions(self, topic_id: str) -> list[Question]:
        topic_ids = [topic_id] + self.repository.descendant_topic_ids(topic_id)
        questions = {}
        for candidate_topic_id in topic_ids:
            questions.update({
                question.id: question for question in self.repository.list_questions_by_topic(candidate_topic_id)
            })
        try:
            from app.core.database import QuestionBankORM
            with sql_repository.session() as session:
                rows = session.execute(
                    select(QuestionBankORM).where(
                        QuestionBankORM.topic_id.in_(topic_ids),
                        QuestionBankORM.status == "approved",
                    )
                ).scalars().all()
                for row in rows:
                    if self._is_verification_question(row):
                        continue
                    questions[row.external_id] = self._question_from_db_row(row)
        except Exception:
            pass
        return list(questions.values())

    def _selection_key(self, question: Question, target_difficulty: float) -> tuple[int, float, str]:
        source_rank = 0 if question.id.startswith("q_") else 1
        return (source_rank, abs(question.difficulty - target_difficulty), question.id)

    def _is_verification_question(self, row) -> bool:
        external_id = row.external_id or ""
        stem = row.stem or ""
        tags = row.tags or []
        if external_id.startswith("verify_"):
            return True
        if any(str(tag).startswith("验证") or str(tag) == "复核验证" for tag in tags):
            return True
        return "测试" in stem and row.source in {"csv_import", "seed"}

    def _question_from_db_row(self, row) -> Question:
        from app.domain.models import QuestionOption, QuestionType as QT, ScorePoint
        options = [QuestionOption(**opt) for opt in (row.options or [])]
        score_points = [ScorePoint(**sp) for sp in (row.score_points or [])]
        try:
            qtype = QT(row.question_type)
        except ValueError:
            qtype = QT.blank
        return Question(
            id=row.external_id,
            topic_id=row.topic_id,
            stem=row.stem,
            difficulty=row.difficulty,
            answer=row.answer,
            explanation=row.explanation,
            question_type=qtype,
            options=options,
            blank_count=row.blank_count or 1,
            score_points=score_points,
            tags=row.tags or [],
        )

    def _get_consecutive_correct(self, student_id: str, topic_id: str) -> int:
        try:
            with sql_repository.session() as session:
                rows = session.execute(
                    select(PracticeRecordORM.is_correct)
                    .where(
                        PracticeRecordORM.student_profile_id == int(student_id),
                        PracticeRecordORM.topic_id == topic_id,
                        PracticeRecordORM.evaluation_status != "pending_review",
                    )
                    .order_by(PracticeRecordORM.created_at.desc())
                    .limit(5)
                ).scalars().all()
                count = 0
                for r in rows:
                    if r:
                        count += 1
                    else:
                        break
                return count
        except Exception:
            return 0
