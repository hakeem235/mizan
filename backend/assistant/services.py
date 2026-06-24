"""Orchestrates: classify question → compute grounded figures → phrase answer."""

from . import intents
from . import claude_client

DISCLAIMER = (
    "This is informational only and not financial or tax advice. "
    "هذه معلومات عامة وليست استشارة مالية أو ضريبية."
)

HELP_TEXT = (
    "I can answer questions about your books — for example: your highest "
    "expenses last month, unpaid invoices older than 60 days, a cash-flow "
    "forecast for next quarter, or why revenue changed."
)


def answer_question(organization, question):
    """
    Return a grounded answer dict:
      {intent, answer, grounded, citations, disclaimer}

    `grounded` is True when the answer is backed by computed ledger figures.
    The `answer` is Claude-phrased when a key is configured, else the templated
    summary — either way the figures come from the deterministic analytics layer.
    """
    intent_name, fn = intents.classify(question)
    if fn is None:
        return {
            "intent": None,
            "answer": HELP_TEXT,
            "grounded": False,
            "citations": [],
            "disclaimer": DISCLAIMER,
        }

    result = fn(organization)
    summary = result["summary"]
    citations = result["citations"]

    phrased = claude_client.phrase_answer(question, summary, citations)
    answer = phrased or summary

    return {
        "intent": intent_name,
        "answer": answer,
        "grounded": True,
        "citations": citations,
        "disclaimer": DISCLAIMER,
    }
