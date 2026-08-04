"""
Optional Claude phrasing layer. The figures are always computed deterministically
(see analytics.py); Claude only turns them into a natural sentence. When no API
key is configured (CI/dev), `phrase_answer` returns None and the caller uses the
templated grounded summary — so the assistant works, and stays grounded, with or
without a live model.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Per the Anthropic guidance, default to the latest Opus; override via env.
DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = (
    "You are Mizan, an AI assistant for a Saudi accounting platform. "
    "Answer the user's question using ONLY the figures provided in the "
    "GROUNDED DATA block. Never invent, estimate, or alter any number — every "
    "figure in your answer must appear verbatim in the grounded data. Be concise "
    "(2-3 sentences). Do not add a disclaimer; the application appends one. "
    "If the user's language is Arabic, answer in Arabic."
)


def phrase_answer(question, grounded_summary, citations):
    """
    Return a Claude-phrased answer grounded in the given figures, or None to fall
    back to the templated summary (no key configured, or any API error).
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is pinned in requirements
        logger.warning("anthropic SDK not installed; using templated answer.")
        return None

    model = getattr(settings, "ANTHROPIC_MODEL", "") or DEFAULT_MODEL
    cited = "\n".join(f"- {c['label']}: {c['value']}" for c in citations)
    user_content = (
        f"Question: {question}\n\n"
        f"GROUNDED DATA (the only figures you may use):\n"
        f"{grounded_summary}\n{cited}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return text or None
    except Exception as exc:  # never let a model error break the endpoint
        logger.warning("Claude phrasing failed (%s); using templated answer.", exc)
        return None
