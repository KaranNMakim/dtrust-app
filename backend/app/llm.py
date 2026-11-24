"""Single gateway for every Claude call (PRD 1.7).

Claude is used for bounded jobs only: intent classification, grounded answers,
score explanations and (optionally) semantic duplicate matching. It never sets a
score. If no ANTHROPIC_API_KEY is configured, or the SDK is missing, every caller
falls back to a deterministic path, so the product runs fully offline.
"""

from __future__ import annotations

import hashlib
import json
import logging

from .config import Settings

log = logging.getLogger("decision_trust.llm")

ANSWER_SYSTEM = """You are Decision Trust, a metric-governance assistant.
Answer ONLY from the JSON facts supplied. Never invent metrics, owners, numbers or lineage.
Every sentence you write must be supported by a fact whose id appears in `citations`.
If the facts do not answer the question, say so plainly.
Write for a business executive: short, specific, no jargon."""

EXPLAIN_SYSTEM = """Write a two-sentence explanation of a trust score for a business user.
Use only the evidence JSON. Sentence 1: the score and what it means. Sentence 2: the main reason, with its number."""

INTENT_SYSTEM = """Classify a question about enterprise metrics. Return JSON only:
{"intent": one of [resolve_metric, explain_score, find_conflicts, lineage, recommendation_trust, other],
 "term": the business term or metric name mentioned, or null}"""


class ClaudeGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        self._cache: dict[str, str] = {}
        if settings.anthropic_api_key:
            try:
                import anthropic  # type: ignore

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            except ImportError:
                log.warning("anthropic SDK not installed; running without Claude")

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _call(self, system: str, user: str, model: str, max_tokens: int = 600) -> str:
        key = hashlib.sha256(f"{model}|{system}|{user}".encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        resp = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        self._cache[key] = text
        return text

    def classify(self, question: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            raw = self._call(INTENT_SYSTEM, question, self.settings.claude_fast_model, 150)
            return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception as exc:  # noqa: BLE001
            log.warning("intent classification failed: %s", exc)
            return None

    def explain(self, ts, name: str) -> str:
        payload = json.dumps({
            "name": name, "score": ts.score, "zone": ts.zone,
            "components": [{"label": c.label, "raw": c.raw, "weight": c.weight, "evidence": c.evidence}
                           for c in ts.components],
            "penalties": ts.penalties, "cap": ts.cap,
        })
        return self._call(EXPLAIN_SYSTEM, payload, self.settings.claude_model, 200)

    def answer(self, question: str, facts: dict) -> str | None:
        if not self.enabled:
            return None
        try:
            return self._call(ANSWER_SYSTEM,
                              f"Question: {question}\n\nFacts:\n{json.dumps(facts, default=str)}",
                              self.settings.claude_model, 400)
        except Exception as exc:  # noqa: BLE001
            log.warning("answer generation failed: %s", exc)
            return None
