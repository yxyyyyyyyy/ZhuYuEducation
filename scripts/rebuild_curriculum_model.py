from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import (  # noqa: E402
    ChatMessageORM,
    ChatSessionORM,
    ClassroomORM,
    KnowledgeChunkORM,
    KnowledgeDocumentORM,
    KnowledgeNodeORM,
    MistakeRecordORM,
    PracticeRecordORM,
    QuestionBankORM,
    RagDocumentORM,
    ReportRecordORM,
    RetrievalCaseORM,
    SchoolORM,
    StudentMasteryORM,
    StudentProfileORM,
    TextbookORM,
    init_database,
)
from app.repositories.knowledge_repository import KnowledgeRepository  # noqa: E402
from app.repositories.sql_repository import sql_repository  # noqa: E402
from app.services.knowledge_config_service import KnowledgeConfigService  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402


BOOTSTRAP_SOURCE = "ai_bootstrap"
MAX_RETRIES = 3
SLOT_BLUEPRINTS = [
    {"tier": "基础知识点", "difficulty_level": 2, "question_type": "blank"},
    {"tier": "核心知识点", "difficulty_level": 3, "question_type": "choice"},
    {"tier": "扩展知识点", "difficulty_level": 4, "question_type": "steps"},
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重建教材树并可选批量回填题库")
    parser.add_argument(
        "--generate-questions",
        dest="generate_questions",
        action="store_true",
        help="重建后按二级知识点批量生成题目（默认开启）",
    )
    parser.add_argument(
        "--no-generate-questions",
        dest="generate_questions",
        action="store_false",
        help="仅重建教材树与学习数据，不回填题目",
    )
    parser.add_argument(
        "--questions-per-topic",
        type=int,
        default=3,
        help="每个二级知识点生成题目数（默认 3）",
    )
    parser.add_argument(
        "--strict-llm",
        dest="strict_llm",
        action="store_true",
        help="强制在线 LLM 生成（默认开启）",
    )
    parser.add_argument(
        "--allow-offline-llm",
        dest="strict_llm",
        action="store_false",
        help="允许离线模板兜底生成",
    )
    parser.add_argument(
        "--max-topics",
        type=int,
        default=0,
        help="调试用：限制最多生成的二级知识点数量（0 表示不限制）",
    )
    parser.add_argument(
        "--question-status",
        choices=["approved", "pending"],
        default="approved",
        help="批量回填题目的状态（默认 approved）",
    )
    parser.add_argument(
        "--llm-workers",
        type=int,
        default=1,
        help="并发调用 LLM 的线程数（默认 1）",
    )
    parser.set_defaults(generate_questions=True, strict_llm=True)
    return parser.parse_args()


def _pick_textbook_id(service: KnowledgeConfigService, school_id: int, grade_level: str, subject: str) -> int:
    books = service.list_textbooks(school_id)
    grade_level = (grade_level or "").strip()
    subject = (subject or "").strip()
    if grade_level and subject:
        exact = next((row for row in books if row.grade_level == grade_level and row.subject == subject), None)
        if exact:
            return exact.id
    if grade_level:
        grade_rows = [row for row in books if row.grade_level == grade_level]
        if grade_rows:
            math_row = next((row for row in grade_rows if row.subject == "数学"), None)
            return (math_row or grade_rows[0]).id
    default = next((row for row in books if row.is_default), None)
    return (default or books[0]).id


def _first_l2_topic(service: KnowledgeConfigService, school_id: int, textbook_id: int) -> str:
    topics = service.list_topics_for_school(school_id, textbook_id)
    l2 = [item for item in topics if item.level == 2]
    l2.sort(key=lambda item: (item.sort_order, item.id))
    return l2[0].id if l2 else ""


def _difficulty_level_to_float(level: int) -> float:
    mapping = {1: 0.1, 2: 0.3, 3: 0.5, 4: 0.7, 5: 0.9}
    return mapping.get(int(level), 0.5)


def _slot_for_index(index: int) -> dict:
    return SLOT_BLUEPRINTS[index % len(SLOT_BLUEPRINTS)]


def _normalize_options(raw_options) -> list[dict]:
    if not isinstance(raw_options, list):
        return []
    options = []
    seen = set()
    for item in raw_options:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip().upper()[:1]
        content = str(item.get("content", "")).strip()
        if key not in {"A", "B", "C", "D"} or not content or key in seen:
            continue
        seen.add(key)
        options.append({"key": key, "content": content})
    options.sort(key=lambda item: item["key"])
    return options


def _normalize_choice_answer(answer: str, options: list[dict]) -> str:
    normalized = (answer or "").strip().upper()
    if normalized in {"A", "B", "C", "D"}:
        return normalized
    for option in options:
        if (answer or "").strip() == option["content"]:
            return option["key"]
    return options[0]["key"] if options else normalized or "A"


def _default_score_points(topic_name: str) -> list[dict]:
    return [
        {"title": "识别考点", "points": 3.0, "keywords": [topic_name, "考点"]},
        {"title": "列出条件", "points": 3.0, "keywords": ["条件", "已知"]},
        {"title": "完成推导", "points": 4.0, "keywords": ["步骤", "结论"]},
    ]


def _normalize_score_points(raw_points, question_type: str, topic_name: str) -> list[dict]:
    if question_type != "steps":
        return []
    if not isinstance(raw_points, list):
        return _default_score_points(topic_name)
    points = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        try:
            value = float(item.get("points", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        keywords = [str(word).strip() for word in item.get("keywords", []) if str(word).strip()]
        points.append(
            {
                "title": title,
                "points": max(value, 0.5),
                "keywords": keywords[:5],
            }
        )
    return points or _default_score_points(topic_name)


def _normalize_tags(base_tags: list[str], raw_tags) -> list[str]:
    tags = [item for item in base_tags if item and str(item).strip()]
    for tag in raw_tags or []:
        value = str(tag).strip()
        if value and value not in tags:
            tags.append(value)
    return tags[:15]


def _call_llm_one(
    llm_service: LLMService,
    target: dict,
    slot: dict,
    strict_llm: bool,
) -> dict:
    difficulty = _difficulty_level_to_float(slot["difficulty_level"])
    subtopics = [target["l1_name"], target["l2_name"]]
    if strict_llm:
        if not llm_service.api_key:
            raise RuntimeError("严格模式需要配置 OPENAI_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY")
        raw = llm_service._online_generate_questions(  # noqa: SLF001
            topic_name=target["l2_name"],
            subject=target["subject"],
            subtopics=subtopics,
            count=1,
            difficulty_min=difficulty,
            difficulty_max=difficulty,
            question_type=slot["question_type"],
        )
    else:
        raw = llm_service.generate_questions(
            topic_name=target["l2_name"],
            subject=target["subject"],
            subtopics=subtopics,
            count=1,
            difficulty_min=difficulty,
            difficulty_max=difficulty,
            question_type=slot["question_type"],
        )
    if isinstance(raw, dict):
        raw = [raw]
    if not raw:
        raise ValueError("LLM 未返回题目")
    return _normalize_question_item(raw[0], target, slot)


def _normalize_question_item(item: dict, target: dict, slot: dict) -> dict:
    stem = str(item.get("stem", "")).strip()
    answer = str(item.get("answer", "")).strip()
    explanation = str(item.get("explanation", "")).strip()
    if not stem or not answer:
        raise ValueError("LLM 返回题干或答案为空")

    question_type = slot["question_type"]
    options = _normalize_options(item.get("options"))
    if question_type == "choice" and len(options) < 2:
        options = [
            {"key": "A", "content": "选项A"},
            {"key": "B", "content": "选项B"},
            {"key": "C", "content": "选项C"},
            {"key": "D", "content": "选项D"},
        ]
    if question_type == "choice":
        answer = _normalize_choice_answer(answer, options)
    score_points = _normalize_score_points(item.get("score_points"), question_type, target["l2_name"])
    blank_count = 1
    if question_type == "blank":
        try:
            blank_count = max(int(item.get("blank_count", 1)), 1)
        except (TypeError, ValueError):
            blank_count = 1

    base_tags = [
        target["grade_level"],
        target["subject"],
        f"L1:{target['l1_name']}",
        f"L2:{target['l2_name']}",
        slot["tier"],
        f"难度L{slot['difficulty_level']}",
    ]
    tags = _normalize_tags(base_tags, item.get("tags"))

    return {
        "stem": stem,
        "answer": answer,
        "explanation": explanation or f"围绕“{target['l2_name']}”组织思路并完成作答。",
        "question_type": question_type,
        "options": options if question_type == "choice" else [],
        "blank_count": blank_count,
        "score_points": score_points,
        "knowledge_tiers": [slot["tier"]],
        "tags": tags,
        "difficulty_level": int(slot["difficulty_level"]),
        "difficulty": _difficulty_level_to_float(slot["difficulty_level"]),
    }


def _call_llm_bundle(
    llm_service: LLMService,
    target: dict,
    slots: list[dict],
    strict_llm: bool,
) -> list[dict]:
    if not slots:
        return []
    if not strict_llm or len(slots) == 1:
        return [_call_llm_one(llm_service, target, slot, strict_llm=strict_llm) for slot in slots]
    if not llm_service.api_key:
        raise RuntimeError("严格模式需要配置 OPENAI_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY")

    spec = [
        {
            "tier": slot["tier"],
            "difficulty_level": slot["difficulty_level"],
            "difficulty": _difficulty_level_to_float(slot["difficulty_level"]),
            "question_type": slot["question_type"],
        }
        for slot in slots
    ]
    payload = {
        "model": llm_service.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是专业的中小学题库命题老师。只输出JSON数组，不要输出任何解释文字。"
                    " 每个元素必须包含tier、question_type、stem、answer、explanation、difficulty、tags。"
                    " 选择题必须包含options数组，选项key为A/B/C/D，answer只填正确选项字母。"
                    " 填空题可包含blank_count。分步计算题必须包含score_points数组，"
                    "每项含title、points、keywords。题目必须贴合给定教材一级/二级知识点。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"年级：{target['grade_level']}\n"
                    f"学科：{target['subject']}\n"
                    f"教材一级知识点：{target['l1_name']}\n"
                    f"教材二级知识点：{target['l2_name']}\n"
                    f"请严格按下面规格生成 {len(slots)} 道题，每个规格一题，顺序保持一致：\n"
                    f"{json.dumps(spec, ensure_ascii=False)}\n"
                    "标签tags至少包含年级、学科、一级知识点、二级知识点、tier和难度等级。"
                ),
            },
        ],
        "temperature": 0.5,
    }
    response = requests.post(
        f"{llm_service.base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {llm_service.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=llm_service.timeout_seconds,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    raw_items = llm_service._parse_json_from_llm(content)  # noqa: SLF001
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list) or len(raw_items) < len(slots):
        raise ValueError(f"LLM 返回题目数量不足：期望 {len(slots)}，实际 {len(raw_items) if isinstance(raw_items, list) else 0}")

    normalized: list[dict] = []
    used_indexes: set[int] = set()
    for index, slot in enumerate(slots):
        item = None
        for raw_index, raw_item in enumerate(raw_items):
            if raw_index in used_indexes or not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("tier", "")).strip() == slot["tier"]:
                item = raw_item
                used_indexes.add(raw_index)
                break
        if item is None:
            item = raw_items[index]
            used_indexes.add(index)
        if not isinstance(item, dict):
            raise ValueError("LLM 返回了非对象题目")
        normalized.append(_normalize_question_item(item, target, slot))
    return normalized


def _collect_targets(service: KnowledgeConfigService, school_ids: list[int], max_topics: int) -> list[dict]:
    targets: dict[str, dict] = {}
    for school_id in school_ids:
        textbooks = service.list_textbooks(school_id)
        for textbook in textbooks:
            topics = service.list_topics_for_school(school_id, textbook.id)
            topic_by_id = {topic.id: topic for topic in topics}
            for topic in topics:
                if topic.level != 2:
                    continue
                if not topic.parent_id:
                    continue
                parent = topic_by_id.get(topic.parent_id)
                if not parent:
                    continue
                targets[topic.id] = {
                    "school_id": school_id,
                    "textbook_id": textbook.id,
                    "grade_level": topic.grade_level or textbook.grade_level or "",
                    "subject": topic.subject or textbook.subject or "",
                    "l1_id": parent.id,
                    "l1_name": parent.name,
                    "l2_id": topic.id,
                    "l2_name": topic.name,
                }
    ordered = sorted(
        targets.values(),
        key=lambda item: (
            item["grade_level"],
            item["subject"],
            item["l1_name"],
            item["l2_name"],
            item["l2_id"],
        ),
    )
    if max_topics > 0:
        return ordered[:max_topics]
    return ordered


def _generate_items_with_retry(
    llm_service: LLMService,
    target: dict,
    slots: list[dict],
    strict_llm: bool,
) -> tuple[list[dict], str]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _call_llm_bundle(llm_service, target, slots, strict_llm=strict_llm), ""
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(min(2.0 * attempt, 5.0))
    return [], str(last_error) if last_error else "unknown error"


def _build_question_row(target: dict, generated: dict, question_status: str) -> QuestionBankORM:
    l2_id = target["l2_id"]
    return QuestionBankORM(
        external_id=f"boot_{l2_id}_{uuid.uuid4().hex[:10]}",
        knowledge_l1_id=target["l1_id"],
        knowledge_l2_id=l2_id,
        topic_id=l2_id,
        stem=generated["stem"],
        difficulty_level=generated["difficulty_level"],
        difficulty=generated["difficulty"],
        answer=generated["answer"],
        explanation=generated["explanation"],
        knowledge_tiers=generated["knowledge_tiers"],
        question_type=generated["question_type"],
        options=generated["options"],
        blank_count=generated["blank_count"],
        score_points=generated["score_points"],
        tags=generated["tags"],
        status=question_status,
        source=BOOTSTRAP_SOURCE,
    )


def _seed_questions_for_targets(
    llm_service: LLMService,
    targets: list[dict],
    questions_per_topic: int,
    strict_llm: bool,
    question_status: str,
    llm_workers: int,
) -> tuple[int, int, list[dict]]:
    if questions_per_topic <= 0:
        return 0, len(targets), []
    inserted = 0
    skipped = 0
    failures: list[dict] = []

    def add_failures(target: dict, slots: list[dict], reason: str) -> None:
        for slot in slots:
            failures.append(
                {
                    "topic_id": target["l2_id"],
                    "topic_name": target["l2_name"],
                    "grade_level": target["grade_level"],
                    "subject": target["subject"],
                    "tier": slot["tier"],
                    "reason": reason,
                }
            )

    llm_workers = max(1, int(llm_workers or 1))
    with sql_repository.session() as session:
        existing_rows = session.execute(
            select(QuestionBankORM.knowledge_l2_id, func.count())
            .where(QuestionBankORM.source == BOOTSTRAP_SOURCE)
            .group_by(QuestionBankORM.knowledge_l2_id)
        ).all()
        existing_count_by_l2 = {str(row[0]): int(row[1]) for row in existing_rows if row[0]}
        pending_jobs: list[tuple[int, dict, list[dict], int]] = []

        for index, target in enumerate(targets, start=1):
            l2_id = target["l2_id"]
            existing = int(existing_count_by_l2.get(l2_id, 0))
            if existing >= questions_per_topic:
                skipped += 1
                continue
            missing = questions_per_topic - existing
            slots = [_slot_for_index(existing + offset) for offset in range(missing)]
            pending_jobs.append((index, target, slots, missing))

        if llm_workers == 1:
            for index, target, slots, missing in pending_jobs:
                print(
                    f"[{index}/{len(targets)}] 生成 {target['grade_level']} {target['subject']} "
                    f"{target['l1_name']} > {target['l2_name']}，需补 {missing} 题"
                )
                generated_items, reason = _generate_items_with_retry(
                    llm_service, target, slots, strict_llm=strict_llm
                )
                if not generated_items:
                    add_failures(target, slots, reason)
                    print(f"  -> 生成失败：{target['l2_name']} {reason}")
                    continue
                for generated in generated_items:
                    session.add(_build_question_row(target, generated, question_status))
                    session.flush()
                    inserted += 1
        else:
            print(f"LLM 并发生成：workers={llm_workers}，topics={len(pending_jobs)}")
            with ThreadPoolExecutor(max_workers=llm_workers) as executor:
                future_map = {
                    executor.submit(_generate_items_with_retry, llm_service, target, slots, strict_llm): (
                        index,
                        target,
                        slots,
                        missing,
                    )
                    for index, target, slots, missing in pending_jobs
                }
                for completed, future in enumerate(as_completed(future_map), start=1):
                    index, target, slots, missing = future_map[future]
                    try:
                        generated_items, reason = future.result()
                    except Exception as exc:  # noqa: BLE001
                        generated_items, reason = [], str(exc)
                    if not generated_items:
                        add_failures(target, slots, reason)
                        print(
                            f"[完成 {completed}/{len(pending_jobs)} | 原序 {index}/{len(targets)}] "
                            f"失败 {target['grade_level']} {target['subject']} "
                            f"{target['l1_name']} > {target['l2_name']}：{reason}"
                        )
                        continue
                    for generated in generated_items:
                        session.add(_build_question_row(target, generated, question_status))
                        session.flush()
                        inserted += 1
                    print(
                        f"[完成 {completed}/{len(pending_jobs)} | 原序 {index}/{len(targets)}] "
                        f"{target['grade_level']} {target['subject']} "
                        f"{target['l1_name']} > {target['l2_name']}，生成 {len(generated_items)}/{missing} 题"
                    )

    return inserted, skipped, failures


def main() -> None:
    args = _parse_args()
    if args.questions_per_topic <= 0:
        raise ValueError("--questions-per-topic 必须 >= 1")

    init_database()
    repository = KnowledgeRepository(ROOT / "data" / "knowledge_graph.json")
    service = KnowledgeConfigService(repository)
    llm_service = LLMService() if args.generate_questions else None

    if args.generate_questions and args.strict_llm and llm_service and not llm_service.api_key:
        raise RuntimeError(
            "严格模式下未配置 OPENAI_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY，"
            "已中止重建以避免清库后无法回填题目。"
        )

    with sql_repository.session() as session:
        school_ids = [row.id for row in session.execute(select(SchoolORM).order_by(SchoolORM.id.asc())).scalars().all()]
        if not school_ids:
            print("No schools found, skip rebuild.")
            return

        # 全量清空题库与学习过程数据（保留账号、学校、班级、学生档案）
        session.execute(delete(QuestionBankORM))
        session.execute(delete(PracticeRecordORM))
        session.execute(delete(MistakeRecordORM))
        session.execute(delete(ReportRecordORM))
        session.execute(delete(StudentMasteryORM))
        session.execute(delete(ChatMessageORM))
        session.execute(delete(ChatSessionORM))
        session.execute(delete(KnowledgeChunkORM))
        session.execute(delete(KnowledgeDocumentORM))
        session.execute(delete(RagDocumentORM))
        session.execute(delete(RetrievalCaseORM))

        # 清空教材树并重建
        session.execute(delete(KnowledgeNodeORM))
        session.execute(delete(TextbookORM))

        classrooms = session.execute(select(ClassroomORM)).scalars().all()
        for classroom in classrooms:
            classroom.textbook_id = None

        profiles = session.execute(select(StudentProfileORM)).scalars().all()
        for profile in profiles:
            profile.textbook_id = None
            profile.target_topic_id = ""

    for school_id in school_ids:
        service.ensure_seeded(school_id)

    rebound_classrooms = 0
    rebound_profiles = 0
    mastery_seeded = 0

    with sql_repository.session() as session:
        for school_id in school_ids:
            books = service.list_textbooks(school_id)
            if not books:
                continue

            classroom_rows = session.execute(
                select(ClassroomORM).where(ClassroomORM.school_id == school_id)
            ).scalars().all()
            for classroom in classroom_rows:
                textbook_id = _pick_textbook_id(service, school_id, classroom.grade_level or "", "数学")
                classroom.textbook_id = textbook_id
                rebound_classrooms += 1

            profile_rows = session.execute(
                select(StudentProfileORM).where(StudentProfileORM.school_id == school_id)
            ).scalars().all()
            for profile in profile_rows:
                textbook_id = _pick_textbook_id(service, school_id, profile.grade_level or "", profile.target_subject or "数学")
                profile.textbook_id = textbook_id
                profile.target_topic_id = _first_l2_topic(service, school_id, textbook_id)
                rebound_profiles += 1

                topics = service.list_topics_for_school(school_id, textbook_id)
                for topic in topics:
                    if topic.level != 2:
                        continue
                    session.add(
                        StudentMasteryORM(
                            student_profile_id=profile.id,
                            topic_id=topic.id,
                            mastery=0.0,
                            practice_count=0,
                            correct_count=0,
                            last_practiced_at=None,
                            recent_errors=[],
                        )
                    )
                    mastery_seeded += 1

    generated_count = 0
    skipped_topics = 0
    failed_cases: list[dict] = []
    target_topics = 0
    if args.generate_questions:
        assert llm_service is not None
        targets = _collect_targets(service, school_ids, max_topics=args.max_topics)
        target_topics = len(targets)
        generated_count, skipped_topics, failed_cases = _seed_questions_for_targets(
            llm_service=llm_service,
            targets=targets,
            questions_per_topic=args.questions_per_topic,
            strict_llm=args.strict_llm,
            question_status=args.question_status,
            llm_workers=args.llm_workers,
        )

    print(
        "Rebuild done:",
        f"schools={len(school_ids)}",
        f"rebound_classrooms={rebound_classrooms}",
        f"rebound_profiles={rebound_profiles}",
        f"mastery_seeded={mastery_seeded}",
        f"question_targets={target_topics}",
        f"questions_generated={generated_count}",
        f"question_topics_skipped={skipped_topics}",
        f"question_generate_failures={len(failed_cases)}",
    )

    if failed_cases:
        print("Question generation failures:")
        for case in failed_cases[:30]:
            print(
                " -",
                case["grade_level"],
                case["subject"],
                case["topic_name"],
                f"[{case['tier']}]",
                "=>",
                case["reason"],
            )
        raise RuntimeError(f"生成失败 {len(failed_cases)} 条，请修复后重试。")


if __name__ == "__main__":
    main()
