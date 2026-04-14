from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from sqlalchemy import select

from app.core.database import ReportRecordORM
from app.domain.models import ReportRecordView, ReportRequest, ReviewTask, StudyReportResponse
from app.repositories.sql_repository import sql_repository
from app.services.knowledge_graph_service import KnowledgeGraphService


class ReportService:
    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self.graph_service = graph_service

    def generate(self, request: ReportRequest) -> StudyReportResponse:
        mastery_pairs = []
        for topic_id, mastery in request.current_mastery.items():
            topic = self.graph_service.get_topic(topic_id)
            mastery_pairs.append((topic.name, mastery.mastery))

        mastery_values = [value for _, value in mastery_pairs]
        overall = mean(mastery_values) if mastery_values else 0.0

        strong_topics = [name for name, value in mastery_pairs if value >= 0.8]
        weak_topics = [name for name, value in mastery_pairs if value < 0.6]

        recent_categories = [mistake.category.value for mistake in request.recent_mistakes]
        top_issue = recent_categories[0] if recent_categories else "暂无明显错误模式"
        diagnostic_summary = (
            f"{request.student_name} 当前整体掌握度为 {overall:.0%}。"
            f" 当前最需要关注的薄弱主题是 {', '.join(weak_topics[:3]) if weak_topics else '暂无'}，"
            f" 最近主要错误模式为 {top_issue}。"
        )

        next_actions = [
            "优先补强薄弱知识点的先修概念。",
            "每天完成 1 组自适应练习并复盘错题。",
            "把 AI 辅导中的关键提示整理成个人解题模板。",
        ]

        review_plan = self._build_review_plan(request)

        return StudyReportResponse(
            student_id=request.student_id,
            overall_mastery=round(overall, 2),
            strong_topics=strong_topics,
            weak_topics=weak_topics,
            diagnostic_summary=diagnostic_summary,
            next_actions=next_actions,
            review_plan=review_plan,
        )

    def _build_review_plan(self, request: ReportRequest) -> list[ReviewTask]:
        target_topic = self.graph_service.get_topic(request.target_topic_id)
        intervals = [1, 3, 7, 14]
        tasks = [
            ReviewTask(
                review_date=date.today() + timedelta(days=offset),
                topic_id=target_topic.id,
                activity=f"复习“{target_topic.name}”概念并完成 2 道针对题",
            )
            for offset in intervals
        ]
        return tasks

    def save_report(self, student_profile_id: int, report: StudyReportResponse) -> ReportRecordView:
        with sql_repository.session() as session:
            row = ReportRecordORM(
                student_profile_id=student_profile_id,
                overall_mastery=report.overall_mastery,
                diagnostic_summary=report.diagnostic_summary,
                strong_topics=report.strong_topics,
                weak_topics=report.weak_topics,
                next_actions=report.next_actions,
                review_plan=[
                    {
                        "review_date": item.review_date.isoformat(),
                        "topic_id": item.topic_id,
                        "activity": item.activity,
                    }
                    for item in report.review_plan
                ],
            )
            session.add(row)
            session.flush()
            return self._view(row)

    def latest(self, student_profile_id: int) -> ReportRecordView | None:
        with sql_repository.session() as session:
            row = sql_repository.latest_report(session, student_profile_id)
            return self._view(row) if row else None

    def list_reports(self, student_profile_id: int, limit: int = 20) -> list[ReportRecordView]:
        with sql_repository.session() as session:
            rows = session.execute(
                select(ReportRecordORM)
                .where(ReportRecordORM.student_profile_id == student_profile_id)
                .order_by(ReportRecordORM.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return [self._view(row) for row in rows]

    def _view(self, row: ReportRecordORM) -> ReportRecordView:
        return ReportRecordView(
            id=row.id,
            created_at=row.created_at,
            overall_mastery=row.overall_mastery,
            diagnostic_summary=row.diagnostic_summary,
            strong_topics=row.strong_topics or [],
            weak_topics=row.weak_topics or [],
            next_actions=row.next_actions or [],
            review_plan=[ReviewTask(**item) for item in (row.review_plan or [])],
        )
