"""
OCR text → structured financial fields → validation → ledger posting.

All deterministic and unit-tested. OCR itself happens client-side (Tesseract);
this module owns everything after the raw text arrives, including the
NUL-byte / control-char sanitization that Postgres + DRF reject (ComplianceAI
PR #6 lesson).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from ledger.models import Account
from ledger import services

VAT_RATE = Decimal("0.15")
VAT_TOLERANCE = Decimal("0.02")  # absorb OCR rounding noise (halalas)
TWO_PLACES = Decimal("0.01")

# Control chars Postgres text columns / DRF CharField reject. Keep \t \n \r.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_text(text):
    """Strip NUL and disallowed control characters from OCR output."""
    if text is None:
        return ""
    return _CONTROL_CHARS.sub("", text)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
_AMOUNT = r"([0-9][0-9,]*\.?[0-9]{0,2})"


def _to_decimal(raw):
    try:
        return Decimal(raw.replace(",", "")).quantize(TWO_PLACES)
    except (InvalidOperation, AttributeError):
        return None


def _find(pattern, text, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_date(text):
    # Try a few common invoice date formats.
    m = re.search(
        r"(?:date|invoice date|التاريخ)\D{0,10}"
        r"(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_document(raw_text, doc_type=None):
    """
    Extract structured fields from OCR text. Missing fields come back as None;
    validation (not parsing) decides whether that's a problem.
    """
    text = sanitize_text(raw_text or "")

    vendor = _find(r"(?:vendor|supplier|from|bill from|المورد)\s*[:\-]\s*(.+)", text)
    invoice_number = _find(
        r"(?:invoice\s*(?:no|number|#)|رقم الفاتورة)\s*[:\-#]*\s*([A-Za-z0-9\-/]+)", text
    )
    vat_number = _find(
        r"(?:vat\s*(?:no|number|reg)|الرقم الضريبي)\s*[:\-]*\s*(\d{15})", text
    )
    if not vat_number:
        # A bare 15-digit run is a Saudi VAT number.
        vat_number = _find(r"\b(\d{15})\b", text)

    subtotal = _to_decimal(
        _find(r"(?:subtotal|sub-total|amount before vat|الإجمالي قبل)\D{0,12}" + _AMOUNT, text)
    )
    # Skip "VAT Number/No/Reg" so a 15-digit registration number isn't read as
    # the VAT amount.
    vat_amount = _to_decimal(
        _find(r"(?:vat|tax|ضريبة)\b(?!\s*(?:number|no\b|reg|registration|الرقم))\D{0,12}" + _AMOUNT, text)
    )
    # `(?<![a-z])total` keeps "subtotal" from matching the grand-total pattern.
    total = _to_decimal(
        _find(r"(?:grand total|total due|(?<![a-z])total|الإجمالي)\D{0,12}" + _AMOUNT, text)
    )

    return {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "date": _parse_date(text),
        "vat_number": vat_number,
        "subtotal": str(subtotal) if subtotal is not None else None,
        "vat_amount": str(vat_amount) if vat_amount is not None else None,
        "total": str(total) if total is not None else None,
        "currency": "SAR",
    }


# --------------------------------------------------------------------------- #
# Validation — flag inconsistencies, never silently accept
# --------------------------------------------------------------------------- #
def _dec(fields, key):
    val = fields.get(key)
    if val in (None, ""):
        return None
    try:
        return Decimal(str(val)).quantize(TWO_PLACES)
    except (InvalidOperation, ValueError):
        return None


def validate_extraction(fields):
    """Return a list of {field, message, severity} flags for the parsed fields."""
    flags = []
    subtotal = _dec(fields, "subtotal")
    vat = _dec(fields, "vat_amount")
    total = _dec(fields, "total")

    if total is None:
        flags.append({"field": "total", "message": "Total amount not found.",
                      "severity": "danger"})
    if subtotal is None:
        flags.append({"field": "subtotal", "message": "Subtotal not found.",
                      "severity": "warning"})

    # Totals must add up: subtotal + vat == total.
    if subtotal is not None and vat is not None and total is not None:
        if (subtotal + vat) != total:
            flags.append({
                "field": "total",
                "message": f"Totals don't add up: {subtotal} + {vat} ≠ {total}.",
                "severity": "danger",
            })

    # VAT must be 15% of subtotal (within rounding tolerance).
    if subtotal is not None and vat is not None and subtotal > 0:
        expected = (subtotal * VAT_RATE).quantize(TWO_PLACES)
        if abs(vat - expected) > VAT_TOLERANCE:
            flags.append({
                "field": "vat_amount",
                "message": f"VAT {vat} is not 15% of subtotal (expected {expected}).",
                "severity": "warning",
            })

    if not fields.get("vat_number"):
        flags.append({"field": "vat_number",
                      "message": "Missing VAT registration number.",
                      "severity": "warning"})

    # Date sanity: present and not in the future.
    d = fields.get("date")
    if not d:
        flags.append({"field": "date", "message": "Document date not found.",
                      "severity": "warning"})
    else:
        try:
            if date.fromisoformat(d) > date.today():
                flags.append({"field": "date",
                              "message": "Document date is in the future.",
                              "severity": "danger"})
        except ValueError:
            flags.append({"field": "date", "message": "Unrecognized date format.",
                          "severity": "warning"})

    return flags


def extraction_confidence(fields, flags):
    """Heuristic 0–1 confidence: complete fields high, each flag drags it down."""
    core = ["invoice_number", "date", "subtotal", "vat_amount", "total"]
    present = sum(1 for k in core if fields.get(k))
    base = Decimal(present) / Decimal(len(core))
    penalty = Decimal("0.1") * len([f for f in flags if f["severity"] == "danger"])
    score = max(Decimal("0"), base - penalty)
    return score.quantize(TWO_PLACES)


# --------------------------------------------------------------------------- #
# Posting a confirmed document to the ledger
# --------------------------------------------------------------------------- #
def post_document_to_ledger(document, *, expense_account=None):
    """
    Create a balanced purchase-invoice journal entry from a confirmed document:
        Dr Expense (subtotal) + Dr VAT Input (vat)  =  Cr Accounts Payable (total)

    Requires the org to have VAT-input and accounts-payable accounts and at least
    one expense account (or an explicit `expense_account`). Raises ValidationError
    if the figures are incomplete/unbalanced (delegated to post_journal_entry).
    """
    org = document.organization
    fields = document.extracted
    subtotal = _dec(fields, "subtotal")
    vat = _dec(fields, "vat_amount") or Decimal("0")
    total = _dec(fields, "total")

    if subtotal is None or total is None:
        raise ValidationError("Cannot post: subtotal and total are required.")

    expense = expense_account or org.accounts.filter(
        type=Account.Type.EXPENSE, is_active=True
    ).order_by("code").first()
    if expense is None:
        raise ValidationError("No expense account configured for this organization.")

    ap = org.accounts.filter(role=Account.Role.ACCOUNTS_PAYABLE).first()
    if ap is None:
        raise ValidationError("No accounts-payable account configured.")

    lines = [
        {"account": expense, "debit": subtotal, "credit": Decimal("0")},
    ]
    if vat > 0:
        vat_input = org.accounts.filter(role=Account.Role.VAT_INPUT).first()
        if vat_input is None:
            raise ValidationError("No VAT-input account configured.")
        lines.append({"account": vat_input, "debit": vat, "credit": Decimal("0")})
    lines.append({"account": ap, "debit": Decimal("0"), "credit": total})

    entry_date = (
        date.fromisoformat(fields["date"]) if fields.get("date") else date.today()
    )
    entry = services.post_journal_entry(
        organization=org,
        date=entry_date,
        description=f"{document.get_doc_type_display()} {fields.get('invoice_number') or ''}".strip(),
        lines=lines,
    )
    document.journal_entry = entry
    document.status = document.Status.POSTED
    document.save(update_fields=["journal_entry", "status"])
    return entry
