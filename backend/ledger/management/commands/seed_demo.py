"""
Seed a demo organization with a chart of accounts, balanced journal entries
(including a foreign-currency entry), and bank transactions (including a
deliberate duplicate) so the dashboard renders real aggregates out of the box.

Idempotent: re-running resets the demo org's ledger.
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from organizations.models import Organization
from ledger.models import Account, JournalEntry, Transaction
from ledger import services

DEMO_ORG = "Mizan Trading Co."


class Command(BaseCommand):
    help = "Seed demo organization, accounts, journal entries, and transactions."

    @transaction.atomic
    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(
            name=DEMO_ORG,
            defaults={"base_currency": "SAR", "vat_number": "300000000000003"},
        )
        # Reset ledger for a clean, repeatable seed.
        JournalEntry.objects.filter(organization=org).delete()
        Transaction.objects.filter(organization=org).delete()
        Account.objects.filter(organization=org).delete()

        A = Account.Type
        R = Account.Role

        def acc(code, name, type_, role=R.GENERIC):
            return Account.objects.create(
                organization=org, code=code, name=name, type=type_, role=role
            )

        cash = acc("1000", "Cash & Bank", A.ASSET, R.CASH)
        ar = acc("1100", "Accounts Receivable", A.ASSET, R.ACCOUNTS_RECEIVABLE)
        vat_input = acc("1300", "VAT Input (recoverable)", A.ASSET, R.VAT_INPUT)
        ap = acc("2000", "Accounts Payable", A.LIABILITY, R.ACCOUNTS_PAYABLE)
        vat_output = acc("2100", "VAT Output (payable)", A.LIABILITY, R.VAT_OUTPUT)
        capital = acc("3000", "Owner's Capital", A.EQUITY)
        sales = acc("4000", "Sales Revenue", A.REVENUE)
        payroll = acc("5000", "Payroll", A.EXPENSE)
        rent = acc("5100", "Rent", A.EXPENSE)
        cogs = acc("5200", "Inventory & COGS", A.EXPENSE)

        today = date.today()
        this_month = today.replace(day=1)

        def m(months_back, day=5):
            y, mo = this_month.year, this_month.month - months_back
            while mo <= 0:
                mo += 12
                y -= 1
            return date(y, mo, day)

        # Opening capital injection.
        services.post_journal_entry(
            organization=org, date=m(7, 1), description="Opening capital",
            lines=[
                {"account": cash, "debit": Decimal("500000"), "credit": 0},
                {"account": capital, "debit": 0, "credit": Decimal("500000")},
            ],
        )

        # A sales invoice each of the last 8 months (revenue + 15% VAT output).
        for i in range(7, -1, -1):
            net = Decimal("60000") + Decimal("3000") * (7 - i)
            vat = (net * services.VAT_STANDARD_RATE).quantize(Decimal("0.01"))
            services.post_journal_entry(
                organization=org, date=m(i, 6),
                description=f"Sales invoice {m(i, 6)}",
                lines=[
                    {"account": ar, "debit": net + vat, "credit": 0},
                    {"account": sales, "debit": 0, "credit": net},
                    {"account": vat_output, "debit": 0, "credit": vat},
                ],
            )
            # Customer pays most of it (leaving some receivables outstanding).
            services.post_journal_entry(
                organization=org, date=m(i, 20),
                description=f"Customer payment {m(i, 20)}",
                lines=[
                    {"account": cash, "debit": net, "credit": 0},
                    {"account": ar, "debit": 0, "credit": net},
                ],
            )
            # Monthly expenses with recoverable VAT input.
            services.post_journal_entry(
                organization=org, date=m(i, 25), description=f"Payroll {m(i, 25)}",
                lines=[
                    {"account": payroll, "debit": Decimal("28000"), "credit": 0},
                    {"account": cash, "debit": 0, "credit": Decimal("28000")},
                ],
            )
            rent_net = Decimal("8000")
            rent_vat = (rent_net * services.VAT_STANDARD_RATE).quantize(Decimal("0.01"))
            services.post_journal_entry(
                organization=org, date=m(i, 26), description=f"Office rent {m(i, 26)}",
                lines=[
                    {"account": rent, "debit": rent_net, "credit": 0},
                    {"account": vat_input, "debit": rent_vat, "credit": 0},
                    {"account": cash, "debit": 0, "credit": rent_net + rent_vat},
                ],
            )

        # A foreign-currency purchase (USD) converted to SAR at fx_rate 3.75.
        services.post_journal_entry(
            organization=org, date=m(0, 10),
            description="Imported inventory (USD)", currency="USD",
            fx_rate=Decimal("3.75"),
            lines=[
                {"account": cogs, "debit": Decimal("10000"), "credit": 0},
                {"account": ap, "debit": 0, "credit": Decimal("10000")},
            ],
        )

        # Bank feed transactions for the AI bookkeeping screen.
        feed = [
            (m(0, 2), "STC internet subscription", Decimal("-525.00")),
            (m(0, 3), "Payroll run - April", Decimal("-28000.00")),
            (m(0, 4), "POS sales settlement", Decimal("12450.00")),
            (m(0, 5), "Careem business travel", Decimal("-318.00")),
            (m(0, 6), "Bank service charge", Decimal("-75.00")),
        ]
        for d, desc, amt in feed:
            services.ingest_transaction(
                organization=org, date=d, description=desc, amount=amt
            )
        # Deliberate duplicate of the payroll feed line — must be flagged.
        dup = services.ingest_transaction(
            organization=org, date=m(0, 3), description="Payroll run - April",
            amount=Decimal("-28000.00"),
        )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{org.name}' (id={org.id}): "
            f"{org.accounts.count()} accounts, "
            f"{org.journal_entries.count()} journal entries, "
            f"{org.transactions.count()} transactions "
            f"(duplicate flagged: {dup.is_duplicate})."
        ))
