from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, or_, select

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
        self._seed_payload = self._load_seed_payload()

    def list_textbooks(self, school_id: int) -> list[TextbookView]:
        self.ensure_seeded(school_id)
        with sql_repository.session() as session:
            rows = session.execute(
                select(TextbookORM)
                .where(TextbookORM.school_id == school_id)
                .order_by(
                    TextbookORM.grade_level.asc(),
                    TextbookORM.subject.asc(),
                    TextbookORM.is_default.desc(),
                    TextbookORM.id.asc(),
                )
            ).scalars().all()
            return [self._textbook_view(row) for row in rows]

    def create_textbook(
        self,
        school_id: int,
        name: str,
        grade_level: str,
        subject: str,
        set_default: bool = False,
    ) -> TextbookView:
        normalized_name = (name or "").strip()
        normalized_grade = (grade_level or "").strip()
        normalized_subject = (subject or "").strip()
        if not normalized_grade:
            raise ValueError("教材年级不能为空")
        if not normalized_subject:
            raise ValueError("教材学科不能为空")
        if not normalized_name:
            normalized_name = f"人教版{normalized_grade}{normalized_subject}（全年）"

        textbook_id: int
        with sql_repository.session() as session:
            duplicate = session.execute(
                select(TextbookORM).where(
                    TextbookORM.school_id == school_id,
                    TextbookORM.grade_level == normalized_grade,
                    TextbookORM.subject == normalized_subject,
                )
            ).scalars().first()
            if duplicate:
                raise ValueError("该学校同年级同学科已绑定教材")

            row = TextbookORM(
                school_id=school_id,
                name=normalized_name,
                grade_level=normalized_grade,
                subject=normalized_subject,
                is_default=0,
            )
            session.add(row)
            session.flush()
            textbook_id = row.id
            has_default = session.execute(
                select(TextbookORM.id).where(TextbookORM.school_id == school_id, TextbookORM.is_default == 1)
            ).scalars().first()
            if set_default or not has_default:
                self._set_default_in_session(session, school_id, textbook_id)

        self.seed_textbook_nodes(school_id, textbook_id)
        return next(item for item in self.list_textbooks(school_id) if item.id == textbook_id)

    def get_default_textbook_id(self, school_id: int, grade_level: str | None = None, subject: str | None = None) -> int:
        self.ensure_seeded(school_id)
        with sql_repository.session() as session:
            stmt = select(TextbookORM).where(TextbookORM.school_id == school_id)
            if grade_level:
                stmt = stmt.where(TextbookORM.grade_level == grade_level)
            if subject:
                stmt = stmt.where(TextbookORM.subject == subject)
            row = session.execute(stmt.order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())).scalars().first()
            if row:
                return row.id
            fallback = session.execute(
                select(TextbookORM)
                .where(TextbookORM.school_id == school_id)
                .order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().first()
            if not fallback:
                raise ValueError("未找到教材")
            return fallback.id

    def list_topics_for_school(self, school_id: int, textbook_id: int | None = None) -> list[Topic]:
        textbook_id = textbook_id or self.get_default_textbook_id(school_id)
        textbook = self._get_textbook_or_raise(school_id, textbook_id)
        nodes = self._list_nodes(school_id, textbook_id)
        if not nodes:
            self.seed_textbook_nodes(school_id, textbook_id)
            nodes = self._list_nodes(school_id, textbook_id)
        if not nodes:
            return []

        topics: list[Topic] = []
        ordered = sorted(nodes, key=lambda item: (item.level, item.sort_order, item.node_key))
        for node in ordered:
            level = 1 if node.level <= 1 else 2
            topic_id = node.node_key
            topics.append(
                Topic(
                    id=topic_id,
                    name=node.name,
                    subject=node.subject or textbook.subject,
                    parent_id=node.parent_node_key if level == 2 else None,
                    level=level,
                    grade_level=node.grade_level or textbook.grade_level,
                    term="全年",
                    sort_order=node.sort_order,
                    prerequisites=[],
                    subtopics=[],
                    difficulty=0.5,
                    learning_objectives=[f"掌握{node.name}"],
                    common_mistakes=[f"{node.name}的概念边界不清"],
                    tutoring_tips=["先理解概念，再做同类题迁移"],
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

        views: dict[str, KnowledgeNodeView] = {}
        children: dict[str, list[KnowledgeNodeView]] = defaultdict(list)
        roots: list[KnowledgeNodeView] = []

        for node in nodes:
            view = KnowledgeNodeView(
                id=node.id,
                node_key=node.node_key,
                parent_node_key=node.parent_node_key,
                name=node.name,
                level=1 if node.level <= 1 else 2,
                subject=node.subject or "",
                grade_level=node.grade_level or "",
                topic_ref_id=node.node_key if node.level >= 2 else None,
                sort_order=node.sort_order,
                question_count=question_count_by_topic.get(node.node_key, 0) if node.level >= 2 else 0,
                children=[],
            )
            views[node.node_key] = view

        for node in nodes:
            view = views[node.node_key]
            if node.level <= 1 or not node.parent_node_key:
                roots.append(view)
                continue
            parent = views.get(node.parent_node_key)
            if not parent:
                roots.append(view)
                continue
            children[parent.node_key].append(view)

        for root in roots:
            node_children = sorted(children.get(root.node_key, []), key=lambda child: (child.sort_order, child.node_key))
            root.children = node_children
            root.question_count = sum(child.question_count for child in node_children)

        return sorted(roots, key=lambda child: (child.sort_order, child.node_key))

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
        del topic_ref_id, subject, grade_level
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ValueError("知识点名称不能为空")
        normalized_level = 1 if int(level) <= 1 else 2

        with sql_repository.session() as session:
            textbook = self._get_textbook_or_raise(school_id, textbook_id, session=session)
            normalized_parent = (parent_node_key or "").strip() or None
            if normalized_level == 2 and not normalized_parent:
                raise ValueError("二级知识点必须选择一级父节点")
            if normalized_level == 1:
                normalized_parent = None

            if normalized_parent:
                parent = session.execute(
                    select(KnowledgeNodeORM).where(
                        KnowledgeNodeORM.school_id == school_id,
                        KnowledgeNodeORM.textbook_id == textbook_id,
                        KnowledgeNodeORM.node_key == normalized_parent,
                        KnowledgeNodeORM.level <= 1,
                        KnowledgeNodeORM.is_deleted == 0,
                    )
                ).scalars().first()
                if not parent:
                    raise ValueError("一级知识点不存在")

            duplicate_name = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.parent_node_key == normalized_parent,
                    KnowledgeNodeORM.level == normalized_level,
                    KnowledgeNodeORM.name == normalized_name,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().first()
            if duplicate_name:
                raise ValueError("同名知识点已存在")

            max_sort = session.scalar(
                select(func.max(KnowledgeNodeORM.sort_order)).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.parent_node_key == normalized_parent,
                    KnowledgeNodeORM.level == normalized_level,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ) or 0
            node_key = self._new_topic_id(
                session,
                school_id,
                textbook_id,
                normalized_name,
                preferred=f"tb{textbook_id}_l{normalized_level}_{_slug(normalized_name)}",
            )
            row = KnowledgeNodeORM(
                school_id=school_id,
                textbook_id=textbook_id,
                node_key=node_key,
                parent_node_key=normalized_parent,
                name=normalized_name,
                level=normalized_level,
                subject=textbook.subject,
                grade_level=textbook.grade_level,
                topic_ref_id=node_key if normalized_level >= 2 else None,
                sort_order=max_sort + 10,
                is_deleted=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            row_id = row.id

        flat = self._flatten_tree(self.list_tree(school_id, textbook_id))
        return next(item for item in flat if item.id == row_id)

    def update_node(
        self,
        school_id: int,
        textbook_id: int,
        node_key: str,
        name: str | None = None,
        topic_ref_id: str | None = None,
    ) -> KnowledgeNodeView:
        del topic_ref_id
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
            row.updated_at = datetime.utcnow()
            row_id = row.id
        flat = self._flatten_tree(self.list_tree(school_id, textbook_id))
        return next(item for item in flat if item.id == row_id)

    def delete_node(self, school_id: int, textbook_id: int, node_key: str) -> int:
        with sql_repository.session() as session:
            rows = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().all()
            by_parent: dict[str | None, list[KnowledgeNodeORM]] = defaultdict(list)
            by_key = {row.node_key: row for row in rows}
            for row in rows:
                by_parent[row.parent_node_key].append(row)
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
            normalized_parent = (parent_node_key or "").strip() or None
            rows = session.execute(
                select(KnowledgeNodeORM).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.parent_node_key == normalized_parent,
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
        textbook_ids: list[int] = []
        with sql_repository.session() as session:
            rows = session.execute(
                select(TextbookORM).where(TextbookORM.school_id == school_id).order_by(TextbookORM.id.asc())
            ).scalars().all()

            if not rows:
                rows = self._seed_textbooks_for_school_in_session(session, school_id)
            else:
                for row in rows:
                    row.grade_level = row.grade_level or ""
                    row.subject = row.subject or ""

            if rows and not any(item.is_default for item in rows):
                rows[0].is_default = 1

            textbook_ids = [row.id for row in rows]
            default_id = next((row.id for row in rows if row.is_default), rows[0].id if rows else None)

        for textbook_id in textbook_ids:
            self.seed_textbook_nodes(school_id, textbook_id)

        if not textbook_ids:
            return

        with sql_repository.session() as session:
            profiles = session.execute(
                select(StudentProfileORM).where(
                    StudentProfileORM.school_id == school_id,
                    StudentProfileORM.textbook_id.is_(None),
                )
            ).scalars().all()
            for profile in profiles:
                profile.textbook_id = default_id
            classrooms = session.execute(
                select(ClassroomORM).where(
                    ClassroomORM.school_id == school_id,
                    ClassroomORM.textbook_id.is_(None),
                )
            ).scalars().all()
            for classroom in classrooms:
                classroom.textbook_id = default_id

    def seed_textbook_nodes(self, school_id: int, textbook_id: int) -> None:
        with sql_repository.session() as session:
            textbook = self._get_textbook_or_raise(school_id, textbook_id, session=session)
            existing = session.execute(
                select(KnowledgeNodeORM.id).where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.is_deleted == 0,
                )
            ).scalars().first()
            if existing:
                return

            outline = self._seed_outline_for_textbook(textbook.grade_level, textbook.subject)
            if not outline:
                outline = self._fallback_outline(textbook.subject)

            l1_sort = 10
            for block in outline:
                l1_name = (block.get("name") or "").strip()
                if not l1_name:
                    continue
                l1_key = self._new_topic_id(
                    session,
                    school_id,
                    textbook_id,
                    l1_name,
                    preferred=f"tb{textbook_id}_l1_{_slug(l1_name)}",
                )
                l1_row = KnowledgeNodeORM(
                    school_id=school_id,
                    textbook_id=textbook_id,
                    node_key=l1_key,
                    parent_node_key=None,
                    name=l1_name,
                    level=1,
                    subject=textbook.subject,
                    grade_level=textbook.grade_level,
                    topic_ref_id=None,
                    sort_order=l1_sort,
                    is_deleted=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(l1_row)

                l2_sort = 10
                for child_name in block.get("level2", []):
                    child_name = (child_name or "").strip()
                    if not child_name:
                        continue
                    l2_key = self._new_topic_id(
                        session,
                        school_id,
                        textbook_id,
                        f"{l1_name}_{child_name}",
                        preferred=f"tb{textbook_id}_l2_{_slug(child_name)}",
                    )
                    session.add(
                        KnowledgeNodeORM(
                            school_id=school_id,
                            textbook_id=textbook_id,
                            node_key=l2_key,
                            parent_node_key=l1_key,
                            name=child_name,
                            level=2,
                            subject=textbook.subject,
                            grade_level=textbook.grade_level,
                            topic_ref_id=l2_key,
                            sort_order=l2_sort,
                            is_deleted=0,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                    )
                    l2_sort += 10
                l1_sort += 10

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
            if profile and profile.grade_level and profile.target_subject:
                matched = session.execute(
                    select(TextbookORM.id).where(
                        TextbookORM.school_id == school_id,
                        TextbookORM.grade_level == profile.grade_level,
                        TextbookORM.subject == profile.target_subject,
                    ).order_by(TextbookORM.id.asc())
                ).scalars().first()
                if matched:
                    return matched
            default = session.execute(
                select(TextbookORM.id)
                .where(TextbookORM.school_id == school_id)
                .order_by(TextbookORM.is_default.desc(), TextbookORM.id.asc())
            ).scalars().first()
            return default

    def topic_ref_options(self) -> list[Topic]:
        topics = []
        seen = set()
        for grade_level, subject in self._seed_pairs_from_seed():
            for block in self._seed_outline_for_textbook(grade_level, subject):
                for idx, child in enumerate(block.get("level2", []), start=1):
                    topic_id = f"seed_{_slug(grade_level)}_{_slug(subject)}_{_slug(child)}"
                    if topic_id in seen:
                        continue
                    seen.add(topic_id)
                    topics.append(
                        Topic(
                            id=topic_id,
                            name=child,
                            subject=subject,
                            parent_id=f"seed_{_slug(grade_level)}_{_slug(subject)}_{_slug(block.get('name', ''))}",
                            level=2,
                            grade_level=grade_level,
                            term="全年",
                            sort_order=idx,
                            prerequisites=[],
                            subtopics=[],
                            difficulty=0.5,
                            learning_objectives=[f"掌握{child}"],
                            common_mistakes=[],
                            tutoring_tips=[],
                        )
                    )
        return topics

    def _list_nodes(self, school_id: int, textbook_id: int) -> list[KnowledgeNodeORM]:
        with sql_repository.session() as session:
            return session.execute(
                select(KnowledgeNodeORM)
                .where(
                    KnowledgeNodeORM.school_id == school_id,
                    KnowledgeNodeORM.textbook_id == textbook_id,
                    KnowledgeNodeORM.is_deleted == 0,
                    KnowledgeNodeORM.level.in_([1, 2]),
                )
                .order_by(KnowledgeNodeORM.level.asc(), KnowledgeNodeORM.sort_order.asc(), KnowledgeNodeORM.node_key.asc())
            ).scalars().all()

    def _question_count_by_topic(self, nodes: list[KnowledgeNodeORM]) -> dict[str, int]:
        topic_ids = list({node.node_key for node in nodes if node.level >= 2})
        if not topic_ids:
            return {}
        with sql_repository.session() as session:
            rows = session.execute(
                select(QuestionBankORM.knowledge_l2_id, QuestionBankORM.topic_id).where(
                    or_(QuestionBankORM.knowledge_l2_id.in_(topic_ids), QuestionBankORM.topic_id.in_(topic_ids))
                )
            ).all()
        counter: dict[str, int] = defaultdict(int)
        for knowledge_l2_id, topic_id in rows:
            key = (knowledge_l2_id or topic_id or "").strip()
            if key:
                counter[key] += 1
        return dict(counter)

    def _flatten_tree(self, nodes: list[KnowledgeNodeView]) -> list[KnowledgeNodeView]:
        result: list[KnowledgeNodeView] = []
        queue = list(nodes)
        while queue:
            current = queue.pop(0)
            result.append(current)
            queue[0:0] = current.children
        return result

    def _set_default_in_session(self, session, school_id: int, textbook_id: int) -> None:
        rows = session.execute(select(TextbookORM).where(TextbookORM.school_id == school_id)).scalars().all()
        for row in rows:
            row.is_default = 1 if row.id == textbook_id else 0

    def _textbook_view(self, row: TextbookORM) -> TextbookView:
        return TextbookView(
            id=row.id,
            school_id=row.school_id,
            grade_level=row.grade_level or "",
            subject=row.subject or "",
            name=row.name,
            is_default=bool(row.is_default),
        )

    def _get_textbook_or_raise(self, school_id: int, textbook_id: int, session=None) -> TextbookORM:
        if session is None:
            with sql_repository.session() as inner:
                row = inner.execute(
                    select(TextbookORM).where(TextbookORM.school_id == school_id, TextbookORM.id == textbook_id)
                ).scalars().first()
                if not row:
                    raise ValueError("教材不存在")
                return row
        row = session.execute(
            select(TextbookORM).where(TextbookORM.school_id == school_id, TextbookORM.id == textbook_id)
        ).scalars().first()
        if not row:
            raise ValueError("教材不存在")
        return row

    def _seed_textbooks_for_school_in_session(self, session, school_id: int) -> list[TextbookORM]:
        pairs = self._seed_pairs_from_seed()
        rows: list[TextbookORM] = []
        for index, (grade_level, subject) in enumerate(pairs, start=1):
            row = TextbookORM(
                school_id=school_id,
                grade_level=grade_level,
                subject=subject,
                name=f"人教版{grade_level}{subject}（全年）",
                is_default=1 if index == 1 else 0,
            )
            session.add(row)
            rows.append(row)
        session.flush()
        return rows

    def _seed_pairs_from_seed(self) -> list[tuple[str, str]]:
        grades = self._seed_payload.get("grades", [])
        pairs: list[tuple[str, str]] = []
        for item in grades:
            grade = (item.get("grade_level") or "").strip()
            for subject in item.get("subjects", []):
                subject = (subject or "").strip()
                if grade and subject:
                    pairs.append((grade, subject))
        if pairs:
            return pairs
        return [("小学四年级", "数学")]

    def _seed_outline_for_textbook(self, grade_level: str, subject: str) -> list[dict]:
        templates = self._seed_payload.get("templates", {})
        base = templates.get(subject, {})
        blocks = base.get("level1", []) if isinstance(base, dict) else []
        result = []
        for block in blocks:
            name = (block.get("name") or "").strip()
            children = [str(item).strip() for item in block.get("level2", []) if str(item).strip()]
            if not name or not children:
                continue
            result.append({"name": name, "level2": children})

        grade_overrides = self._seed_payload.get("grade_overrides", {})
        override_key = f"{grade_level}|{subject}"
        override_blocks = grade_overrides.get(override_key, [])
        for block in override_blocks:
            name = (block.get("name") or "").strip()
            children = [str(item).strip() for item in block.get("level2", []) if str(item).strip()]
            if not name or not children:
                continue
            replaced = False
            for index, current in enumerate(result):
                if current["name"] == name:
                    result[index] = {"name": name, "level2": children}
                    replaced = True
                    break
            if not replaced:
                result.append({"name": name, "level2": children})

        return result

    def _fallback_outline(self, subject: str) -> list[dict]:
        mapping = {
            "数学": [
                {"name": "数与代数", "level2": ["数与运算", "方程与不等式", "函数与模型"]},
                {"name": "图形与几何", "level2": ["图形性质", "度量计算", "空间观念"]},
                {"name": "统计与概率", "level2": ["数据整理", "统计推断", "概率思想"]},
            ],
            "语文": [
                {"name": "语言积累", "level2": ["字词句", "古诗文", "语法修辞"]},
                {"name": "阅读鉴赏", "level2": ["现代文阅读", "文言文阅读", "整本书阅读"]},
                {"name": "表达与写作", "level2": ["写作表达", "口语交际", "综合实践"]},
            ],
            "英语": [
                {"name": "语言知识", "level2": ["词汇", "语法", "语音语调"]},
                {"name": "语言技能", "level2": ["听说", "阅读", "写作"]},
                {"name": "文化意识", "level2": ["跨文化理解", "语用能力", "学习策略"]},
            ],
        }
        return mapping.get(
            subject,
            [
                {"name": "基础知识", "level2": ["核心概念", "典型方法", "综合应用"]},
            ],
        )

    def _new_topic_id(
        self,
        session,
        school_id: int,
        textbook_id: int,
        source: str,
        preferred: str | None = None,
    ) -> str:
        base = preferred or f"tb{textbook_id}_{_slug(source)}"
        candidate = base
        suffix = 1
        while session.execute(
            select(KnowledgeNodeORM.id).where(
                KnowledgeNodeORM.school_id == school_id,
                KnowledgeNodeORM.textbook_id == textbook_id,
                KnowledgeNodeORM.is_deleted == 0,
                or_(KnowledgeNodeORM.node_key == candidate, KnowledgeNodeORM.topic_ref_id == candidate),
            )
        ).scalars().first():
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _load_seed_payload(self) -> dict:
        seed_path = Path(__file__).resolve().parents[2] / "data" / "curriculum_seed_pep.json"
        if not seed_path.exists():
            return {}
        try:
            return json.loads(seed_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
