from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime
import io
import json
import re
import uuid

from sqlalchemy import delete, select

from app.core.database import PracticeRecordORM, QuestionBankORM, StudentMasteryORM, StudentProfileORM
from app.domain.models import (
    CsvImportResponse,
    PracticeCoachCard,
    PracticeCoachRequest,
    PracticeAnalyticsSummary,
    PracticeAnalyticsTopic,
    PracticeReviewResolveRequest,
    PracticeReviewView,
    PracticeSubmissionRequest,
    PracticeSubmissionResponse,
    Question,
    QuestionBankImportRequest,
    QuestionBankImportItem,
    QuestionBankItemView,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    QuestionOption,
    QuestionReviewRequest,
    QuestionReviewResponse,
    QuestionType,
    ScorePoint,
    ScorePointResult,
    SimilarQuestionView,
    WorkedStep,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.sql_repository import sql_repository


class QuestionBankService:
    def __init__(self, repository: KnowledgeRepository, llm_service=None) -> None:
        self.repository = repository
        self.llm_service = llm_service

    def import_questions(self, request: QuestionBankImportRequest) -> list[QuestionBankItemView]:
        imported = []
        with sql_repository.session() as session:
            for item in request.questions:
                row = session.execute(
                    select(QuestionBankORM).where(QuestionBankORM.external_id == item.id)
                ).scalars().first()
                if row is None:
                    row = QuestionBankORM(external_id=item.id)
                    session.add(row)
                row.topic_id = item.topic_id
                row.stem = item.stem
                row.difficulty = item.difficulty
                row.answer = item.answer
                row.explanation = item.explanation
                row.question_type = item.question_type.value
                row.options = [self._dump_model(option) for option in item.options]
                row.blank_count = item.blank_count
                row.score_points = [self._dump_model(point) for point in item.score_points]
                row.tags = item.tags
                session.flush()
                imported.append(self._view(row))
        return imported

    def list_questions(self) -> list[QuestionBankItemView]:
        with sql_repository.session() as session:
            rows = session.execute(select(QuestionBankORM).order_by(QuestionBankORM.created_at.desc())).scalars().all()
            return [self._view(row) for row in rows]

    def list_questions_by_topic(self, topic_id: str) -> list[Question]:
        with sql_repository.session() as session:
            rows = session.execute(
                select(QuestionBankORM).where(QuestionBankORM.topic_id == topic_id)
            ).scalars().all()
            return [self._question_from_row(row) for row in rows]

    def get_question(self, external_id: str) -> Question | None:
        with sql_repository.session() as session:
            row = session.execute(
                select(QuestionBankORM).where(QuestionBankORM.external_id == external_id)
            ).scalars().first()
            if not row:
                return None
            return self._question_from_row(row)

    def submit_practice(
        self,
        student_profile_id: int,
        recommended_band: str,
        request: PracticeSubmissionRequest,
    ) -> PracticeSubmissionResponse:
        question = self.get_question(request.question_id)
        if not question:
            raise ValueError("question not found")
        evaluation = self._evaluate_answer(question, request.student_answer, request.blank_answers)
        is_correct = evaluation["is_correct"]
        score = evaluation["score"]
        review_status = evaluation.get("review_status", "graded")
        mastery_applied = review_status == "graded"
        mastery_delta = self._mastery_delta_for_score(score) if mastery_applied else 0.0
        stored_answer = "，".join(request.blank_answers) if request.blank_answers is not None else request.student_answer

        record_id = None
        with sql_repository.session() as session:
            record = PracticeRecordORM(
                student_profile_id=student_profile_id,
                question_external_id=question.id,
                topic_id=question.topic_id,
                recommended_band=recommended_band,
                student_answer=stored_answer,
                is_correct=1 if is_correct else 0,
                score=score,
                earned_points=evaluation["earned_points"],
                total_points=evaluation["total_points"],
                evaluation_method=evaluation["method"],
                feedback=evaluation["feedback"],
                evaluation_status="pending_review" if review_status == "pending_review" else "graded",
                review_reason=evaluation.get("review_reason", ""),
                mastery_applied=1 if mastery_applied else 0,
                duration_seconds=request.duration_seconds,
            )
            session.add(record)
            session.flush()
            record_id = record.id
            if mastery_applied:
                self._apply_mastery_delta(session, student_profile_id, question.topic_id, is_correct, score)

        return PracticeSubmissionResponse(
            question_id=question.id,
            is_correct=is_correct,
            correct_answer=question.answer,
            explanation=question.explanation,
            mastery_delta=round(mastery_delta, 2),
            answer_type=question.question_type,
            earned_points=evaluation["earned_points"],
            total_points=evaluation["total_points"],
            score=round(score, 2),
            score_label=evaluation["score_label"],
            evaluation_method=evaluation["method"],
            feedback=evaluation["feedback"],
            breakdown=evaluation["breakdown"],
            review_status=review_status,
            review_record_id=record_id if review_status == "pending_review" else None,
            review_reason=evaluation.get("review_reason", ""),
        )

    def analytics_for_students(self, student_ids: list[int]) -> PracticeAnalyticsSummary:
        with sql_repository.session() as session:
            rows = session.execute(
                select(PracticeRecordORM).where(
                    PracticeRecordORM.student_profile_id.in_(student_ids),
                    PracticeRecordORM.evaluation_status != "pending_review",
                )
            ).scalars().all()

        total = len(rows)
        correct = sum(1 for row in rows if row.is_correct)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.topic_id].append(row)

        topics = []
        for topic_id, items in grouped.items():
            accuracy = sum(1 for item in items if item.is_correct) / len(items)
            avg_duration = sum(item.duration_seconds for item in items) / len(items) if items else 0
            topics.append(
                PracticeAnalyticsTopic(
                    topic_id=topic_id,
                    attempt_count=len(items),
                    accuracy=round(accuracy, 2),
                    avg_duration_seconds=round(avg_duration, 1),
                )
            )
        topics.sort(key=lambda item: item.attempt_count, reverse=True)
        return PracticeAnalyticsSummary(
            total_attempts=total,
            correct_attempts=correct,
            accuracy=round((correct / total), 2) if total else 0.0,
            topics=topics,
        )

    def list_practice_reviews(self, teacher_user_id: int, status: str = "pending") -> list[PracticeReviewView]:
        with sql_repository.session() as session:
            students = session.execute(
                select(StudentProfileORM).where(StudentProfileORM.user_id == teacher_user_id)
            ).scalars().all()
            student_map = {student.id: student.name for student in students}
            if not student_map:
                return []

            query = select(PracticeRecordORM).where(PracticeRecordORM.student_profile_id.in_(list(student_map.keys())))
            if status == "reviewed":
                query = query.where(PracticeRecordORM.evaluation_status == "reviewed")
            elif status == "all":
                query = query.where(PracticeRecordORM.evaluation_status.in_(["pending_review", "reviewed"]))
            else:
                query = query.where(PracticeRecordORM.evaluation_status == "pending_review")
            records = session.execute(query.order_by(PracticeRecordORM.created_at.desc())).scalars().all()
            question_ids = [record.question_external_id for record in records]
            questions = {
                row.external_id: row
                for row in session.execute(
                    select(QuestionBankORM).where(QuestionBankORM.external_id.in_(question_ids))
                ).scalars().all()
            } if question_ids else {}
            return [
                self._practice_review_view(record, student_map.get(record.student_profile_id, "学生"), questions.get(record.question_external_id))
                for record in records
            ]

    def resolve_practice_review(
        self,
        record_id: int,
        teacher_user_id: int,
        request: PracticeReviewResolveRequest,
    ) -> PracticeReviewView:
        with sql_repository.session() as session:
            record = session.execute(
                select(PracticeRecordORM).where(PracticeRecordORM.id == record_id)
            ).scalars().first()
            if not record:
                raise ValueError("practice review not found")
            student = session.execute(
                select(StudentProfileORM).where(
                    StudentProfileORM.id == record.student_profile_id,
                    StudentProfileORM.user_id == teacher_user_id,
                )
            ).scalars().first()
            if not student:
                raise ValueError("practice review not found")

            score = max(0.0, min(1.0, float(request.score)))
            total_points = record.total_points or 1.0
            record.score = score
            record.earned_points = round(score * total_points, 2)
            record.is_correct = 1 if request.is_correct else 0
            record.feedback = request.feedback or ("教师复核判定为正确。" if request.is_correct else "教师复核判定为需订正。")
            record.evaluation_method = "teacher_review"
            record.evaluation_status = "reviewed"
            record.review_reason = ""
            record.reviewed_at = datetime.utcnow()
            record.reviewed_by_user_id = teacher_user_id
            if not record.mastery_applied:
                self._apply_mastery_delta(session, record.student_profile_id, record.topic_id, bool(record.is_correct), score)
                record.mastery_applied = 1

            question = session.execute(
                select(QuestionBankORM).where(QuestionBankORM.external_id == record.question_external_id)
            ).scalars().first()
            session.flush()
            return self._practice_review_view(record, student.name, question)

    def _mastery_delta_for_score(self, score: float) -> float:
        return 0.05 if score >= 0.85 else (0.01 if score >= 0.55 else -0.03)

    def _apply_mastery_delta(
        self,
        session,
        student_profile_id: int,
        topic_id: str,
        is_correct: bool,
        score: float,
    ) -> None:
        mastery_delta = self._mastery_delta_for_score(score)
        mastery_row = session.execute(
            select(StudentMasteryORM).where(
                StudentMasteryORM.student_profile_id == student_profile_id,
                StudentMasteryORM.topic_id == topic_id,
            )
        ).scalars().first()
        if mastery_row:
            mastery_row.practice_count += 1
            if is_correct:
                mastery_row.correct_count += 1
            mastery_row.mastery = max(0.0, min(1.0, mastery_row.mastery + mastery_delta))

    def _practice_review_view(
        self,
        record: PracticeRecordORM,
        student_name: str,
        question: QuestionBankORM | None,
    ) -> PracticeReviewView:
        return PracticeReviewView(
            record_id=record.id,
            student_profile_id=record.student_profile_id,
            student_name=student_name,
            question_id=record.question_external_id,
            topic_id=record.topic_id,
            question_stem=question.stem if question else "题目已删除",
            correct_answer=question.answer if question else "",
            explanation=question.explanation if question else "",
            student_answer=record.student_answer,
            score=record.score or 0.0,
            is_correct=bool(record.is_correct),
            evaluation_method=record.evaluation_method or "pending_teacher_review",
            feedback=record.feedback or "",
            evaluation_status=record.evaluation_status or "pending_review",
            review_reason=record.review_reason or "",
            created_at=record.created_at,
            reviewed_at=record.reviewed_at,
        )

    def build_coach_card(self, request: PracticeCoachRequest) -> PracticeCoachCard:
        question = self.get_question(request.question_id)
        if not question:
            raise ValueError("question not found")
        topic = self.repository.get_topic(question.topic_id)
        mismatch = bool(
            request.student_answer
            and request.student_answer.strip().lower() != question.answer.strip().lower()
        )
        step_cards = self._build_step_cards(question, topic.name)
        if mismatch:
            step_cards.insert(
                1,
                WorkedStep(
                    title="先纠正当前误区",
                    content=(
                        f"你当前填写的是“{request.student_answer}”，和正确答案“{question.answer}”不一致。"
                        " 建议回到定义层面重新判断变量关系或公式含义。"
                    ),
                ),
            )

        misconception_alerts = list(dict.fromkeys((topic.common_mistakes or []) + (question.tags or [])))[:4]
        next_drills = [
            f"围绕 {topic.name} 再刷 2 道同类基础题，重点盯住同一类关键词。",
            f"把这题总结成一句规则：{question.explanation[:36]}..." if question.explanation else f"把 {topic.name} 的定义写成自己的话。",
            f"下一轮优先练习与 {topic.name} 同主题、难度接近 {question.difficulty:.2f} 的题。",
        ]
        return PracticeCoachCard(
            question_id=question.id,
            topic_id=question.topic_id,
            topic_name=topic.name,
            strategy_summary=(
                f"这道题适合按“识别考点 -> 套用规则 -> 结果复核”的三步来做，"
                f"核心是先把 {topic.name} 的定义和题干条件对上。"
            ),
            step_cards=step_cards,
            misconception_alerts=misconception_alerts,
            next_drills=next_drills,
            similar_questions=self.similar_questions(question.id),
        )

    def similar_questions(self, question_id: str, limit: int = 3) -> list[SimilarQuestionView]:
        question = self.get_question(question_id)
        if not question:
            return []
        candidates = [
            item
            for item in self.list_questions_by_topic(question.topic_id)
            if item.id != question.id
        ]
        scored = []
        base_tags = set(question.tags or [])
        base_tokens = self._tokenize(question.stem)
        for item in candidates:
            difficulty_gap = abs(item.difficulty - question.difficulty)
            tag_overlap = len(base_tags & set(item.tags or []))
            token_overlap = len(base_tokens & self._tokenize(item.stem))
            score = tag_overlap * 2.0 + token_overlap * 0.3 - difficulty_gap
            reason_parts = []
            if tag_overlap:
                reason_parts.append("同标签考点")
            if token_overlap:
                reason_parts.append("题干结构相近")
            if difficulty_gap <= 0.15:
                reason_parts.append("难度接近")
            scored.append(
                (
                    score,
                    SimilarQuestionView(
                        question_id=item.id,
                        topic_id=item.topic_id,
                        stem=item.stem,
                        difficulty=item.difficulty,
                        question_type=item.question_type,
                        recommendation_reason="，".join(reason_parts) or "同一知识点延伸练习",
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def _tokenize(self, text: str) -> set[str]:
        return {
            token
            for token in re.split(r"[\s，。；、,.!?：:（）()\[\]\-_/]+", text.lower())
            if token
        }

    def _evaluate_answer(self, question: Question, student_answer: str, blank_answers: list[str] | None = None) -> dict:
        correct_answer = question.answer
        explanation = question.explanation
        stem = question.stem
        normalized_student = self._normalize_text(student_answer)
        normalized_correct = self._normalize_text(correct_answer)
        normalized_blank_answers = self._normalize_blank_answers(blank_answers)
        if question.question_type == QuestionType.judgment:
            return self._evaluate_judgment(question, student_answer)

        if question.question_type == QuestionType.choice:
            return self._evaluate_choice(question, student_answer)

        if question.question_type == QuestionType.steps:
            return self._evaluate_rubric(question, student_answer, strict=False)

        if question.question_type == QuestionType.solution:
            llm_result = self._evaluate_with_llm(question, student_answer)
            if llm_result:
                return llm_result
            return self._pending_teacher_review(question, student_answer, "AI 判分不可用，解答题需要教师复核。")

        if normalized_student == normalized_correct:
            return {
                "is_correct": True,
                "score": 1.0,
                "earned_points": 1.0,
                "total_points": 1.0,
                "score_label": "1/1",
                "method": "exact",
                "feedback": "答案与参考答案一致。",
                "breakdown": [
                    ScorePointResult(
                        title="答案匹配",
                        points=1.0,
                        earned_points=1.0,
                        status="正确",
                        evidence="答案与参考答案完全一致",
                    )
                ],
            }

        blank_answer_count = len(normalized_blank_answers) if normalized_blank_answers is not None else 0
        if question.blank_count > 1 or blank_answer_count > 1:
            return self._evaluate_multi_blank(question, student_answer, normalized_blank_answers)

        keyword_match = self._evaluate_single_blank_keyword(question, student_answer)
        if keyword_match:
            return keyword_match

        if self._is_subjective(stem, correct_answer):
            llm_result = self._evaluate_with_llm(question, student_answer)
            if llm_result:
                return llm_result
            return self._pending_teacher_review(question, student_answer, "AI 判分不可用，简答题需要教师复核。")

        llm_result = self._evaluate_with_llm(question, student_answer)
        if llm_result:
            return llm_result
        return self._pending_teacher_review(question, student_answer, "规则判分未能可靠命中，已转交教师复核。")

    def _evaluate_choice(self, question: Question, student_answer: str) -> dict:
        normalized_student = self._normalize_text(student_answer)
        accepted = {self._normalize_text(question.answer)}
        for option in question.options:
            if self._normalize_text(option.key) == self._normalize_text(question.answer):
                accepted.add(self._normalize_text(option.content))
            if self._normalize_text(option.content) == self._normalize_text(question.answer):
                accepted.add(self._normalize_text(option.key))
        is_correct = normalized_student in accepted
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "earned_points": 1.0 if is_correct else 0.0,
            "total_points": 1.0,
            "score_label": "1/1" if is_correct else "0/1",
            "method": "choice",
            "feedback": "系统按选项答案精确匹配判分。",
            "breakdown": [
                ScorePointResult(
                    title="选项判断",
                    points=1.0,
                    earned_points=1.0 if is_correct else 0.0,
                    status="正确" if is_correct else "错误",
                    evidence=f"参考答案为 {question.answer}",
                )
            ],
        }

    def _evaluate_judgment(self, question: Question, student_answer: str) -> dict:
        normalized_student = self._normalize_judgment_answer(student_answer)
        normalized_correct = self._normalize_judgment_answer(question.answer)
        if normalized_correct is None:
            normalized_correct = self._normalize_text(question.answer)
        student_value = normalized_student if normalized_student is not None else self._normalize_text(student_answer)
        is_correct = student_value == normalized_correct
        display_answer = "正确" if normalized_correct is True else ("错误" if normalized_correct is False else question.answer)
        return {
            "is_correct": is_correct,
            "score": 1.0 if is_correct else 0.0,
            "earned_points": 1.0 if is_correct else 0.0,
            "total_points": 1.0,
            "score_label": "1/1" if is_correct else "0/1",
            "method": "judgment",
            "feedback": "系统按判断题同义表达判分，支持正确/错误、对/错、true/false 等写法。",
            "breakdown": [
                ScorePointResult(
                    title="判断结果",
                    points=1.0,
                    earned_points=1.0 if is_correct else 0.0,
                    status="正确" if is_correct else "错误",
                    evidence=f"参考判断为 {display_answer}",
                )
            ],
        }

    def _normalize_judgment_answer(self, value: str) -> bool | str | None:
        raw = (value or "").strip().lower()
        normalized = self._normalize_text(raw)
        normalized = normalized.replace(".", "").replace("。", "").replace("！", "").replace("!", "")
        true_values = {"正确", "对", "是", "true", "t", "yes", "y", "√", "✓", "1", "正确的", "对的"}
        false_values = {"错误", "错", "否", "false", "f", "no", "n", "×", "✗", "x", "0", "错误的", "错的", "不正确"}
        if normalized in true_values:
            return True
        if normalized in false_values:
            return False
        if "不正确" in normalized or "错误" in normalized:
            return False
        if normalized.endswith("是正确的") or normalized.endswith("正确"):
            return True
        if normalized.endswith("是错误的") or normalized.endswith("错误"):
            return False
        return None

    def _evaluate_multi_blank(
        self,
        question: Question,
        student_answer: str,
        blank_answers: list[str] | None = None,
    ) -> dict:
        correct_parts = self._split_correct_blank_answers(question)
        student_parts = blank_answers if blank_answers is not None else self._split_student_blank_answers(
            student_answer,
            question.blank_count,
        )
        breakdown = []
        hits = 0
        total = max(len(correct_parts), question.blank_count, 1)
        for index in range(total):
            correct_part = correct_parts[index] if index < len(correct_parts) else ""
            student_part = student_parts[index] if index < len(student_parts) else ""
            accepted_values = self._accepted_blank_values(question, index, correct_part)
            matched = self._blank_answer_matches(student_part, accepted_values)
            if matched:
                hits += 1
            title = question.score_points[index].title if index < len(question.score_points) else f"第 {index + 1} 空"
            breakdown.append(
                ScorePointResult(
                    title=title,
                    points=1.0,
                    earned_points=1.0 if matched else 0.0,
                    status="命中" if matched else "未命中",
                    evidence=correct_part or "请补全对应答案",
                )
            )
        score = hits / total
        return {
            "is_correct": score >= 0.99,
            "score": score,
            "earned_points": float(hits),
            "total_points": float(total),
            "score_label": f"{hits}/{total}",
            "method": "multi_blank",
            "feedback": "系统按多空填答逐项比对，并接受关键值简写。",
            "breakdown": breakdown,
        }

    def _evaluate_single_blank_keyword(self, question: Question, student_answer: str) -> dict | None:
        accepted_values = self._accepted_blank_values(question, 0, question.answer)
        if not self._blank_answer_matches(student_answer, accepted_values):
            return None
        if not self._single_blank_core_safe(question.answer, student_answer):
            return None
        return {
            "is_correct": True,
            "score": 1.0,
            "earned_points": 1.0,
            "total_points": 1.0,
            "score_label": "1/1",
            "method": "keyword_match",
            "feedback": "答案命中了参考答案的核心表达。",
            "breakdown": [
                ScorePointResult(
                    title="答案匹配",
                    points=1.0,
                    earned_points=1.0,
                    status="命中",
                    evidence=f"核心表达：{student_answer.strip()}",
                )
            ],
        }

    def _single_blank_core_safe(self, correct_answer: str, student_answer: str) -> bool:
        normalized_correct = self._normalize_text(correct_answer)
        normalized_student = self._normalize_text(student_answer)
        if not normalized_student:
            return False
        if re.search(r"\d", normalized_correct) and not re.search(r"\d", normalized_student):
            return False
        negative_markers = ["没有", "不能", "不是", "不", "无", "非"]
        if any(marker in correct_answer for marker in negative_markers) and not any(
            marker in student_answer for marker in negative_markers
        ):
            return False
        if self._answer_has_multiple_requirements(correct_answer) and normalized_correct not in normalized_student:
            return False
        if (
            normalized_student.isascii()
            and normalized_student.isalpha()
            and re.search(r"[a-zA-Z]", normalized_correct)
            and normalized_student != normalized_correct
        ):
            return False
        return len(normalized_student) >= 2 or re.search(r"\d", normalized_student) is not None

    def _answer_has_multiple_requirements(self, answer: str) -> bool:
        if "或" in answer:
            return False
        return bool(re.search(r"[，,；;、/]|和|与|以及|分别|至少", answer))

    def _normalize_blank_answers(self, blank_answers: list[str] | None) -> list[str] | None:
        if blank_answers is None:
            return None
        return [(answer or "").strip() for answer in blank_answers]

    def _split_correct_blank_answers(self, question: Question) -> list[str]:
        parts = [part.strip() for part in re.split(r"[，,；;、]", question.answer) if part.strip()]
        if len(parts) >= question.blank_count:
            return parts
        if question.score_points:
            inferred = []
            for point in question.score_points:
                if point.keywords:
                    inferred.append(point.keywords[0])
            if len(inferred) >= question.blank_count:
                return inferred
        return parts or [question.answer]

    def _split_student_blank_answers(self, student_answer: str, expected_count: int) -> list[str]:
        answer = student_answer.strip()
        if not answer:
            return []
        if re.search(r"[，,；;、\n]", answer):
            return [part.strip() for part in re.split(r"[，,；;、\n]", answer)]
        whitespace_parts = [part.strip() for part in answer.split() if part.strip()]
        if expected_count > 1 and 1 < len(whitespace_parts) <= expected_count:
            return whitespace_parts
        return [answer]

    def _accepted_blank_values(self, question: Question, index: int, correct_part: str) -> set[str]:
        accepted = {correct_part}
        if index < len(question.score_points):
            accepted.update(question.score_points[index].keywords)
        accepted.update(self._extract_core_values(correct_part))
        return {value for value in accepted if value and value.strip()}

    def _extract_core_values(self, text: str) -> set[str]:
        values = set()
        clean = text.strip()
        if not clean:
            return values
        for part in re.split(r"或|/|｜|\|", clean):
            part = part.strip(" （）()")
            if part:
                values.add(part)
        for match in re.findall(r"(?:是|为|=|＝)\s*([^，,；;、。()（）]+)", clean):
            if match.strip():
                values.add(match.strip())
        for number in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", clean):
            values.add(number)
        for equation in re.findall(r"[a-zA-Z]\s*[=＝]\s*[^，,；;、。()（）]+", clean):
            values.add(equation.strip())
        return values

    def _blank_answer_matches(self, student_part: str, accepted_values: set[str]) -> bool:
        normalized_student = self._normalize_text(student_part)
        if not normalized_student:
            return False
        for value in accepted_values:
            normalized_value = self._normalize_text(value)
            if not normalized_value:
                continue
            if normalized_student == normalized_value:
                return True
            if len(normalized_student) <= 8 and normalized_student in normalized_value:
                return True
            if len(normalized_value) <= 8 and normalized_value in normalized_student:
                return True
        return False

    def _evaluate_rubric(self, question: Question, student_answer: str, strict: bool) -> dict:
        score_points = question.score_points or self._infer_score_points(question.question_type, question.explanation, question.answer)
        breakdown = []
        earned_points = 0.0
        total_points = round(sum(point.points for point in score_points), 2) or 10.0
        student_tokens = self._tokenize(student_answer)
        normalized_answer = self._normalize_text(student_answer)
        for point in score_points:
            keywords = point.keywords or list(self._tokenize(point.title))
            matched_keywords = [keyword for keyword in keywords if self._normalize_text(keyword) in normalized_answer or self._normalize_text(keyword) in student_tokens]
            coverage = min(len(matched_keywords) / max(len(keywords), 1), 1.0)
            earned = point.points if coverage >= 0.99 else round(point.points * coverage, 2)
            if strict and coverage < 0.45:
                earned = 0.0
            earned_points += earned
            breakdown.append(
                ScorePointResult(
                    title=point.title,
                    points=point.points,
                    earned_points=earned,
                    status="已覆盖" if earned >= point.points * 0.8 else ("部分覆盖" if earned > 0 else "待补充"),
                    evidence="、".join(matched_keywords[:3]) if matched_keywords else "答案中尚未体现该得分点",
                )
            )
        score = round(earned_points / total_points, 4) if total_points else 0.0
        return {
            "is_correct": score >= (0.8 if strict else 0.7),
            "score": score,
            "earned_points": round(earned_points, 2),
            "total_points": total_points,
            "score_label": f"{round(earned_points, 1)}/{round(total_points, 1)}",
            "method": "rubric_steps" if question.question_type == QuestionType.steps else "rubric_solution",
            "feedback": "系统按得分点覆盖度给出学习型评分，适合看步骤完成度和订正方向。",
            "breakdown": breakdown,
        }

    def _pending_teacher_review(self, question: Question, student_answer: str, reason: str) -> dict:
        total_points = 10.0 if question.question_type in {QuestionType.solution, QuestionType.steps} else 1.0
        return {
            "is_correct": False,
            "score": 0.0,
            "earned_points": 0.0,
            "total_points": total_points,
            "score_label": "待复核",
            "method": "pending_teacher_review",
            "feedback": "这次答案已进入教师复核，不会暂时计入掌握度。",
            "breakdown": [
                ScorePointResult(
                    title="待教师复核",
                    points=total_points,
                    earned_points=0.0,
                    status="待复核",
                    evidence=reason,
                )
            ],
            "review_status": "pending_review",
            "review_reason": reason,
        }

    def _build_step_cards(self, question: Question, topic_name: str) -> list[WorkedStep]:
        if question.score_points:
            cards = []
            for point in question.score_points[:4]:
                cues = f" 关键词：{'、'.join(point.keywords[:3])}" if point.keywords else ""
                cards.append(WorkedStep(title=point.title, content=f"先完成这一得分点，再继续往下推。{cues}".strip()))
            if cards:
                return cards
        return [
            WorkedStep(
                title="先定位考点",
                content=(
                    f"这道题属于“{topic_name}”。先用题干里的关键词锁定考点："
                    f"{'、'.join(question.tags[:3]) or topic_name}"
                ),
            ),
            WorkedStep(
                title="再套用规则",
                content=(
                    question.explanation
                    or f"优先使用 {topic_name} 的核心规则，并把题干条件逐一对应到公式或定义。"
                ),
            ),
            WorkedStep(
                title="最后做复核",
                content=(
                    f"把你的结果和标准答案“{question.answer}”对照，检查单位、符号、定义是否一致。"
                ),
            ),
        ]

    def _question_from_row(self, row: QuestionBankORM) -> Question:
        question_type = self._resolve_question_type(row.question_type, row.stem, row.answer, row.score_points or [])
        return Question(
            id=row.external_id,
            topic_id=row.topic_id,
            stem=row.stem,
            difficulty=row.difficulty,
            answer=row.answer,
            explanation=row.explanation,
            question_type=question_type,
            options=row.options or self._infer_options(question_type, row.stem),
            blank_count=row.blank_count or self._infer_blank_count(row.answer),
            score_points=row.score_points or self._infer_score_points(question_type, row.explanation, row.answer),
            tags=row.tags or [],
        )

    def _resolve_question_type(self, raw_type: str | None, stem: str, answer: str, score_points: list) -> QuestionType:
        if raw_type:
            normalized = raw_type.strip().lower()
            type_aliases = {
                "选择": QuestionType.choice,
                "选择题": QuestionType.choice,
                "single_choice": QuestionType.choice,
                "multiple_choice": QuestionType.choice,
                "判断": QuestionType.judgment,
                "判断题": QuestionType.judgment,
                "true_false": QuestionType.judgment,
                "tf": QuestionType.judgment,
                "填空": QuestionType.blank,
                "填空题": QuestionType.blank,
                "blank_question": QuestionType.blank,
                "简答": QuestionType.solution,
                "简答题": QuestionType.solution,
                "解答": QuestionType.solution,
                "解答题": QuestionType.solution,
                "solution_question": QuestionType.solution,
                "分步": QuestionType.steps,
                "分步题": QuestionType.steps,
                "分步计算题": QuestionType.steps,
                "step": QuestionType.steps,
            }
            if normalized in type_aliases:
                return type_aliases[normalized]
            try:
                return QuestionType(normalized)
            except ValueError:
                pass
        if score_points:
            return QuestionType.steps
        if self._normalize_judgment_answer(answer) is not None or re.search(r"判断|正确|错误|对错|是否", stem):
            return QuestionType.judgment
        if re.search(r"[A-D][.．、]", stem):
            return QuestionType.choice
        if self._is_subjective(stem, answer):
            return QuestionType.solution
        if self._is_multi_part(answer):
            return QuestionType.blank
        return QuestionType.blank

    def _infer_options(self, question_type: QuestionType, stem: str) -> list[dict]:
        if question_type != QuestionType.choice:
            return []
        matches = re.findall(r"([A-D])[.．、]\s*([^A-D]+?)(?=(?:[A-D][.．、])|$)", stem)
        return [{"key": key, "content": content.strip()} for key, content in matches]

    def _infer_blank_count(self, answer: str) -> int:
        return max(len([part for part in re.split(r"[，,；;、]", answer) if part.strip()]), 1)

    def _infer_score_points(self, question_type: QuestionType, explanation: str, answer: str) -> list[dict]:
        if question_type not in {QuestionType.solution, QuestionType.steps}:
            return []
        source = explanation or answer
        sentences = [item.strip() for item in re.split(r"[。；;]", source) if item.strip()]
        points = []
        for index, sentence in enumerate(sentences[:3], start=1):
            points.append(
                {
                    "title": f"步骤 {index}",
                    "points": round(10 / max(len(sentences[:3]), 1), 1),
                    "keywords": list(self._tokenize(sentence))[:3],
                }
            )
        return points

    def _dump_model(self, item) -> dict:
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return item.dict()

    def _normalize_text(self, text: str) -> str:
        normalized = text.strip().lower()
        normalized = normalized.replace(" ", "").replace("，", ",").replace("。", "")
        normalized = normalized.replace("＝", "=").replace("：", ":")
        return normalized

    def _is_multi_part(self, answer: str) -> bool:
        return len(re.split(r"[，,；;、]", answer)) > 1

    def _is_subjective(self, stem: str, answer: str) -> bool:
        flags = ["说明", "证明", "分析", "解答", "为什么", "理由"]
        return any(flag in stem for flag in flags) or len(answer) >= 20

    def _view(self, row: QuestionBankORM) -> QuestionBankItemView:
        question = self._question_from_row(row)
        return QuestionBankItemView(
            id=row.id,
            external_id=row.external_id,
            topic_id=row.topic_id,
            stem=row.stem,
            difficulty=row.difficulty,
            answer=row.answer,
            explanation=row.explanation,
            question_type=question.question_type,
            options=question.options,
            blank_count=question.blank_count,
            score_points=question.score_points,
            tags=question.tags,
            status=row.status or "approved",
            source=row.source or "seed",
        )

    def generate_questions(self, request: QuestionGenerateRequest) -> QuestionGenerateResponse:
        topic = self.repository.get_topic(request.topic_id)
        raw_questions = self.llm_service.generate_questions(
            topic_name=topic.name,
            subject=topic.subject,
            subtopics=topic.subtopics,
            count=request.count,
            difficulty_min=request.difficulty_min,
            difficulty_max=request.difficulty_max,
            question_type=request.question_type.value,
        )
        if not raw_questions:
            return QuestionGenerateResponse(generated_count=0, questions=[])
        if isinstance(raw_questions, dict):
            raw_questions = [raw_questions]

        saved = []
        with sql_repository.session() as session:
            for item in raw_questions:
                external_id = f"ai_{request.topic_id}_{uuid.uuid4().hex[:8]}"
                options = item.get("options", [])
                score_points = item.get("score_points", [])
                blank_count = item.get("blank_count", 1)
                if options:
                    blank_count = 1
                row = QuestionBankORM(
                    external_id=external_id,
                    topic_id=request.topic_id,
                    stem=item.get("stem", ""),
                    difficulty=float(item.get("difficulty", 0.5)),
                    answer=item.get("answer", ""),
                    explanation=item.get("explanation", ""),
                    question_type=request.question_type.value,
                    options=options,
                    blank_count=blank_count,
                    score_points=score_points,
                    tags=item.get("tags", []),
                    status="pending",
                    source="ai_generated",
                )
                session.add(row)
                session.flush()
                saved.append(self._view(row))

        return QuestionGenerateResponse(generated_count=len(saved), questions=saved)

    def review_questions(self, request: QuestionReviewRequest) -> QuestionReviewResponse:
        new_status = "approved" if request.action == "approve" else "rejected"
        reviewed = []
        with sql_repository.session() as session:
            for qid in request.question_ids:
                row = session.execute(
                    select(QuestionBankORM).where(QuestionBankORM.id == qid)
                ).scalars().first()
                if row and row.status == "pending":
                    row.status = new_status
                    session.flush()
                    reviewed.append(self._view(row))
        return QuestionReviewResponse(reviewed_count=len(reviewed), questions=reviewed)

    def list_pending_questions(self) -> list[QuestionBankItemView]:
        with sql_repository.session() as session:
            rows = session.execute(
                select(QuestionBankORM).where(QuestionBankORM.status == "pending").order_by(QuestionBankORM.created_at.desc())
            ).scalars().all()
            return [self._view(row) for row in rows]

    def import_csv(self, csv_content: str) -> CsvImportResponse:
        cn_to_en = {
            "题目": "stem", "题干": "stem",
            "答案": "answer",
            "知识点ID": "topic_id", "知识点": "topic_id",
            "难度": "difficulty",
            "解析": "explanation",
            "题型": "question_type",
            "选项": "options",
            "空数": "blank_count", "填空数": "blank_count",
            "得分点": "score_points",
            "标签": "tags",
            "编号": "id",
        }
        reader = csv.DictReader(io.StringIO(csv_content))
        if reader.fieldnames:
            mapped = []
            for f in reader.fieldnames:
                field_name = f.strip().lstrip("\ufeff")
                mapped.append(cn_to_en.get(field_name, field_name))
            reader = csv.DictReader(io.StringIO(csv_content), fieldnames=mapped)
            next(reader)
        imported = []
        skipped = 0
        with sql_repository.session() as session:
            for row_data in reader:
                stem = row_data.get("stem", "").strip()
                answer = row_data.get("answer", "").strip()
                topic_id = row_data.get("topic_id", "").strip()
                if not stem or not answer or not topic_id:
                    skipped += 1
                    continue
                if not self.repository.has_topic(topic_id):
                    skipped += 1
                    continue
                external_id = row_data.get("id", f"csv_{uuid.uuid4().hex[:8]}").strip()
                existing = session.execute(
                    select(QuestionBankORM).where(QuestionBankORM.external_id == external_id)
                ).scalars().first()
                if existing:
                    skipped += 1
                    continue
                difficulty = float(row_data.get("difficulty", 0.5))
                explanation = row_data.get("explanation", "")
                raw_question_type = row_data.get("question_type", "blank").strip()
                question_type = self._resolve_question_type(raw_question_type, stem, answer, []).value
                tags_str = row_data.get("tags", "")
                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
                options = self._parse_csv_options(row_data.get("options", ""))
                if question_type == QuestionType.choice.value and not options:
                    options = self._infer_options(QuestionType.choice, stem)
                score_points = self._parse_csv_score_points(row_data.get("score_points", ""))
                blank_count = self._parse_csv_blank_count(row_data.get("blank_count", ""), answer, score_points)
                if question_type in {QuestionType.choice.value, QuestionType.judgment.value, QuestionType.solution.value}:
                    blank_count = 1
                row = QuestionBankORM(
                    external_id=external_id,
                    topic_id=topic_id,
                    stem=stem,
                    difficulty=difficulty,
                    answer=answer,
                    explanation=explanation,
                    question_type=question_type,
                    options=options,
                    blank_count=blank_count,
                    score_points=score_points,
                    tags=tags,
                    status="pending",
                    source="csv_import",
                )
                session.add(row)
                session.flush()
                imported.append(self._view(row))
        return CsvImportResponse(imported_count=len(imported), skipped_count=skipped, questions=imported)

    def _parse_csv_options(self, raw: str) -> list[dict]:
        raw = (raw or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    {"key": str(item.get("key", "")).strip(), "content": str(item.get("content", "")).strip()}
                    for item in parsed
                    if isinstance(item, dict) and item.get("key") and item.get("content")
                ]
        except json.JSONDecodeError:
            pass
        options = []
        for part in re.split(r"\|", raw):
            part = part.strip()
            if not part:
                continue
            match = re.match(r"^([A-Da-d])\s*[:：.．、]\s*(.+)$", part)
            if match:
                options.append({"key": match.group(1).upper(), "content": match.group(2).strip()})
        return options

    def _parse_csv_blank_count(self, raw: str, answer: str, score_points: list[dict]) -> int:
        raw = (raw or "").strip()
        if raw:
            try:
                return max(int(float(raw)), 1)
            except ValueError:
                pass
        if score_points:
            return max(len(score_points), 1)
        return self._infer_blank_count(answer)

    def _parse_csv_score_points(self, raw: str) -> list[dict]:
        raw = (raw or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    {
                        "title": str(item.get("title", f"得分点 {index + 1}")).strip(),
                        "points": float(item.get("points", 1.0)),
                        "keywords": [str(keyword).strip() for keyword in item.get("keywords", []) if str(keyword).strip()],
                    }
                    for index, item in enumerate(parsed)
                    if isinstance(item, dict)
                ]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        points = []
        for index, part in enumerate(re.split(r"\|", raw), start=1):
            part = part.strip()
            if not part:
                continue
            pieces = [piece.strip() for piece in re.split(r"[:：]", part) if piece.strip()]
            if not pieces:
                continue
            title = pieces[0]
            point_value = 1.0
            keyword_source = pieces[-1] if len(pieces) > 1 else pieces[0]
            if len(pieces) >= 3:
                try:
                    point_value = float(pieces[1])
                except ValueError:
                    point_value = 1.0
            keywords = [item.strip() for item in re.split(r"[,，/、;；]", keyword_source) if item.strip()]
            points.append({"title": title or f"得分点 {index}", "points": point_value, "keywords": keywords})
        return points

    def _evaluate_with_llm(self, question: Question, student_answer: str) -> dict:
        if not self.llm_service:
            return None
        result = self.llm_service.grade_answer(
            question_stem=question.stem,
            correct_answer=question.answer,
            student_answer=student_answer,
            explanation=question.explanation,
            allow_offline=False,
        )
        if not result:
            return None
        score = float(result.get("score", 0.0))
        is_correct = bool(result.get("is_correct", score >= 0.8))
        feedback = result.get("feedback", "")
        raw_breakdown = result.get("breakdown", [])
        breakdown = []
        for item in raw_breakdown:
            breakdown.append(
                ScorePointResult(
                    title=item.get("title", "评分项"),
                    points=float(item.get("points", 1.0)),
                    earned_points=float(item.get("earned_points", 0.0)),
                    status=item.get("status", ""),
                    evidence=item.get("evidence", ""),
                )
            )
        total_points = sum(item.points for item in breakdown) if breakdown else 1.0
        earned_points = sum(item.earned_points for item in breakdown) if breakdown else score
        return {
            "is_correct": is_correct,
            "score": score,
            "earned_points": round(earned_points, 2),
            "total_points": round(total_points, 2),
            "score_label": f"{round(earned_points, 1)}/{round(total_points, 1)}" if breakdown else f"{round(score * 100)}%",
            "method": "llm_semantic",
            "feedback": feedback or "AI 语义判分完成。",
            "breakdown": breakdown,
        }

    @staticmethod
    def _normalize_text_static(text: str) -> str:
        normalized = text.strip().lower()
        normalized = normalized.replace(" ", "").replace("，", ",").replace("。", "")
        normalized = normalized.replace("＝", "=").replace("：", ":")
        return normalized
