from __future__ import annotations

import re
import secrets
from datetime import datetime

from sqlalchemy import func, select

from app.core.database import ClassroomORM, KnowledgeNodeORM, QuestionBankORM, StudentProfileORM, TextbookORM
from app.domain.models import KnowledgeNodeView, TextbookView, Topic
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.sql_repository import sql_repository


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (text or "").strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or "node"


class KnowledgeConfigService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def list_textbooks(self, school_id: int) -> list[TextbookView]:
        self.ensure_seeded(school_id)
        with sql_repository.session() as session:
            rows = session.execute(
                select(TextbookORM)
                .where(TextbookORM.school_id == school_id)
                .order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().all()
            return [
                TextbookView(id=row.id, school_id=row.school_id, name=row.name, is_default=bool(row.is_default))
                for row in rows
            ]

    def create_textbook(self, school_id: int, name: str, set_default: bool = False) -> TextbookView:
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ValueError("教材名称不能为空")
        with sql_repository.session() as session:
            existing = session.execute(
                select(TextbookORM).where(
                    TextbookORM.school_id == school_id,
                    TextbookORM.name == normalized_name,
                )
            ).scalars().first()
            if existing:
                if set_default:
                    self._set_default_in_session(session, school_id, existing.id)
                textbook_id = existing.id
            else:
                row = TextbookORM(
                    school_id=school_id,
                    name=normalized_name,
                    is_default=0,
                )
                session.add(row)
                session.flush()
                textbook_id = row.id
                if set_default or not session.execute(
                    select(TextbookORM.id).where(TextbookORM.school_id == school_id, TextbookORM.is_default == 1)
                ).scalars().first():
                    self._set_default_in_session(session, school_id, textbook_id)
        self.seed_textbook_nodes(school_id, textbook_id)
        return next(item for item in self.list_textbooks(school_id) if item.id == textbook_id)

    def get_default_textbook_id(self, school_id: int) -> int:
        self.ensure_seeded(school_id)
        with sql_repository.session() as session:
            row = session.execute(
                select(TextbookORM).where(TextbookORM.school_id == school_id).order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().first()
            if not row:
                raise ValueError("未找到教材")
            return row.id

    def list_topics_for_school(self, school_id: int, textbook_id: int | None = None) -> list[Topic]:
        textbook_id = textbook_id or self.get_default_textbook_id(school_id)
        nodes = self._list_nodes(school_id, textbook_id)
        if not nodes:
            self.seed_textbook_nodes(school_id, textbook_id)
            nodes = self._list_nodes(school_id, textbook_id)
        if not nodes:
            return self.repository.list_topics()

        by_key = {item.node_key: item for item in nodes}
        repository_map = {topic.id: topic for topic in self.repository.list_topics()}
        topics: list[Topic] = []
        for node in sorted(nodes, key=lambda item: (item.sort_order, item.node_key)):
            topic_id = node.topic_ref_id if (node.level == 3 and node.topic_ref_id) else node.node_key
            if node.level == 3 and not node.topic_ref_id:
                continue
            repo_topic = repository_map.get(node.topic_ref_id or "")
            topics.append(
                Topic(
                    id=topic_id,
                    name=node.name,
                    subject=node.subject or (by_key.get(node.parent_node_key).subject if node.parent_node_key and by_key.get(node.parent_node_key) else ""),
                    parent_id=node.parent_node_key,
                    level=node.level,
                    grade_level=node.grade_level,
                    term=repo_topic.term if repo_topic else "",
                    sort_order=node.sort_order,
                    prerequisites=repo_topic.prerequisites if repo_topic else [],
                    subtopics=repo_topic.subtopics if repo_topic else [],
                    difficulty=repo_topic.difficulty if repo_topic else 0.5,
                    learning_objectives=repo_topic.learning_objectives if repo_topic else [f"掌握{node.name}"],
                    common_mistakes=repo_topic.common_mistakes if repo_topic else [],
                    tutoring_tips=repo_topic.tutoring_tips if repo_topic else [],
                )
            )
        return topics

    def has_topic_for_school(self, school_id: int, topic_id: str, textbook_id: int | None = None) -> bool:
        return any(item.id == topic_id for item in self.list_topics_for_school(school_id, textbook_id))

    def get_topic_for_school(self, school_id: int, topic_id: str, textbook_id: int | None = None) -> Topic | None:
        for topic in self.list_topics_for_school(school_id, textbook_id):
            if topic.id == topic_id:
                return topic
        return None

    def list_tree(self, school_id: int, textbook_id: int | None = None) -> list[KnowledgeNodeView]:
        textbook_id = textbook_id or self.get_default_textbook_id(school_id)
        nodes = self._list_nodes(school_id, textbook_id)
        if not nodes:
            self.seed_textbook_nodes(school_id, textbook_id)
            nodes = self._list_nodes(school_id, textbook_id)
        question_count_by_topic = self._question_count_by_topic(nodes)
        children: dict[str, list[KnowledgeNodeView]] = {}
        views: dict[str, KnowledgeNodeView] = {}
        for node in nodes:
            question_count = question_count_by_topic.get(node.topic_ref_id or "", 0) if node.level == 3 else 0
            views[node.node_key] = KnowledgeNodeView(
                id=node.id,
                node_key=node.node_key,
                parent_node_key=node.parent_node_key,
                name=node.name,
                level=node.level,
                subject=node.subject or "",
                grade_level=node.grade_level or "",
                topic_ref_id=node.topic_ref_id,
                sort_order=node.sort_order,
                question_count=question_count,
                children=[],
            )
        for node in nodes:
            view = views[node.node_key]
            if node.parent_node_key and node.parent_node_key in views:
                children.setdefault(node.parent_node_key, []).append(view)
            else:
                children.setdefault("__root__", []).append(view)

        def attach(item: KnowledgeNodeView) -> KnowledgeNodeView:
            node_children = sorted(children.get(item.node_key, []), key=lambda child: (child.sort_order, child.node_key))
            item.children = [attach(child) for child in node_children]
            if item.children:
                item.question_count = sum(child.question_count for child in item.children)
            return item

        return [attach(item) for item in sorted(children.get("__root__", []), key=lambda child: (child.sort_order, child.node_key))]

    def create_node(
        self,
        school_id: int,
        textbook_id: int,
        name: str,
        level: int,
        parent_node_key: str | None = None,
        topic_ref_id: str | None = None,
        subject: str = "",
        grade_level: str = "",
    ) -> KnowledgeNodeView:
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ValueError("知识点名称不能为空")
        if level not in {1, 2, 3}:
            raise ValueError("知识点层级必须为 1/2/3")
        now = datetime.utcnow()
        with sql_repository.session() as session:
            parent = None
            if level > 1:
                if not parent_node_key:
                    raise ValueError("二级或三级知识点必须选择父节点")
                parent = session.execute(
                    select(KnowledgeNodeORM).where(
                        KnowledgeNodeORM.school_id == school_id,
                        KnowledgeNodeORM.textbook_id == textbook_id,
                        KnowledgeNodeORM.node_key == parent_node_key,
                        KnowledgeNodeORM.is_deleted == 0,
                    )
                ).scalars().first()
                if not parent:
                    raise ValueError("父节点不存在")
                if parent.level != level - 1:
                    raise ValueError("父节点层级不匹配")
            if level == 3 and not topic_ref_id:
                raise ValueError("三级知识点必须关联题库知识点")
            node_key = self._new_node_key(level, normalized_name, topic_ref_id)
            existing = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.node_key == node_key,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().first()
            if existing:
                if level == 3:
                    raise ValueError("同名知识点已存在，请修改名称")
                node_key = f"{node_key}_{secrets.token_hex(2)}"
            if level == 3 and topic_ref_id:
                duplicate_topic = session.execute(
                    select(KnowledgeNodeORM).where(
                        KnowledgeNodeORM.school_id == school_id,
                        KnowledgeNodeORM.textbook_id == textbook_id,
                        KnowledgeNodeORM.level == 3,
                        KnowledgeNodeORM.topic_ref_id == topic_ref_id,
                        KnowledgeNodeORM.is_deleted == 0,
                    )
                ).scalars().first()
                if duplicate_topic:
                    raise ValueError("该题库知识点已被当前教材绑定")
            max_sort = session.scalar(
                select(func.max(KnowledgeNodeORM.sort_order)).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.parent_node_key == parent_node_key,
                    KnowledgeNodeORM.level == level,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ) or 0
            row = KnowledgeNodeORM(
                school_id=school_id,
                textbook_id=textbook_id,
                node_key=node_key,
                parent_node_key=parent_node_key,
                name=normalized_name,
                level=level,
                subject=subject or (parent.subject if parent else normalized_name if level == 1 else ""),
                grade_level=grade_level or (parent.grade_level if parent else ""),
                topic_ref_id=topic_ref_id or None,
                sort_order=max_sort + 10,
                is_deleted=0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        flat = self._flatten_tree(self.list_tree(school_id, textbook_id))
        return next(item for item in flat if item.node_key == node_key)

    def update_node(
        self,
        school_id: int,
        textbook_id: int,
        node_key: str,
        name: str | None = None,
        topic_ref_id: str | None = None,
    ) -> KnowledgeNodeView:
        now = datetime.utcnow()
        with sql_repository.session() as session:
            row = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.node_key == node_key,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().first()
            if not row:
                raise ValueError("知识点不存在")
            if name is not None and name.strip():
                row.name = name.strip()
            if row.level == 3 and topic_ref_id:
                duplicate_topic = session.execute(
                    select(KnowledgeNodeORM).where(
                        KnowledgeNodeORM.school_id == school_id,
                        KnowledgeNodeORM.textbook_id == textbook_id,
                        KnowledgeNodeORM.level == 3,
                        KnowledgeNodeORM.topic_ref_id == topic_ref_id,
                        KnowledgeNodeORM.node_key != node_key,
                        KnowledgeNodeORM.is_deleted == 0,
                    )
                ).scalars().first()
                if duplicate_topic:
                    raise ValueError("该题库知识点已被当前教材绑定")
                row.topic_ref_id = topic_ref_id
                row.node_key = self._new_node_key(3, row.name, topic_ref_id)
            row.updated_at = now
        flat = self._flatten_tree(self.list_tree(school_id, textbook_id))
        return next(item for item in flat if item.id == row.id)

    def delete_node(self, school_id: int, textbook_id: int, node_key: str) -> int:
        with sql_repository.session() as session:
            rows = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().all()
            by_parent: dict[str | None, list[KnowledgeNodeORM]] = {}
            by_key = {row.node_key: row for row in rows}
            for row in rows:
                by_parent.setdefault(row.parent_node_key, []).append(row)
            target = by_key.get(node_key)
            if not target:
                return 0
            to_delete = []
            stack = [target.node_key]
            while stack:
                key = stack.pop()
                row = by_key.get(key)
                if not row or row.is_deleted:
                    continue
                to_delete.append(row)
                for child in by_parent.get(key, []):
                    stack.append(child.node_key)
            for row in to_delete:
                row.is_deleted = 1
                row.updated_at = datetime.utcnow()
            return len(to_delete)

    def batch_delete_nodes(self, school_id: int, textbook_id: int, node_keys: list[str]) -> int:
        total = 0
        for node_key in node_keys:
            total += self.delete_node(school_id, textbook_id, node_key)
        return total

    def reorder_siblings(
        self,
        school_id: int,
        textbook_id: int,
        parent_node_key: str | None,
        ordered_node_keys: list[str],
    ) -> int:
        with sql_repository.session() as session:
            rows = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.parent_node_key == parent_node_key,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().all()
            row_map = {row.node_key: row for row in rows}
            valid_order = [key for key in ordered_node_keys if key in row_map]
            untouched = [row.node_key for row in rows if row.node_key not in valid_order]
            final_order = valid_order + untouched
            for index, key in enumerate(final_order, start=1):
                row_map[key].sort_order = index * 10
                row_map[key].updated_at = datetime.utcnow()
            return len(final_order)

    def ensure_seeded(self, school_id: int) -> None:
        created_textbook_id: int | None = None
        with sql_repository.session() as session:
            existing = session.execute(
                select(TextbookORM).where(TextbookORM.school_id == school_id)
            ).scalars().first()
            if existing:
                created_textbook_id = existing.id
            else:
                row = TextbookORM(school_id=school_id, name="通用教材", is_default=1)
                session.add(row)
                session.flush()
                created_textbook_id = row.id
        if created_textbook_id is None:
            return
        self.seed_textbook_nodes(school_id, created_textbook_id)
        with sql_repository.session() as session:
            profiles = session.execute(
                select(StudentProfileORM).where(
                    StudentProfileORM.school_id == school_id,
                    StudentProfileORM.textbook_id.is_(None),
                )
            ).scalars().all()
            for profile in profiles:
                profile.textbook_id = created_textbook_id
            classrooms = session.execute(
                select(ClassroomORM).where(
                    ClassroomORM.school_id == school_id,
                    ClassroomORM.textbook_id.is_(None),
                )
            ).scalars().all()
            for classroom in classrooms:
                classroom.textbook_id = created_textbook_id

    def seed_textbook_nodes(self, school_id: int, textbook_id: int) -> None:
        with sql_repository.session() as session:
            existing = session.execute(
                select(KnowledgeNodeORM.id).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().first()
            if existing:
                return
            topics = sorted(self.repository.list_topics(), key=lambda item: (item.sort_order, item.subject, item.grade_level, item.name))
            subject_map: dict[str, str] = {}
            grade_map: dict[tuple[str, str], str] = {}
            subject_index = 0
            for topic in topics:
                subject = topic.subject or "通用学科"
                grade = topic.grade_level or "通用学段"
                if subject not in subject_map:
                    subject_index += 1
                    subject_key = f"s_{_slug(subject)}"
                    subject_map[subject] = subject_key
                    session.add(
                        KnowledgeNodeORM(
                            school_id=school_id,
                            textbook_id=textbook_id,
                            node_key=subject_key,
                            parent_node_key=None,
                            name=subject,
                            level=1,
                            subject=subject,
                            grade_level="",
                            topic_ref_id=None,
                            sort_order=subject_index * 1000,
                            is_deleted=0,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                    )
                grade_key_tuple = (subject, grade)
                if grade_key_tuple not in grade_map:
                    grade_key = f"g_{_slug(subject)}_{_slug(grade)}"
                    grade_map[grade_key_tuple] = grade_key
                    sort_base = subject_index * 1000 + len([item for item in grade_map if item[0] == subject]) * 100
                    session.add(
                        KnowledgeNodeORM(
                            school_id=school_id,
                            textbook_id=textbook_id,
                            node_key=grade_key,
                            parent_node_key=subject_map[subject],
                            name=grade,
                            level=2,
                            subject=subject,
                            grade_level=grade,
                            topic_ref_id=None,
                            sort_order=sort_base,
                            is_deleted=0,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                    )
                if topic.level < 3:
                    continue
                session.add(
                    KnowledgeNodeORM(
                        school_id=school_id,
                        textbook_id=textbook_id,
                        node_key=f"k_{topic.id}",
                        parent_node_key=grade_map[grade_key_tuple],
                        name=topic.name,
                        level=3,
                        subject=subject,
                        grade_level=grade,
                        topic_ref_id=topic.id,
                        sort_order=topic.sort_order or 0,
                        is_deleted=0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )

    def resolve_user_textbook_id(self, user_id: int, school_id: int | None) -> int | None:
        if not school_id:
            return None
        self.ensure_seeded(school_id)
        with sql_repository.session() as session:
            profile = session.execute(
                select(StudentProfileORM).where(StudentProfileORM.user_id == user_id).order_by(StudentProfileORM.id.asc())
            ).scalars().first()
            if profile and profile.textbook_id:
                return profile.textbook_id
            default = session.execute(
                select(TextbookORM.id).where(TextbookORM.school_id == school_id).order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().first()
            return default

    def topic_ref_options(self) -> list[Topic]:
        return sorted([topic for topic in self.repository.list_topics() if topic.level >= 3], key=lambda item: (item.subject, item.grade_level, item.sort_order, item.id))

    def _new_node_key(self, level: int, name: str, topic_ref_id: str | None = None) -> str:
        if level == 3 and topic_ref_id:
            return f"k_{topic_ref_id}"
        return f"n{level}_{_slug(name)}"

    def _list_nodes(self, school_id: int, textbook_id: int) -> list[KnowledgeNodeORM]:
        with sql_repository.session() as session:
            return session.execute(
                select(KnowledgeNodeORM)
                .where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.is_deleted == 0,
                )
                .order_by(KnowledgeNodeORM.level.asc(), KnowledgeNodeORM.sort_order.asc(), KnowledgeNodeORM.node_key.asc())
            ).scalars().all()

    def _question_count_by_topic(self, nodes: list[KnowledgeNodeORM]) -> dict[str, int]:
        topic_ids = [node.topic_ref_id for node in nodes if node.topic_ref_id]
        if not topic_ids:
            return {}
        with sql_repository.session() as session:
            rows = session.execute(
                select(QuestionBankORM.topic_id, func.count())
                .where(QuestionBankORM.topic_id.in_(topic_ids))
                .group_by(QuestionBankORM.topic_id)
            ).all()
            return {row[0]: int(row[1]) for row in rows}

    def _flatten_tree(self, nodes: list[KnowledgeNodeView]) -> list[KnowledgeNodeView]:
        result: list[KnowledgeNodeView] = []
        stack = list(nodes)
        while stack:
            current = stack.pop(0)
            result.append(current)
            stack[0:0] = current.children
        return result

    def _set_default_in_session(self, session, school_id: int, textbook_id: int) -> None:
        rows = session.execute(select(TextbookORM).where(TextbookORM.school_id == school_id)).scalars().all()
        for row in rows:
            row.is_default = 1 if row.id == textbook_id else 0
