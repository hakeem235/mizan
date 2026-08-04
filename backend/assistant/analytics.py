"""
Deterministic analytics that answer the assistant's questions directly from the
ledger. Every number the assistant states comes from here — the LLM only phrases
these figures, it never computes or invents them (Issue 7.3 grounding rule).

All functions are org-scoped (tenant boundary) and return a dict with:
  - `summary`: a templated, grounded sentence (used as the fallback answer and
    as the source-of-truth the LLM must not contradict)
  - `citations`: [{label, value}] — the underlying figures the answer cites
  - `data`: structured values for the LLM prompt
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta
from decimal import Decimal

from ledger.models import Account, JournalEntry, JournalLine
from ledger import services

ZERO = Decimal("0")
TWO = Decimal("0.01")


def _money(org, amount):
    return f"{org.base_currency} {Decimal(amount).quantize(TWO):,}"


def _last_complete_month(as_of: date):
    first_this = as_of.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


# --------------------------------------------------------------------------- #
# 1. Highest expenses last month
# --------------------------------------------------------------------------- #
def highest_expenses(org, *, as_of=None, top_n=3):
    as_of = as_of or date.today()
    start, end = _last_complete_month(as_of)

    rows = []
    for acc in org.accounts.filter(type=Account.Type.EXPENSE):
        bal = services.account_balance(acc, start=start, end=end)
        if bal > 0:
            rows.append((acc, bal))
    rows.sort(key=lambda r: r[1], reverse=True)
    top = rows[:top_n]

    citations = [{"label": acc.name, "value": _money(org, bal)} for acc, bal in top]
    if top:
        lead = ", ".join(f"{acc.name} ({_money(org, bal)})" for acc, bal in top)
        summary = (
            f"Your highest expenses in {start.strftime('%B %Y')} were: {lead}."
        )
    else:
        summary = f"No expenses were recorded in {start.strftime('%B %Y')}."

    return {
        "summary": summary,
        "citations": citations,
        "data": {
            "period": start.strftime("%B %Y"),
            "expenses": [{"account": a.name, "amount": str(b)} for a, b in top],
        },
    }


# --------------------------------------------------------------------------- #
# 2. Unpaid invoices older than N days (AR aging via FIFO)
# --------------------------------------------------------------------------- #
def unpaid_invoices_older_than(org, *, days=60, as_of=None):
    """
    Approximate invoice-level aging from the AR control account: treat AR debits
    as invoices and AR credits as payments, then apply payments FIFO to the
    oldest open invoices. Invoice-level records arrive in Phase 8; until then the
    AR sub-ledger is reconstructed from journal activity.
    """
    as_of = as_of or date.today()
    cutoff = as_of - timedelta(days=days)

    ar_accounts = list(org.accounts.filter(role=Account.Role.ACCOUNTS_RECEIVABLE))
    open_invoices = deque()  # (date, remaining_amount) oldest first
    payments_total = ZERO

    lines = (
        JournalLine.objects.filter(
            account__in=ar_accounts, entry__status=JournalEntry.Status.POSTED
        )
        .select_related("entry")
        .order_by("entry__date", "id")
    )
    for ln in lines:
        rate = ln.entry.fx_rate
        if ln.debit > 0:  # invoice raised
            open_invoices.append([ln.entry.date, (ln.debit * rate).quantize(TWO)])
        if ln.credit > 0:  # payment received → apply FIFO to oldest invoices
            pay = (ln.credit * rate).quantize(TWO)
            payments_total += pay
            while pay > 0 and open_invoices:
                inv = open_invoices[0]
                applied = min(pay, inv[1])
                inv[1] -= applied
                pay -= applied
                if inv[1] <= 0:
                    open_invoices.popleft()

    overdue = sum((amt for d, amt in open_invoices if d <= cutoff), ZERO)
    overdue_count = sum(1 for d, amt in open_invoices if d <= cutoff and amt > 0)
    total_open = sum((amt for d, amt in open_invoices), ZERO)

    summary = (
        f"You have {_money(org, overdue)} in receivables older than {days} days "
        f"across {overdue_count} invoice(s). Total outstanding receivables: "
        f"{_money(org, total_open)}."
    )
    return {
        "summary": summary,
        "citations": [
            {"label": f"Overdue >{days}d", "value": _money(org, overdue)},
            {"label": "Total receivables", "value": _money(org, total_open)},
        ],
        "data": {
            "days": days,
            "overdue_amount": str(overdue.quantize(TWO)),
            "overdue_count": overdue_count,
            "total_open": str(total_open.quantize(TWO)),
        },
    }


# --------------------------------------------------------------------------- #
# 3. Cash-flow forecast — next quarter (heuristic, not a trained model)
# --------------------------------------------------------------------------- #
def cashflow_forecast(org, *, as_of=None, lookback_months=6):
    as_of = as_of or date.today()
    cash_accounts = list(org.accounts.filter(role=Account.Role.CASH))

    monthly = []
    cursor_first, _ = _last_complete_month(as_of)
    for i in range(lookback_months):
        y, m = cursor_first.year, cursor_first.month - i
        while m <= 0:
            m += 12
            y -= 1
        m_start = date(y, m, 1)
        nxt = date(y + (m // 12), (m % 12) + 1, 1)
        m_end = nxt - timedelta(days=1)
        net = sum(
            (services.account_balance(a, start=m_start, end=m_end) for a in cash_accounts),
            ZERO,
        )
        monthly.append(net)

    avg = (sum(monthly, ZERO) / Decimal(len(monthly))).quantize(TWO) if monthly else ZERO
    projected_quarter = (avg * 3).quantize(TWO)

    summary = (
        f"Based on the trailing {lookback_months} months, average monthly net cash "
        f"flow is {_money(org, avg)}. Projected net cash flow for next quarter is "
        f"approximately {_money(org, projected_quarter)} (a heuristic estimate from "
        f"recent trends, not a guarantee)."
    )
    return {
        "summary": summary,
        "citations": [
            {"label": "Avg monthly net cash flow", "value": _money(org, avg)},
            {"label": "Projected next quarter", "value": _money(org, projected_quarter)},
        ],
        "data": {
            "avg_monthly": str(avg),
            "projected_quarter": str(projected_quarter),
            "method": f"mean of trailing {lookback_months} months × 3",
        },
    }


# --------------------------------------------------------------------------- #
# 4. Explain a revenue change (latest complete month vs prior)
# --------------------------------------------------------------------------- #
def explain_revenue_change(org, *, as_of=None):
    as_of = as_of or date.today()
    cur_start, cur_end = _last_complete_month(as_of)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)

    cur = services._sum_type(org, Account.Type.REVENUE, start=cur_start, end=cur_end)
    prev = services._sum_type(org, Account.Type.REVENUE, start=prev_start, end=prev_end)
    delta = (cur - prev).quantize(TWO)
    pct = (delta / prev * 100).quantize(TWO) if prev > 0 else None

    direction = "increased" if delta > 0 else "decreased" if delta < 0 else "was unchanged"
    pct_str = f" ({pct}%)" if pct is not None else ""
    summary = (
        f"Revenue {direction} from {_money(org, prev)} in "
        f"{prev_start.strftime('%B %Y')} to {_money(org, cur)} in "
        f"{cur_start.strftime('%B %Y')}, a change of {_money(org, delta)}{pct_str}."
    )
    return {
        "summary": summary,
        "citations": [
            {"label": prev_start.strftime("%B %Y"), "value": _money(org, prev)},
            {"label": cur_start.strftime("%B %Y"), "value": _money(org, cur)},
            {"label": "Change", "value": _money(org, delta)},
        ],
        "data": {
            "previous": str(prev),
            "current": str(cur),
            "delta": str(delta),
            "pct": str(pct) if pct is not None else None,
        },
    }
