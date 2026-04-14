from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from app.domain.models import Question, Topic


class KnowledgeRepository:
    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path
        self._payload = self._load()
        self._expand_curriculum()
        self._topics = {
            item["id"]: Topic(**item) for item in self._payload["topics"]
        }
        self._questions = [Question(**item) for item in self._payload["questions"]]

    def _load(self) -> Dict:
        with self._data_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _expand_curriculum(self) -> None:
        legacy_meta = {
            "arithmetic": ("小学四年级", "数学", 110),
            "equations": ("初一", "数学", 710),
            "functions": ("初二", "数学", 820),
            "linear_functions": ("初二", "数学", 830),
            "geometry_triangles": ("初一", "数学", 720),
            "quadratic": ("初三", "数学", 910),
            "chinese_reading": ("初一", "语文", 730),
            "chinese_classical": ("初二", "语文", 840),
            "chinese_writing": ("初二", "语文", 850),
            "english_vocab": ("初一", "英语", 740),
            "english_grammar": ("初二", "英语", 860),
            "english_reading": ("初二", "英语", 870),
            "physics_mechanics": ("初二", "物理", 880),
            "physics_motion": ("初二", "物理", 890),
            "physics_electricity": ("初三", "物理", 920),
        }
        for topic in self._payload["topics"]:
            grade, subject, order = legacy_meta.get(topic["id"], ("", topic.get("subject", ""), 999))
            topic.setdefault("parent_id", f"{subject}_{grade}" if subject and grade else None)
            topic.setdefault("level", 3 if grade else 2)
            topic.setdefault("grade_level", grade)
            topic.setdefault("term", "")
            topic.setdefault("sort_order", order)

        existing_ids = {item["id"] for item in self._payload["topics"]}
        existing_question_ids = {item["id"] for item in self._payload["questions"]}
        grades = [
            ("小学一年级", "p1", ["数学", "语文"]),
            ("小学二年级", "p2", ["数学", "语文"]),
            ("小学三年级", "p3", ["数学", "语文", "英语"]),
            ("小学四年级", "p4", ["数学", "语文", "英语"]),
            ("小学五年级", "p5", ["数学", "语文", "英语"]),
            ("小学六年级", "p6", ["数学", "语文", "英语"]),
            ("初一", "m1", ["数学", "语文", "英语"]),
            ("初二", "m2", ["数学", "语文", "英语", "物理"]),
            ("初三", "m3", ["数学", "语文", "英语", "物理", "化学"]),
        ]
        cores = {
            "数学": ["数与运算", "图形与几何", "数量关系"],
            "语文": ["阅读理解", "语言积累", "写作表达"],
            "英语": ["词汇语音", "语法句型", "阅读表达"],
            "物理": ["力学", "声光热", "电学"],
            "化学": ["物质构成", "化学变化", "实验探究"],
        }
        for grade_index, (grade_name, grade_code, subjects) in enumerate(grades, start=1):
            for subject_index, subject in enumerate(subjects, start=1):
                parent_id = f"{subject}_{grade_name}"
                if parent_id not in existing_ids:
                    self._payload["topics"].append({
                        "id": parent_id,
                        "name": f"{grade_name}{subject}",
                        "subject": subject,
                        "parent_id": subject,
                        "level": 2,
                        "grade_level": grade_name,
                        "term": "全年",
                        "sort_order": grade_index * 100 + subject_index * 10,
                        "prerequisites": [],
                        "subtopics": cores[subject],
                        "difficulty": min(0.2 + grade_index * 0.07, 0.88),
                        "learning_objectives": [f"掌握{grade_name}{subject}核心知识"],
                        "common_mistakes": ["基础概念不清", "审题不完整"],
                        "tutoring_tips": ["先回顾概念，再做分层练习"],
                    })
                    existing_ids.add(parent_id)
                for core_index, core in enumerate(cores[subject], start=1):
                    topic_id = f"core_{grade_code}_{self._subject_code(subject)}_{core_index}"
                    if topic_id not in existing_ids:
                        self._payload["topics"].append({
                            "id": topic_id,
                            "name": core,
                            "subject": subject,
                            "parent_id": parent_id,
                            "level": 3,
                            "grade_level": grade_name,
                            "term": "全年",
                            "sort_order": grade_index * 1000 + subject_index * 100 + core_index,
                            "prerequisites": [],
                            "subtopics": self._subtopics_for(subject, core, grade_name),
                            "difficulty": min(0.18 + grade_index * 0.07 + core_index * 0.03, 0.92),
                            "learning_objectives": [f"理解并应用{core}"],
                            "common_mistakes": ["只记结论，不会迁移应用"],
                            "tutoring_tips": ["用例题拆解关键步骤，再做同类变式"],
                        })
                        existing_ids.add(topic_id)
                    question_id = f"q_{topic_id}_01"
                    if question_id not in existing_question_ids:
                        self._payload["questions"].append(self._sample_question(question_id, topic_id, grade_name, subject, core))
                        existing_question_ids.add(question_id)

    def _subject_code(self, subject: str) -> str:
        return {"数学": "math", "语文": "chinese", "英语": "english", "物理": "physics", "化学": "chemistry"}.get(subject, "general")

    def _subtopics_for(self, subject: str, core: str, grade_name: str) -> list[str]:
        mapping = {
            "数与运算": ["整数/小数/分数", "运算顺序", "估算与检验"],
            "图形与几何": ["图形认识", "周长面积体积", "位置与变换"],
            "数量关系": ["应用题建模", "比例与方程", "函数意识"],
            "阅读理解": ["信息提取", "主旨概括", "表达效果"],
            "语言积累": ["字词句基础", "古诗文积累", "语言运用"],
            "写作表达": ["审题立意", "结构安排", "语言修改"],
            "词汇语音": ["核心词汇", "自然拼读", "词义辨析"],
            "语法句型": ["时态语态", "句子结构", "从句表达"],
            "阅读表达": ["细节理解", "推断判断", "书面表达"],
            "力学": ["运动和力", "压强浮力", "功和机械"],
            "声光热": ["声现象", "光现象", "物态变化"],
            "电学": ["电路", "欧姆定律", "电功率"],
            "物质构成": ["分子原子", "元素化合物", "化学式"],
            "化学变化": ["质量守恒", "化学方程式", "酸碱盐"],
            "实验探究": ["实验操作", "现象分析", "方案评价"],
        }
        return mapping.get(core, [grade_name, subject, core])

    def _sample_question(self, question_id: str, topic_id: str, grade: str, subject: str, core: str) -> dict:
        return {
            "id": question_id,
            "topic_id": topic_id,
            "stem": f"{grade}{subject}：请说明「{core}」学习中最关键的一个方法，并举一个简单例子。",
            "difficulty": 0.45,
            "answer": f"围绕{core}先说清概念，再结合例子说明应用过程。",
            "explanation": f"本题用于检查学生是否理解{grade}{subject}{core}的核心方法。",
            "question_type": "solution",
            "tags": [grade, subject, core, "课标核心样题"],
        }

    def list_topics(self) -> List[Topic]:
        return list(self._topics.values())

    def get_topic(self, topic_id: str) -> Topic:
        return self._topics[topic_id]

    def has_topic(self, topic_id: str) -> bool:
        return topic_id in self._topics

    def list_questions_by_topic(self, topic_id: str) -> List[Question]:
        return [question for question in self._questions if question.topic_id == topic_id]

    def descendant_topic_ids(self, topic_id: str) -> list[str]:
        child_map: dict[str, list[str]] = {}
        for topic in self._topics.values():
            if topic.parent_id:
                child_map.setdefault(topic.parent_id, []).append(topic.id)
        result: list[str] = []
        stack = list(child_map.get(topic_id, []))
        while stack:
            current = stack.pop(0)
            result.append(current)
            stack.extend(child_map.get(current, []))
        return result
