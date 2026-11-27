# -*- coding: utf-8 -*-
"""HTTP reranker adapter for a SiliconFlow/BGE-compatible rerank endpoint."""

import math
import requests


class HTTPReranker:
    def __init__(self, base_url: str, api_key: str, model: str, http_post=requests.post):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_post = http_post

    @staticmethod
    def _document_text(candidate: dict) -> str:
        title = str(candidate.get("title") or candidate.get("name") or "").strip()
        body = str(
            candidate.get("description")
            or candidate.get("content")
            or candidate.get("text")
            or ""
        ).strip()
        return "\n".join(part for part in (title, body) if part)

    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None, timeout_seconds: float = 1.0) -> list[dict]:
        if cancellation:
            cancellation.throw_if_cancelled()
        if not candidates:
            return []

        response = self.http_post(
            self.base_url + "/rerank",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "query": query,
                "documents": [self._document_text(item) for item in candidates],
                "top_n": max(1, int(final_k)),
            },
            timeout=float(timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise ValueError("rerank response results must be a list")

        ranked = []
        seen_indices = set()
        for row in results:
            if not isinstance(row, dict):
                raise ValueError("rerank result must be an object")
            index = row.get("index")
            score = row.get("relevance_score", row.get("score"))
            if (isinstance(index, bool) or not isinstance(index, int)
                    or index < 0 or index >= len(candidates)):
                raise ValueError("rerank result index out of range")
            if index in seen_indices:
                raise ValueError("rerank result contains duplicate index")
            if (isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(float(score))):
                raise ValueError("rerank result score must be finite numeric")
            seen_indices.add(index)
            item = dict(candidates[index])
            item["rerank_score"] = float(score)
            ranked.append(item)
        return ranked[:max(0, int(final_k))]
