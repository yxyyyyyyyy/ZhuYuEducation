from __future__ import annotations

import json
import os
import re
from typing import List

import requests

from app.core.settings import load_environment
from app.domain.models import RagDocument, TutorMode


class LLMService:
    def __init__(self) -> None:
        load_environment()
        self.api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or ""
        )
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "deepseek-chat")
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))

    def generate_tutor_reply(
        self,
        topic_name: str,
        mode: TutorMode,
        user_message: str,
        evidence: List[RagDocument],
        fallback_text: str,
    ) -> str:
        if not self.api_key:
            return self._offline_reply(topic_name, mode, user_message, evidence, fallback_text)
        try:
            return self._online_reply(topic_name, mode, user_message, evidence, fallback_text)
        except Exception:
            return self._offline_reply(topic_name, mode, user_message, evidence, fallback_text)

    def generate_questions(
        self,
        topic_name: str,
        subject: str,
        subtopics: list[str],
        count: int,
        difficulty_min: float,
        difficulty_max: float,
        question_type: str,
    ) -> list[dict]:
        if not self.api_key:
            return self._offline_generate_questions(
                topic_name, subject, subtopics, count, difficulty_min, difficulty_max, question_type
            )
        try:
            return self._online_generate_questions(
                topic_name, subject, subtopics, count, difficulty_min, difficulty_max, question_type
            )
        except Exception:
            return self._offline_generate_questions(
                topic_name, subject, subtopics, count, difficulty_min, difficulty_max, question_type
            )

    def grade_answer(
        self,
        question_stem: str,
        correct_answer: str,
        student_answer: str,
        explanation: str,
        allow_offline: bool = True,
    ) -> dict | None:
        if not self.api_key:
            if allow_offline:
                return self._offline_grade(question_stem, correct_answer, student_answer, explanation)
            return None
        try:
            return self._online_grade(question_stem, correct_answer, student_answer, explanation)
        except Exception:
            if allow_offline:
                return self._offline_grade(question_stem, correct_answer, student_answer, explanation)
            return None

    def _online_reply(
        self,
        topic_name: str,
        mode: TutorMode,
        user_message: str,
        evidence: List[RagDocument],
        fallback_text: str,
    ) -> str:
        evidence_text = "\n".join(
            [f"- {doc.title} (score={doc.score:.2f}): {doc.snippet}" for doc in evidence]
        ) or "- 无额外证据"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是祝余教育智能辅导老师。请根据给定证据进行教学，不要编造来源。"
                        f" 当前模式是 {mode.value}。输出中文，简洁、耐心、适合学生阅读。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"知识点：{topic_name}\n"
                        f"学生提问：{user_message}\n"
                        f"检索证据：\n{evidence_text}\n"
                        f"如果证据不足，请至少保持以下教学意图：{fallback_text}"
                    ),
                },
            ],
            "temperature": 0.4,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def _offline_reply(
        self,
        topic_name: str,
        mode: TutorMode,
        user_message: str,
        evidence: List[RagDocument],
        fallback_text: str,
    ) -> str:
        evidence_line = "；".join(doc.title for doc in evidence[:2]) if evidence else "当前离线模式无额外文档"
        return (
            f"当前处于离线辅导模式。围绕「{topic_name}」，我会采用 {mode.value} 策略帮助你。"
            f" 结合你的问题「{user_message}」，建议先抓住这些依据：{evidence_line}。"
            f" {fallback_text}"
        )

    def _online_generate_questions(
        self,
        topic_name: str,
        subject: str,
        subtopics: list[str],
        count: int,
        difficulty_min: float,
        difficulty_max: float,
        question_type: str,
    ) -> list[dict]:
        type_desc = {
            "blank": "填空题（有明确答案）",
            "choice": "选择题（4个选项，标明正确答案）",
            "judgment": "判断题（只判断正确或错误）",
            "solution": "解答题（需要写出解题过程）",
            "steps": "分步计算题",
        }.get(question_type, "填空题")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的教育题目生成器。请严格按照JSON格式输出，不要输出任何其他内容。"
                        " 所有题目必须用中文，难度在0到1之间（0最简单，1最难）。"
                        " 每道题必须包含：stem（题干）、answer（答案）、explanation（解析）、"
                        "difficulty（难度0-1）、tags（标签数组）。"
                        " 如果是选择题，还需包含options数组，每项有key(A/B/C/D)和content，answer填正确选项字母。"
                        " 如果是判断题，answer只能填“正确”或“错误”。"
                        " 如果是填空题有多个空，包含blank_count和score_points数组。"
                        " 重要：answer字段必须是简短的答案关键词或短语（不超过20字），不要写长句子！"
                        " 详细的解题思路放在explanation字段中。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"请生成 {count} 道{type_desc}，要求如下：\n"
                        f"学科：{subject}\n"
                        f"知识点：{topic_name}\n"
                        f"子主题：{'、'.join(subtopics)}\n"
                        f"难度范围：{difficulty_min:.1f} ~ {difficulty_max:.1f}\n"
                        f"题型：{question_type}\n\n"
                        f"请输出JSON数组，格式如下：\n"
                        f'[{{"stem":"题干","answer":"答案","explanation":"解析",'
                        f'"difficulty":0.5,"tags":["标签1","标签2"]}}]\n'
                        f"注意：只输出JSON数组，不要输出任何其他文字。"
                    ),
                },
            ],
            "temperature": 0.7,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        return self._parse_json_from_llm(content)

    def _offline_generate_questions(
        self,
        topic_name: str,
        subject: str,
        subtopics: list[str],
        count: int,
        difficulty_min: float,
        difficulty_max: float,
        question_type: str,
    ) -> list[dict]:
        import random

        base_difficulty = lambda: round(random.uniform(difficulty_min, difficulty_max), 2)
        if question_type == "choice":
            templates = [
                {
                    "stem": f"关于{topic_name}，下列说法正确的是哪一项？",
                    "answer": "A",
                    "options": [
                        {"key": "A", "content": f"先抓住{topic_name}的核心定义或对应关系"},
                        {"key": "B", "content": "只需要记住题干里的最后一个数字"},
                        {"key": "C", "content": "所有题目都可以不看条件直接套同一个结论"},
                        {"key": "D", "content": "答案和知识点没有关系"},
                    ],
                    "explanation": f"选择题先排除与{topic_name}定义冲突的选项，再保留最符合题干的说法。",
                    "difficulty": base_difficulty(),
                    "tags": [topic_name, "选择题"],
                }
            ]
        elif question_type == "judgment":
            templates = [
                {
                    "stem": f"判断：学习{topic_name}时，需要先理解核心概念，再做题。",
                    "answer": "正确",
                    "explanation": f"{topic_name}相关题目通常依赖概念和条件识别，先理解再练习更稳。",
                    "difficulty": base_difficulty(),
                    "tags": [topic_name, "判断题"],
                },
                {
                    "stem": f"判断：{topic_name}的题目都不需要看题干条件。",
                    "answer": "错误",
                    "explanation": f"{topic_name}题目需要根据题干条件判断关系和步骤。",
                    "difficulty": base_difficulty(),
                    "tags": [topic_name, "判断题"],
                },
            ]
        elif question_type == "steps":
            templates = [
                {
                    "stem": f"请分步说明如何解决一道{topic_name}基础题。",
                    "answer": "考点→条件→规则→复核",
                    "explanation": f"分步题关注过程完整性，关键是考点、条件、规则和复核四步。",
                    "difficulty": base_difficulty(),
                    "score_points": [
                        {"title": "识别考点", "points": 3.0, "keywords": [topic_name, "考点"]},
                        {"title": "列出条件", "points": 3.0, "keywords": ["条件", "已知"]},
                        {"title": "完成复核", "points": 4.0, "keywords": ["规则", "复核"]},
                    ],
                    "tags": [topic_name, "分步"],
                }
            ]
        else:
            templates = [
                {"stem": f"关于{topic_name}，{subtopics[0] if subtopics else '核心概念'}的定义是______。", "answer": subtopics[0] if subtopics else topic_name, "explanation": f"{topic_name}的基础概念题，需要准确理解定义后再填空。", "difficulty": base_difficulty(), "tags": [topic_name, "概念"]},
                {"stem": f"{topic_name}的{subtopics[1] if len(subtopics) > 1 else '基本性质'}包括______。（至少写出两点）", "answer": f"{subtopics[1] if len(subtopics) > 1 else '定义、性质、应用'}", "explanation": f"需要结合{topic_name}的定义来理解其性质，从多个角度作答。", "difficulty": base_difficulty(), "tags": [topic_name, "性质"]},
                {"stem": f"{topic_name}在实际生活中的一个应用实例是______。", "answer": "结合实际场景举例即可", "explanation": f"应用题需要将{topic_name}的概念与实际问题结合，合理举例即给分。", "difficulty": base_difficulty(), "tags": [topic_name, "应用"]},
            ]
        result = []
        for i in range(count):
            template = templates[i % len(templates)]
            template_copy = dict(template)
            template_copy["difficulty"] = round(random.uniform(difficulty_min, difficulty_max), 2)
            result.append(template_copy)
        return result

    def _online_grade(
        self,
        question_stem: str,
        correct_answer: str,
        student_answer: str,
        explanation: str,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的教育评分助手。请对学生的答案进行评分。"
                        "输出严格的JSON格式，不要输出任何其他内容。"
                        "JSON格式：{\"score\": 0.0-1.0, \"is_correct\": true/false, "
                        "\"feedback\": \"评语\", \"breakdown\": [{\"title\": \"评分项\", "
                        "\"points\": 1.0, \"earned_points\": 0.0, \"status\": \"正确/部分正确/错误\", "
                        "\"evidence\": \"依据\"}]}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"题目：{question_stem}\n"
                        f"参考答案：{correct_answer}\n"
                        f"参考解析：{explanation}\n"
                        f"学生答案：{student_answer}\n\n"
                        f"请评分。注意：如果学生答案在数学上等价或语义上正确，即使表述不同也应给分。"
                        f"只输出JSON，不要输出其他内容。"
                    ),
                },
            ],
            "temperature": 0.2,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = self._parse_json_from_llm(content)
        if parsed and isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]
        if parsed and isinstance(parsed, dict):
            return parsed
        raise ValueError("invalid grading response")

    def _offline_grade(
        self,
        question_stem: str,
        correct_answer: str,
        student_answer: str,
        explanation: str,
    ) -> dict:
        from app.services.question_bank_service import QuestionBankService
        normalized_student = QuestionBankService._normalize_text_static(student_answer)
        normalized_correct = QuestionBankService._normalize_text_static(correct_answer)
        if normalized_student == normalized_correct:
            return {
                "score": 1.0,
                "is_correct": True,
                "feedback": "答案与参考答案一致。",
                "breakdown": [{"title": "答案匹配", "points": 1.0, "earned_points": 1.0, "status": "正确", "evidence": "完全一致"}],
            }
        if normalized_correct in normalized_student:
            return {
                "score": 1.0,
                "is_correct": True,
                "feedback": "学生答案包含正确答案，判定为正确。",
                "breakdown": [{"title": "答案匹配", "points": 1.0, "earned_points": 1.0, "status": "正确", "evidence": "学生答案中包含参考答案"}],
            }
        correct_tokens = set(re.split(r"[,，；;=\s+x×÷\-/()（）\[\]{}]+", normalized_correct)) - {""}
        student_tokens = set(re.split(r"[,，；;=\s+x×÷\-/()（）\[\]{}]+", normalized_student)) - {""}
        if correct_tokens and student_tokens:
            overlap = len(correct_tokens & student_tokens)
            total = max(len(correct_tokens), 1)
            coverage = overlap / total
            if coverage >= 0.8:
                return {
                    "score": round(coverage, 2),
                    "is_correct": True,
                    "feedback": f"学生答案覆盖了参考答案中 {coverage:.0%} 的关键要素，判定为正确。",
                    "breakdown": [{"title": "关键词覆盖", "points": 1.0, "earned_points": round(coverage, 2), "status": "正确", "evidence": f"命中 {overlap}/{total} 个关键要素"}],
                }
            if coverage >= 0.4:
                return {
                    "score": round(coverage, 2),
                    "is_correct": False,
                    "feedback": f"学生答案覆盖了参考答案中 {coverage:.0%} 的关键要素，部分正确但不够完整。",
                    "breakdown": [{"title": "关键词覆盖", "points": 1.0, "earned_points": round(coverage, 2), "status": "部分正确", "evidence": f"命中 {overlap}/{total} 个关键要素"}],
                }
        return {
            "score": 0.0,
            "is_correct": False,
            "feedback": "答案与参考答案不一致，请对照解析检查。",
            "breakdown": [{"title": "答案匹配", "points": 1.0, "earned_points": 0.0, "status": "未命中", "evidence": "请对照参考答案检查关键符号、单位和表达"}],
        }

    def _parse_json_from_llm(self, content: str) -> list[dict] | dict | None:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        import re
        json_match = re.search(r"\[[\s\S]*\]", content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return None
