"""
Accounting business logic — kept out of views/serializers so it can be unit
tested directly. This is money: every function here is deterministic and
exact (Decimal throughout), and double-entry balance is enforced, not assumed.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Sum

from .models import Account, JournalEntry, JournalLine, Transaction

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0")

# Saudi standard VAT rate.
VAT_STANDARD_RATE = Decimal("0.15")


# --------------------------------------------------------------------------- #
# Double-entry posting
# --------------------------------------------------------------------------- #
def post_journal_entry(*, organization, date, lines, description="", currency=None,
                       fx_rate=Decimal("1"), status=JournalEntry.Status.POSTED):
    """
    Create a balanced journal entry atomically.

    `lines` is an iterable of dicts: {"account": Account, "debit": Decimal,
    "credit": Decimal}. Raises ValidationError (and writes nothing) when the
    entry is unbalanced, empty, references another org's account, or a line is
    not strictly one-sided.
    """
    currency = currency or organization.base_currency
    lines = list(lines)
    if not lines:
        raise ValidationError("A journal entry must have at least two lines.")

    total_debit = ZERO
    total_credit = ZERO
    for ln in lines:
        account = ln["account"]
        if account.organization_id != organization.id:
            raise ValidationError(
                f"Account {account.code} belongs to another organization."
            )
        debit = Decimal(ln.get("debit") or 0)
        credit = Decimal(ln.get("credit") or 0)
        if debit < 0 or credit < 0:
            raise ValidationError("Debit and credit amounts must be non-negative.")
        if (debit > 0) == (credit > 0):
            # Both zero, or both non-zero — a line is exactly one side.
            raise ValidationError(
                "Each line must have either a debit or a credit, not both/neither."
            )
        total_debit += debit
        total_credit += credit

    if total_debit.quantize(TWO_PLACES) != total_credit.quantize(TWO_PLACES):
        raise ValidationError(
            f"Unbalanced entry: debits {total_debit} ≠ credits {total_credit}."
        )

    with db_transaction.atomic():
        entry = JournalEntry.objects.create(
            organization=organization,
            date=date,
            description=description,
            currency=currency,
            fx_rate=Decimal(fx_rate),
            status=status,
        )
        JournalLine.objects.bulk_create(
            JournalLine(
                entry=entry,
                account=ln["account"],
                debit=Decimal(ln.get("debit") or 0),
                credit=Decimal(ln.get("credit") or 0),
            )
            for ln in lines
        )
    return entry


# --------------------------------------------------------------------------- #
# Balances (in the org's base currency)
# --------------------------------------------------------------------------- #
def account_balance(account, *, start=None, end=None):
    """
    Signed balance for an account in base currency, as a positive number on its
    normal side. Only POSTED entries count. fx_rate converts each line to base.
    """
    qs = JournalLine.objects.filter(
        account=account, entry__status=JournalEntry.Status.POSTED
    )
    if start:
        qs = qs.filter(entry__date__gte=start)
    if end:
        qs = qs.filter(entry__date__lte=end)

    total = ZERO
    for debit, credit, rate in qs.values_list("debit", "credit", "entry__fx_rate"):
        delta = (debit - credit) * rate
        total += delta

    # Debit-normal accounts report positive when debits exceed credits; flip for
    # credit-normal accounts so a normal balance is reported as positive.
    if account.normal_balance == "credit":
        total = -total
    return total.quantize(TWO_PLACES)


def _sum_role(organization, role, **kwargs):
    total = ZERO
    for acc in organization.accounts.filter(role=role):
        total += account_balance(acc, **kwargs)
    return total


def _sum_type(organization, acct_type, **kwargs):
    total = ZERO
    for acc in organization.accounts.filter(type=acct_type):
        total += account_balance(acc, **kwargs)
    return total


# --------------------------------------------------------------------------- #
# AI bookkeeping foundations — heuristic, deterministic, testable.
# Claude-powered reasoning lands in Issue 7.3; these rules are the baseline.
# --------------------------------------------------------------------------- #
CATEGORY_RULES = [
    ("Payroll", ("payroll", "salary", "salaries", "wages", "راتب", "رواتب")),
    ("Rent", ("rent", "lease", "إيجار")),
    ("Utilities", ("electric", "water", "internet", "stc", "utility", "كهرباء", "مياه")),
    ("Software & Subscriptions", ("subscription", "saas", "software", "github",
                                  "aws", "google", "microsoft", "اشتراك")),
    ("Inventory & COGS", ("inventory", "stock", "supplier", "wholesale", "مخزون", "مورد")),
    ("Travel", ("flight", "hotel", "uber", "careem", "taxi", "travel", "طيران", "فندق")),
    ("Bank Fees", ("fee", "charge", "commission", "رسوم", "عمولة")),
    ("Sales Revenue", ("invoice paid", "payment received", "sale", "pos", "مبيعات", "دفعة")),
    ("Marketing", ("ads", "advertis", "marketing", "campaign", "تسويق", "إعلان")),
]


def categorize_transaction(description):
    """
    Return (category, confidence) for a transaction description using keyword
    rules. Confidence is high (0.95) for a keyword hit, low (0.30) otherwise.
    """
    text = (description or "").lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return category, Decimal("0.95")
    return "Uncategorized", Decimal("0.30")


_WS = re.compile(r"\s+")


def transaction_fingerprint(organization_id, date, amount, description):
    """Stable hash of the dedup-significant fields (normalized description)."""
    norm = _WS.sub(" ", (description or "").strip().lower())
    raw = f"{organization_id}|{date}|{Decimal(amount).quantize(TWO_PLACES)}|{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ingest_transaction(*, organization, date, description, amount, currency=None):
    """
    Create a Transaction with AI categorization + duplicate detection applied.
    A transaction matching an existing fingerprint in the same org is flagged as
    a duplicate (not silently merged) and pointed at the original.
    """
    currency = currency or organization.base_currency
    fp = transaction_fingerprint(organization.id, date, amount, description)
    category, confidence = categorize_transaction(description)

    original = (
        Transaction.objects.filter(organization=organization, fingerprint=fp)
        .order_by("id")
        .first()
    )

    txn = Transaction(
        organization=organization,
        date=date,
        description=description,
        amount=Decimal(amount),
        currency=currency,
        category=category,
        confidence=confidence,
        fingerprint=fp,
    )
    if original is not None:
        txn.is_duplicate = True
        txn.duplicate_of = original
        txn.status = Transaction.Status.FLAGGED
    else:
        txn.status = (
            Transaction.Status.CATEGORIZED
            if category != "Uncategorized"
            else Transaction.Status.UNCATEGORIZED
        )
    txn.save()
    return txn


# --------------------------------------------------------------------------- #
# Dashboard aggregates — all computed from the ledger, in base currency.
# --------------------------------------------------------------------------- #
def _month_window(d: date):
    start = d.replace(day=1)
    if start.month == 12:
        nxt = start.replace(year=start.year + 1, month=1)
    else:
        nxt = start.replace(month=start.month + 1)
    return start, nxt


def _shift_month(d: date, months_back: int):
    y, m = d.year, d.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def dashboard_summary(organization, *, as_of=None, chart_months=8):
    as_of = as_of or date.today()
    period_start, period_end_excl = _month_window(as_of)
    period_end = period_end_excl  # __lt for exclusivity handled via lte below
    # Use inclusive end = last day of month by passing lte period_end - 1 day.
    from datetime import timedelta

    last_day = period_end_excl - timedelta(days=1)

    revenue = _sum_type(organization, Account.Type.REVENUE, start=period_start, end=last_day)
    expenses = _sum_type(organization, Account.Type.EXPENSE, start=period_start, end=last_day)
    net_cash_flow = _sum_role(organization, Account.Role.CASH, start=period_start, end=last_day)

    outstanding_invoices = _sum_role(organization, Account.Role.ACCOUNTS_RECEIVABLE)
    vat_payable = (
        _sum_role(organization, Account.Role.VAT_OUTPUT)
        - _sum_role(organization, Account.Role.VAT_INPUT)
    )

    # Monthly revenue vs expenses series (oldest → newest).
    chart = []
    for i in range(chart_months - 1, -1, -1):
        m_start = _shift_month(as_of, i)
        _, m_next = _month_window(m_start)
        m_last = m_next - timedelta(days=1)
        chart.append({
            "month": m_start.strftime("%b"),
            "revenue": _sum_type(organization, Account.Type.REVENUE, start=m_start, end=m_last),
            "expenses": _sum_type(organization, Account.Type.EXPENSE, start=m_start, end=m_last),
        })

    health = financial_health(revenue, expenses, outstanding_invoices, net_cash_flow)
    recommendations = ai_recommendations(
        revenue, expenses, outstanding_invoices, vat_payable, net_cash_flow
    )

    recent = list(
        organization.transactions.all()[:5]
    )

    return {
        "period": period_start.strftime("%b %Y"),
        "base_currency": organization.base_currency,
        "kpis": {
            "revenue": revenue,
            "expenses": expenses,
            "net_cash_flow": net_cash_flow,
            "outstanding_invoices": outstanding_invoices,
            "vat_payable": vat_payable,
        },
        "health": health,
        "recommendations": recommendations,
        "chart": chart,
        "recent_transactions": recent,
    }


def financial_health(revenue, expenses, receivables, net_cash_flow):
    """
    Heuristic 0–100 score from profit margin, cash-flow positivity, and
    receivables drag. Not a trained model (that's Phase 9) — a transparent rubric.
    """
    score = Decimal("50")
    if revenue > 0:
        margin = (revenue - expenses) / revenue
        score += (margin * Decimal("40")).quantize(TWO_PLACES)  # ±40 on margin
    if net_cash_flow > 0:
        score += Decimal("10")
    # Heavy receivables relative to revenue drag the score.
    if revenue > 0 and receivables > revenue:
        score -= Decimal("10")
    score = max(Decimal("0"), min(Decimal("100"), score))
    score = int(score)
    if score >= 75:
        label = "GOOD"
    elif score >= 50:
        label = "FAIR"
    else:
        label = "AT RISK"
    return {"score": score, "label": label}


def ai_recommendations(revenue, expenses, receivables, vat_payable, net_cash_flow):
    recs = []
    if revenue > 0 and expenses > revenue:
        recs.append({
            "title": "Expenses exceed revenue",
            "body": "Your spending outpaced income this period. Review the largest "
                    "expense categories on the Bookkeeping screen.",
            "severity": "danger",
        })
    if receivables > 0:
        recs.append({
            "title": "Chase outstanding invoices",
            "body": f"You have {receivables} in receivables. Following up on aged "
                    "invoices will improve cash flow.",
            "severity": "warning",
        })
    if vat_payable > 0:
        recs.append({
            "title": "VAT liability accruing",
            "body": f"VAT payable stands at {vat_payable}. Set aside funds ahead of "
                    "the ZATCA filing deadline.",
            "severity": "info",
        })
    if not recs:
        recs.append({
            "title": "Books look healthy",
            "body": "No issues detected this period. Keep categorizing transactions "
                    "to maintain an accurate picture.",
            "severity": "info",
        })
    return recs
