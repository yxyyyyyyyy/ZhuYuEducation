from __future__ import annotations

from app.domain.models import CitationEvidence, TutorMode, TutorRequest, TutorResponse
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.llm_service import LLMService
from app.services.rag_service import RagService


class TutorService:
    def __init__(
        self,
        graph_service: KnowledgeGraphService,
        rag_service: RagService,
        llm_service: LLMService,
    ) -> None:
        self.graph_service = graph_service
        self.rag_service = rag_service
        self.llm_service = llm_service

    def respond(self, request: TutorRequest) -> TutorResponse:
        topic = self.graph_service.get_topic(request.topic_id)
        mastery = request.current_mastery.get(request.topic_id)
        mastery_value = mastery.mastery if mastery else 0.0

        if mastery_value < 0.45:
            mode = TutorMode.direct
            response = (
                f"我们先不急着做题，先把“{topic.name}”的核心概念钉牢。"
                f" 你先记住：{topic.learning_objectives[0]}。"
                f" 常见误区是：{topic.common_mistakes[0]}。"
            )
            next_step = "先看概念讲解，再完成两道基础题。"
        elif request.difficulty_signal > 0.75:
            mode = TutorMode.example_based
            response = (
                f"这题难度偏高，我们用例题迁移。"
                f" 先找出与“{topic.name}”最相关的规则，再套到一个简单例子里。"
                f" 提示：{topic.tutoring_tips[0]}"
            )
            next_step = "按例题模板复现一次，再独立尝试原题。"
        else:
            mode = TutorMode.socratic
            fallback_text = (
                f"先别急着看答案。关于“{topic.name}”，你能先说出已知条件、目标量，"
                f"以及要用的第一个规则吗？如果只能选一步，你会先做哪一步？"
            )
            next_step = "回答上面两个问题后，再进入下一轮追问。"
            evidence = self.rag_service.retrieve(request.topic_id, request.question, limit=3)
            response = self.llm_service.generate_tutor_reply(
                topic_name=topic.name,
                mode=mode,
                user_message=request.question,
                evidence=evidence,
                fallback_text=fallback_text,
            )
            return TutorResponse(
                mode=mode,
                response=response,
                next_step=next_step,
                evidence=[self._citation_view(doc) for doc in evidence],
            )

        evidence = self.rag_service.retrieve(request.topic_id, request.question, limit=3)
        response = self.llm_service.generate_tutor_reply(
            topic_name=topic.name,
            mode=mode,
            user_message=request.question,
            evidence=evidence,
            fallback_text=response,
        )
        return TutorResponse(
            mode=mode,
            response=response,
            next_step=next_step,
            evidence=[self._citation_view(doc) for doc in evidence],
        )

    def _citation_view(self, doc) -> CitationEvidence:
        return CitationEvidence(
            document_title=doc.title,
            source_name=doc.source_name,
            doc_type=doc.doc_type,
            topic_id=doc.topic_id,
            snippet=doc.snippet,
            score=round(doc.score, 4),
        )
