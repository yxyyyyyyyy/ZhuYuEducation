from __future__ import annotations

from collections import deque
from typing import List

from app.domain.models import LearningStep, Topic, TopicMastery
from app.repositories.knowledge_repository import KnowledgeRepository


class KnowledgeGraphService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def get_topic(self, topic_id: str) -> Topic:
        return self.repository.get_topic(topic_id)

    def find_learning_path(
        self, target_topic_id: str, current_mastery: dict[str, TopicMastery]
    ) -> List[LearningStep]:
        ordered_topic_ids = self._collect_prerequisite_chain(target_topic_id)
        path: List[LearningStep] = []
        for topic_id in ordered_topic_ids:
            topic = self.repository.get_topic(topic_id)
            mastery = current_mastery.get(topic_id)
            mastery_value = mastery.mastery if mastery else 0.0
            if mastery_value >= 0.75 and topic_id != target_topic_id:
                continue

            reason = (
                "目标知识点本身需要巩固"
                if topic_id == target_topic_id
                else f"先修掌握度仅为 {mastery_value:.0%}"
            )
            action = (
                "先完成概念讲解与两道基础题"
                if mastery_value < 0.4
                else "完成一组针对性练习并复盘错题"
            )
            path.append(
                LearningStep(
                    topic_id=topic.id,
                    topic_name=topic.name,
                    reason=reason,
                    recommended_action=action,
                )
            )
        return path

    def _collect_prerequisite_chain(self, target_topic_id: str) -> List[str]:
        visited = set()
        ordered: List[str] = []
        queue = deque([target_topic_id])

        while queue:
            topic_id = queue.popleft()
            if topic_id in visited:
                continue
            visited.add(topic_id)
            topic = self.repository.get_topic(topic_id)
            for prerequisite in topic.prerequisites:
                queue.append(prerequisite)

        def dfs(node_id: str) -> None:
            topic = self.repository.get_topic(node_id)
            for prerequisite in topic.prerequisites:
                if prerequisite not in ordered:
                    dfs(prerequisite)
            if node_id not in ordered:
                ordered.append(node_id)

        dfs(target_topic_id)
        return ordered
