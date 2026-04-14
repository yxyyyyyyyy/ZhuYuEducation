from __future__ import annotations

import os
from typing import Iterable, Sequence

import requests

from app.core.settings import load_environment


class DashScopeEmbeddingService:
    def __init__(self) -> None:
        load_environment()
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.region = os.getenv("DASHSCOPE_REGION", "intl").lower()
        self.embedding_model = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")
        self.embedding_dimensions = int(os.getenv("DASHSCOPE_EMBEDDING_DIMENSIONS", "1024"))
        self.rerank_model = os.getenv("DASHSCOPE_RERANK_MODEL", "qwen3-rerank" if self.region == "intl" else "gte-rerank-v2")
        self.embedding_url = os.getenv(
            "DASHSCOPE_EMBEDDING_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/embeddings"
            if self.region == "intl"
            else "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        )
        self.rerank_url = os.getenv(
            "DASHSCOPE_RERANK_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-api/v1/reranks"
            if self.region == "intl"
            else "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def embed_texts(self, texts: Sequence[str], text_type: str = "document") -> list[list[float]]:
        if not self.enabled:
            raise RuntimeError("DashScope API key is not configured")
        if not texts:
            return []
        payload = {
            "model": self.embedding_model,
            "input": list(texts),
            "dimensions": self.embedding_dimensions,
            "encoding_format": "float",
        }
        # Official docs note text_type is available in DashScope API for query/document distinction.
        payload["text_type"] = text_type
        response = requests.post(
            self.embedding_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data.get("data", [])]

    def rerank(self, query: str, documents: Sequence[str], top_n: int | None = None) -> list[float]:
        if not self.enabled:
            raise RuntimeError("DashScope API key is not configured")
        if not documents:
            return []

        if "compatible-api" in self.rerank_url:
            payload = {
                "model": self.rerank_model,
                "query": query,
                "documents": list(documents),
                "top_n": top_n or len(documents),
                "return_documents": False,
            }
        else:
            payload = {
                "model": self.rerank_model,
                "input": {"query": query, "documents": list(documents)},
                "parameters": {"top_n": top_n or len(documents), "return_documents": False},
            }

        response = requests.post(
            self.rerank_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results") or data.get("output", {}).get("results", [])
        indexed_scores = {result["index"]: float(result["relevance_score"]) for result in results}
        return [indexed_scores.get(index, 0.0) for index in range(len(documents))]
