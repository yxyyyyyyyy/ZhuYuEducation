from __future__ import annotations

from statistics import mean

from app.domain.models import DiagnosisRequest, DiagnosisResponse
from app.services.knowledge_graph_service import KnowledgeGraphService


class DiagnosisService:
    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self.graph_service = graph_service

    def evaluate(self, request: DiagnosisRequest) -> DiagnosisResponse:
        path = self.graph_service.find_learning_path(
            request.target_topic_id, request.current_mastery
        )

        weakness_pairs = []
        strengths = []
        for topic_id, mastery in request.current_mastery.items():
            topic = self.graph_service.get_topic(topic_id)
            if mastery.mastery < 0.6:
                weakness_pairs.append((topic.name, mastery.mastery))
            elif mastery.mastery >= 0.8:
                strengths.append(topic.name)

        target_topic = self.graph_service.get_topic(request.target_topic_id)
        target_mastery = request.current_mastery.get(request.target_topic_id)
        target_value = target_mastery.mastery if target_mastery else 0.0

        prerequisite_scores = []
        for prerequisite in target_topic.prerequisites:
            prerequisite_mastery = request.current_mastery.get(prerequisite)
            prerequisite_scores.append(
                prerequisite_mastery.mastery if prerequisite_mastery else 0.0
            )

        readiness_score = mean(prerequisite_scores + [target_value]) if prerequisite_scores or target_value else 0.0
        weak_topics = [name for name, _ in sorted(weakness_pairs, key=lambda pair: pair[1])]

        summary = (
            f"目标知识点“{target_topic.name}”的准备度为 {readiness_score:.0%}。"
            f" 优先补强 {', '.join(weak_topics[:3]) if weak_topics else '暂无明显薄弱项'}，"
            f" 再进入目标知识点练习。"
        )

        return DiagnosisResponse(
            student_id=request.student_id,
            target_topic_id=request.target_topic_id,
            readiness_score=round(readiness_score, 2),
            weak_topics=weak_topics,
            strengths=strengths,
            learning_path=path,
            summary=summary,
        )
