from __future__ import annotations

from sqlalchemy import select

from app.core.database import MistakeRecordORM
from app.domain.models import (
    MistakeAnalysisRequest,
    MistakeAnalysisResponse,
    MistakeCategory,
    MistakeRecordView,
)
from app.repositories.sql_repository import sql_repository
from app.services.knowledge_graph_service import KnowledgeGraphService


class MistakeService:
    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self.graph_service = graph_service

    def analyze(self, request: MistakeAnalysisRequest) -> MistakeAnalysisResponse:
        answer = request.student_answer.strip()
        correct = request.correct_answer.strip()
        scratchpad = (request.scratchpad or "").strip()
        text = request.problem_text

        if not answer:
            category = MistakeCategory.incomplete_strategy
            confidence = 0.72
            explanation = "学生没有形成完整求解步骤，属于解题策略未成型。"
        elif any(token in text for token in ["至少", "最多", "一共", "分别"]) and not any(
            token in answer for token in ["至少", "最多", "分别", "因为"]
        ):
            category = MistakeCategory.misread_question
            confidence = 0.76
            explanation = "题目条件没有被完整使用，属于审题不充分。"
        elif any(char.isdigit() for char in answer) and any(char.isdigit() for char in correct):
            category = MistakeCategory.calculation_error
            confidence = 0.8
            explanation = "解题方向接近正确，但最终结果偏差更像计算过程失误。"
        else:
            category = MistakeCategory.concept_confusion
            confidence = 0.69
            explanation = "错误表现更接近知识点概念混淆，建议先回到定义和典型例题。"

        topic = self.graph_service.get_topic(request.topic_id)
        correction_advice = [
            f"回顾“{topic.name}”的核心定义和判定条件。",
            "把正确解法拆成 2 到 3 个固定步骤，再复做同类题。",
            "将本题加入错题本，明天进行一次间隔复习。",
        ]
        return MistakeAnalysisResponse(
            student_id=request.student_id,
            topic_id=request.topic_id,
            category=category,
            confidence=confidence,
            explanation=explanation,
            correction_advice=correction_advice,
            follow_up_topics=topic.prerequisites or [request.topic_id],
        )

    def save_record(
        self,
        student_profile_id: int,
        question_stem: str,
        result: MistakeAnalysisResponse,
        student_answer: str,
        correct_answer: str,
        question_id: str,
    ) -> MistakeRecordView:
        with sql_repository.session() as session:
            row = MistakeRecordORM(
                student_profile_id=student_profile_id,
                topic_id=result.topic_id,
                question_id=question_id,
                question_stem=question_stem,
                student_answer=student_answer,
                correct_answer=correct_answer,
                category=result.category.value,
                explanation=result.explanation,
                correction_advice=result.correction_advice,
            )
            session.add(row)
            session.flush()
            return self._view(row)

    def list_records(self, student_profile_id: int) -> list[MistakeRecordView]:
        with sql_repository.session() as session:
            rows = sql_repository.recent_mistakes(session, student_profile_id, limit=50)
            return [self._view(row) for row in rows]

    def _view(self, row: MistakeRecordORM) -> MistakeRecordView:
        return MistakeRecordView(
            id=row.id,
            created_at=row.created_at,
            question_stem=row.question_stem,
            topic_name=row.topic_id,
            student_answer=row.student_answer,
            correct_answer=row.correct_answer,
            category=MistakeCategory(row.category),
            explanation=row.explanation,
            correction_advice=row.correction_advice or [],
        )
