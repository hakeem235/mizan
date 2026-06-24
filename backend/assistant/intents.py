"""Map a free-text question to one of the supported analytics intents (AR/EN)."""

from . import analytics

# (intent, analytics callable, keyword list)
INTENTS = [
    ("highest_expenses", analytics.highest_expenses,
     ("highest expense", "biggest expense", "top expense", "most expensive",
      "largest expense", "spend most", "أعلى المصروفات", "أكبر مصروف", "مصروفات")),
    ("unpaid_invoices", analytics.unpaid_invoices_older_than,
     ("unpaid", "overdue", "outstanding invoice", "receivable", "aging", "owe",
      "not paid", "60 day", "فواتير غير مدفوعة", "متأخرة", "مستحقة", "الذمم")),
    ("cashflow_forecast", analytics.cashflow_forecast,
     ("cash flow", "cashflow", "forecast", "next quarter", "projection",
      "predict", "runway", "التدفق النقدي", "توقع", "الربع القادم")),
    ("revenue_change", analytics.explain_revenue_change,
     ("revenue", "sales change", "income change", "why did revenue", "explain revenue",
      "turnover", "الإيرادات", "تغير الإيراد", "المبيعات")),
]


def classify(question):
    """Return (intent_name, callable) or (None, None) if no intent matches."""
    text = (question or "").lower()
    for name, fn, keywords in INTENTS:
        if any(kw in text for kw in keywords):
            return name, fn
    return None, None
