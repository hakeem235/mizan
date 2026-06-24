"""
Financial reports — all derived from the ledger so they reconcile by construction.

Each report function returns a Report dict:
  {
    "key", "title", "subtitle",
    "columns": [{"label": str, "numeric": bool}],
    "rows": [{"cells": [...], "style": "normal|section|subtotal|total"}],
    "meta": {...},           # report-specific extras (e.g. balanced flags)
  }

Numeric cells hold Decimal (or None); label cells hold str. The view serializes
Decimals to strings; the exporters format them per the xlsx/pdf SKILLS rules.
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta
from decimal import Decimal

from ledger.models import Account, JournalEntry, JournalLine
from ledger import services as ledger

ZERO = Decimal("0")
TWO = Decimal("0.01")
VAT_RATE = Decimal("0.15")


def _raw_balance(account, *, start=None, end=None):
    """Signed (debit − credit) balance in base currency. Posted entries only."""
    qs = JournalLine.objects.filter(
        account=account, entry__status=JournalEntry.Status.POSTED
    )
    if start:
        qs = qs.filter(entry__date__gte=start)
    if end:
        qs = qs.filter(entry__date__lte=end)
    total = ZERO
    for debit, credit, rate in qs.values_list("debit", "credit", "entry__fx_rate"):
        total += (debit - credit) * rate
    return total.quantize(TWO)


def _period_label(org, start, end):
    bits = [org.name]
    if start and end:
        bits.append(f"{start.isoformat()} → {end.isoformat()}")
    elif end:
        bits.append(f"As of {end.isoformat()}")
    bits.append(org.base_currency)
    return " · ".join(bits)


# --------------------------------------------------------------------------- #
# Trial Balance
# --------------------------------------------------------------------------- #
def trial_balance(org, *, end=None):
    end = end or date.today()
    rows = []
    total_debit = ZERO
    total_credit = ZERO
    for acc in org.accounts.order_by("code"):
        raw = _raw_balance(acc, end=end)
        if raw == 0:
            continue
        debit = raw if raw > 0 else ZERO
        credit = -raw if raw < 0 else ZERO
        total_debit += debit
        total_credit += credit
        rows.append({"cells": [f"{acc.code}  {acc.name}", debit or None, credit or None],
                     "style": "normal"})
    rows.append({"cells": ["Total", total_debit, total_credit], "style": "total"})
    return {
        "key": "trial_balance",
        "title": "Trial Balance",
        "subtitle": _period_label(org, None, end),
        "columns": [{"label": "Account", "numeric": False},
                    {"label": "Debit", "numeric": True},
                    {"label": "Credit", "numeric": True}],
        "rows": rows,
        "meta": {"balanced": total_debit == total_credit,
                 "total_debit": str(total_debit), "total_credit": str(total_credit)},
    }


# --------------------------------------------------------------------------- #
# Profit & Loss (Income Statement)
# --------------------------------------------------------------------------- #
def profit_and_loss(org, *, start=None, end=None):
    end = end or date.today()
    rows = []

    revenue_total = ZERO
    rows.append({"cells": ["Revenue", None], "style": "section"})
    for acc in org.accounts.filter(type=Account.Type.REVENUE).order_by("code"):
        bal = ledger.account_balance(acc, start=start, end=end)
        if bal:
            revenue_total += bal
            rows.append({"cells": [f"  {acc.name}", bal], "style": "normal"})
    rows.append({"cells": ["Total Revenue", revenue_total], "style": "subtotal"})

    expense_total = ZERO
    rows.append({"cells": ["Expenses", None], "style": "section"})
    for acc in org.accounts.filter(type=Account.Type.EXPENSE).order_by("code"):
        bal = ledger.account_balance(acc, start=start, end=end)
        if bal:
            expense_total += bal
            rows.append({"cells": [f"  {acc.name}", bal], "style": "normal"})
    rows.append({"cells": ["Total Expenses", expense_total], "style": "subtotal"})

    net = (revenue_total - expense_total).quantize(TWO)
    rows.append({"cells": ["Net Profit", net], "style": "total"})
    return {
        "key": "profit_and_loss",
        "title": "Profit & Loss Statement",
        "subtitle": _period_label(org, start, end),
        "columns": [{"label": "", "numeric": False}, {"label": "Amount", "numeric": True}],
        "rows": rows,
        "meta": {"revenue": str(revenue_total), "expenses": str(expense_total),
                 "net_profit": str(net)},
    }


# --------------------------------------------------------------------------- #
# Balance Sheet
# --------------------------------------------------------------------------- #
def balance_sheet(org, *, end=None):
    end = end or date.today()
    rows = []

    assets = ZERO
    rows.append({"cells": ["Assets", None], "style": "section"})
    for acc in org.accounts.filter(type=Account.Type.ASSET).order_by("code"):
        bal = ledger.account_balance(acc, end=end)
        if bal:
            assets += bal
            rows.append({"cells": [f"  {acc.name}", bal], "style": "normal"})
    rows.append({"cells": ["Total Assets", assets], "style": "subtotal"})

    liabilities = ZERO
    rows.append({"cells": ["Liabilities", None], "style": "section"})
    for acc in org.accounts.filter(type=Account.Type.LIABILITY).order_by("code"):
        bal = ledger.account_balance(acc, end=end)
        if bal:
            liabilities += bal
            rows.append({"cells": [f"  {acc.name}", bal], "style": "normal"})
    rows.append({"cells": ["Total Liabilities", liabilities], "style": "subtotal"})

    equity = ZERO
    rows.append({"cells": ["Equity", None], "style": "section"})
    for acc in org.accounts.filter(type=Account.Type.EQUITY).order_by("code"):
        bal = ledger.account_balance(acc, end=end)
        if bal:
            equity += bal
            rows.append({"cells": [f"  {acc.name}", bal], "style": "normal"})
    # Current earnings (cumulative revenue − expenses) close into equity.
    revenue = ledger._sum_type(org, Account.Type.REVENUE, end=end)
    expenses = ledger._sum_type(org, Account.Type.EXPENSE, end=end)
    earnings = (revenue - expenses).quantize(TWO)
    rows.append({"cells": ["  Current Earnings", earnings], "style": "normal"})
    equity_total = (equity + earnings).quantize(TWO)
    rows.append({"cells": ["Total Equity", equity_total], "style": "subtotal"})

    le_total = (liabilities + equity_total).quantize(TWO)
    rows.append({"cells": ["Total Liabilities + Equity", le_total], "style": "total"})
    return {
        "key": "balance_sheet",
        "title": "Balance Sheet",
        "subtitle": _period_label(org, None, end),
        "columns": [{"label": "", "numeric": False}, {"label": "Amount", "numeric": True}],
        "rows": rows,
        "meta": {"assets": str(assets), "liabilities_plus_equity": str(le_total),
                 "balanced": assets == le_total},
    }


# --------------------------------------------------------------------------- #
# Cash Flow Statement (movement on cash/bank accounts)
# --------------------------------------------------------------------------- #
def cash_flow(org, *, start=None, end=None):
    end = end or date.today()
    cash_accounts = list(org.accounts.filter(role=Account.Role.CASH))

    opening = ZERO
    if start:
        day_before = start - timedelta(days=1)
        opening = sum((ledger.account_balance(a, end=day_before) for a in cash_accounts), ZERO)
    net_change = sum(
        (ledger.account_balance(a, start=start, end=end) for a in cash_accounts), ZERO
    )
    closing = (opening + net_change).quantize(TWO)

    rows = [
        {"cells": ["Opening cash balance", opening], "style": "normal"},
        {"cells": ["Net cash flow for period", net_change], "style": "subtotal"},
        {"cells": ["Closing cash balance", closing], "style": "total"},
    ]
    return {
        "key": "cash_flow",
        "title": "Cash Flow Statement",
        "subtitle": _period_label(org, start, end),
        "columns": [{"label": "", "numeric": False}, {"label": "Amount", "numeric": True}],
        "rows": rows,
        "meta": {"opening": str(opening), "net_change": str(net_change.quantize(TWO)),
                 "closing": str(closing)},
    }


# --------------------------------------------------------------------------- #
# General Ledger
# --------------------------------------------------------------------------- #
def general_ledger(org, *, start=None, end=None):
    end = end or date.today()
    rows = []
    for acc in org.accounts.order_by("code"):
        lines = (
            JournalLine.objects.filter(
                account=acc, entry__status=JournalEntry.Status.POSTED
            )
            .select_related("entry")
            .order_by("entry__date", "id")
        )
        if start:
            lines = lines.filter(entry__date__gte=start)
        lines = lines.filter(entry__date__lte=end)
        lines = list(lines)
        if not lines:
            continue
        rows.append({"cells": [f"{acc.code}  {acc.name}", None, None, None],
                     "style": "section"})
        running = ZERO
        for ln in lines:
            d = (ln.debit * ln.entry.fx_rate).quantize(TWO)
            c = (ln.credit * ln.entry.fx_rate).quantize(TWO)
            running += d - c
            rows.append({"cells": [f"  {ln.entry.date}  {ln.entry.description}",
                                   d or None, c or None, running.quantize(TWO)],
                         "style": "normal"})
    return {
        "key": "general_ledger",
        "title": "General Ledger",
        "subtitle": _period_label(org, start, end),
        "columns": [{"label": "Account / Entry", "numeric": False},
                    {"label": "Debit", "numeric": True},
                    {"label": "Credit", "numeric": True},
                    {"label": "Balance", "numeric": True}],
        "rows": rows,
        "meta": {},
    }


# --------------------------------------------------------------------------- #
# AR / AP Aging (FIFO open items, bucketed)
# --------------------------------------------------------------------------- #
def _open_items(org, role, *, as_of):
    """FIFO-reconstructed open items for an AR/AP control account: [(date, amount)]."""
    accounts = list(org.accounts.filter(role=role))
    debit_is_open = role == Account.Role.ACCOUNTS_RECEIVABLE  # AR: invoice = debit
    items = deque()
    lines = (
        JournalLine.objects.filter(
            account__in=accounts, entry__status=JournalEntry.Status.POSTED,
            entry__date__lte=as_of,
        )
        .select_related("entry")
        .order_by("entry__date", "id")
    )
    for ln in lines:
        rate = ln.entry.fx_rate
        opening = (ln.debit if debit_is_open else ln.credit) * rate
        settling = (ln.credit if debit_is_open else ln.debit) * rate
        if opening > 0:
            items.append([ln.entry.date, opening.quantize(TWO)])
        if settling > 0:
            pay = settling.quantize(TWO)
            while pay > 0 and items:
                head = items[0]
                applied = min(pay, head[1])
                head[1] -= applied
                pay -= applied
                if head[1] <= 0:
                    items.popleft()
    return [(d, amt) for d, amt in items if amt > 0]


def _aging(org, role, title, key, *, as_of=None):
    as_of = as_of or date.today()
    buckets = {"0-30": ZERO, "31-60": ZERO, "61-90": ZERO, "90+": ZERO}
    for d, amt in _open_items(org, role, as_of=as_of):
        age = (as_of - d).days
        if age <= 30:
            buckets["0-30"] += amt
        elif age <= 60:
            buckets["31-60"] += amt
        elif age <= 90:
            buckets["61-90"] += amt
        else:
            buckets["90+"] += amt
    total = sum(buckets.values(), ZERO)
    rows = [{"cells": [label, amt or None], "style": "normal"}
            for label, amt in buckets.items()]
    rows.append({"cells": ["Total", total], "style": "total"})
    return {
        "key": key,
        "title": title,
        "subtitle": _period_label(org, None, as_of),
        "columns": [{"label": "Age bucket (days)", "numeric": False},
                    {"label": "Amount", "numeric": True}],
        "rows": rows,
        "meta": {k: str(v.quantize(TWO)) for k, v in buckets.items()} | {"total": str(total.quantize(TWO))},
    }


def ar_aging(org, *, as_of=None):
    return _aging(org, Account.Role.ACCOUNTS_RECEIVABLE,
                  "Accounts Receivable Aging", "ar_aging", as_of=as_of)


def ap_aging(org, *, as_of=None):
    return _aging(org, Account.Role.ACCOUNTS_PAYABLE,
                  "Accounts Payable Aging", "ap_aging", as_of=as_of)


# --------------------------------------------------------------------------- #
# Saudi VAT report (ZATCA-aligned)
# --------------------------------------------------------------------------- #
def _quarter_bounds(d):
    q = (d.month - 1) // 3
    start = date(d.year, q * 3 + 1, 1)
    end_month = q * 3 + 3
    if end_month == 12:
        end = date(d.year, 12, 31)
    else:
        end = date(d.year, end_month + 1, 1) - timedelta(days=1)
    return start, end


def vat_report(org, *, start=None, end=None, as_of=None):
    as_of = as_of or date.today()
    if not (start and end):
        start, end = _quarter_bounds(as_of)

    output_vat = ledger._sum_role(org, Account.Role.VAT_OUTPUT, start=start, end=end)
    input_vat = ledger._sum_role(org, Account.Role.VAT_INPUT, start=start, end=end)
    # Standard-rated net sales implied by the 15% output VAT collected.
    standard_sales = (output_vat / VAT_RATE).quantize(TWO) if output_vat else ZERO
    net_vat = (output_vat - input_vat).quantize(TWO)

    # ZATCA quarterly filing is due by the end of the month following the quarter.
    filing_due = (end.replace(day=28) + timedelta(days=35)).replace(day=1) - timedelta(days=1)
    days_left = (filing_due - as_of).days

    rows = [
        {"cells": ["Standard-rated sales (15%)", standard_sales], "style": "normal"},
        {"cells": ["Zero-rated sales", ZERO], "style": "normal"},
        {"cells": ["Exempt sales", ZERO], "style": "normal"},
        {"cells": ["Output VAT (collected)", output_vat], "style": "subtotal"},
        {"cells": ["Input VAT (recoverable)", input_vat], "style": "subtotal"},
        {"cells": ["Net VAT payable", net_vat], "style": "total"},
    ]
    return {
        "key": "vat_report",
        "title": "VAT Return (ZATCA)",
        "subtitle": _period_label(org, start, end),
        "columns": [{"label": "", "numeric": False}, {"label": "Amount", "numeric": True}],
        "rows": rows,
        "meta": {
            "standard_rated_sales": str(standard_sales),
            "output_vat": str(output_vat), "input_vat": str(input_vat),
            "net_vat_payable": str(net_vat),
            "filing_due": filing_due.isoformat(), "days_left": days_left,
            "vat_number": org.vat_number,
        },
    }


REPORTS = {
    "trial_balance": trial_balance,
    "profit_and_loss": profit_and_loss,
    "balance_sheet": balance_sheet,
    "cash_flow": cash_flow,
    "general_ledger": general_ledger,
    "ar_aging": ar_aging,
    "ap_aging": ap_aging,
    "vat_report": vat_report,
}
