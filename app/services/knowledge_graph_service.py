from __future__ import annotations

from collections import deque
from typing import List

from sqlalchemy import select

from app.core.database import KnowledgeNodeORM
from app.domain.models import LearningStep, Topic, TopicMastery
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.sql_repository import sql_repository


class KnowledgeGraphService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def get_topic(self, topic_id: str) -> Topic:
        try:
            return self.repository.get_topic(topic_id)
        except KeyError:
            return self._fallback_topic(topic_id)

    def find_learning_path(
        self, target_topic_id: str, current_mastery: dict[str, TopicMastery]
    ) -> List[LearningStep]:
        ordered_topic_ids = self._collect_prerequisite_chain(target_topic_id)
        path: List[LearningStep] = []
        for topic_id in ordered_topic_ids:
            topic = self.get_topic(topic_id)
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
        if not self.repository.has_topic(target_topic_id):
            return [target_topic_id]

        visited = set()
        ordered: List[str] = []
        queue = deque([target_topic_id])

        while queue:
            topic_id = queue.popleft()
            if topic_id in visited:
                continue
            visited.add(topic_id)
            try:
                topic = self.repository.get_topic(topic_id)
            except KeyError:
                continue
            for prerequisite in topic.prerequisites:
                queue.append(prerequisite)

        def dfs(node_id: str) -> None:
            try:
                topic = self.repository.get_topic(node_id)
            except KeyError:
                if node_id not in ordered:
                    ordered.append(node_id)
                return
            for prerequisite in topic.prerequisites:
                if prerequisite not in ordered:
                    dfs(prerequisite)
            if node_id not in ordered:
                ordered.append(node_id)

        dfs(target_topic_id)
        return ordered

    def _fallback_topic(self, topic_id: str) -> Topic:
        with sql_repository.session() as session:
            row = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.is_deleted == 0,
                    (KnowledgeNodeORM.node_key == topic_id) | (KnowledgeNodeORM.topic_ref_id == topic_id),
                )
            ).scalars().first()
            if row:
                return Topic(
                    id=topic_id,
                    name=row.name,
                    subject=row.subject or "",
                    parent_id=row.parent_node_key,
                    level=2 if row.level >= 2 else 1,
                    grade_level=row.grade_level or "",
                    term="全年",
                    sort_order=row.sort_order,
                    prerequisites=[],
                    subtopics=[],
                    difficulty=0.5,
                    learning_objectives=[f"掌握{row.name}"],
                    common_mistakes=[f"{row.name}的概念边界不清"],
                    tutoring_tips=["先定义后应用，再做变式练习"],
                )
        return Topic(
            id=topic_id,
            name=topic_id,
            subject="",
            parent_id=None,
            level=2,
            grade_level="",
            term="全年",
            sort_order=0,
            prerequisites=[],
            subtopics=[],
            difficulty=0.5,
            learning_objectives=[f"掌握{topic_id}"],
            common_mistakes=[f"{topic_id}的概念边界不清"],
            tutoring_tips=["先定义后应用，再做变式练习"],
        )
