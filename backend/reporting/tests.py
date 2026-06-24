import io
from datetime import date
from decimal import Decimal

import openpyxl
from django.test import TestCase

from organizations.models import Organization
from ledger.models import Account
from ledger import services as ledger
from reporting import services, exporters

AS_OF = date(2026, 6, 15)


def make_org(name="Acme"):
    org = Organization.objects.create(name=name, base_currency="SAR", vat_number="300000000000003")
    A, R = Account.Type, Account.Role
    a = {
        "cash": Account.objects.create(organization=org, code="1000", name="Cash", type=A.ASSET, role=R.CASH),
        "ar": Account.objects.create(organization=org, code="1100", name="AR", type=A.ASSET, role=R.ACCOUNTS_RECEIVABLE),
        "vat_in": Account.objects.create(organization=org, code="1300", name="VAT Input", type=A.ASSET, role=R.VAT_INPUT),
        "ap": Account.objects.create(organization=org, code="2000", name="AP", type=A.LIABILITY, role=R.ACCOUNTS_PAYABLE),
        "vat_out": Account.objects.create(organization=org, code="2100", name="VAT Output", type=A.LIABILITY, role=R.VAT_OUTPUT),
        "capital": Account.objects.create(organization=org, code="3000", name="Capital", type=A.EQUITY),
        "sales": Account.objects.create(organization=org, code="4000", name="Sales", type=A.REVENUE),
        "rent": Account.objects.create(organization=org, code="5100", name="Rent", type=A.EXPENSE),
    }
    return org, a


def post(org, a, d, lines):
    ledger.post_journal_entry(organization=org, date=d, lines=[
        {"account": a[k], "debit": Decimal(dr), "credit": Decimal(cr)} for k, dr, cr in lines
    ])


class FinancialStatementTests(TestCase):
    def setUp(self):
        self.org, self.a = make_org()
        post(self.org, self.a, date(2026, 1, 1), [("cash", "100000", "0"), ("capital", "0", "100000")])
        post(self.org, self.a, date(2026, 5, 10), [("ar", "1150", "0"), ("sales", "0", "1000"), ("vat_out", "0", "150")])
        post(self.org, self.a, date(2026, 5, 26), [("rent", "8000", "0"), ("vat_in", "1200", "0"), ("cash", "0", "9200")])
        post(self.org, self.a, date(2026, 6, 1), [("cash", "400", "0"), ("ar", "0", "400")])

    def test_trial_balance_balances(self):
        rep = services.trial_balance(self.org, end=AS_OF)
        self.assertTrue(rep["meta"]["balanced"])
        self.assertEqual(rep["meta"]["total_debit"], "101150.00")
        self.assertEqual(rep["meta"]["total_credit"], "101150.00")

    def test_pl_reconciles_to_ledger(self):
        rep = services.profit_and_loss(self.org, end=AS_OF)
        self.assertEqual(rep["meta"]["revenue"], "1000.00")
        self.assertEqual(rep["meta"]["expenses"], "8000.00")
        self.assertEqual(rep["meta"]["net_profit"], "-7000.00")

    def test_balance_sheet_balances(self):
        rep = services.balance_sheet(self.org, end=AS_OF)
        self.assertTrue(rep["meta"]["balanced"])
        self.assertEqual(rep["meta"]["assets"], "93150.00")
        self.assertEqual(rep["meta"]["liabilities_plus_equity"], "93150.00")

    def test_cash_flow_reconciles(self):
        rep = services.cash_flow(self.org, start=date(2026, 5, 1), end=AS_OF)
        self.assertEqual(rep["meta"]["opening"], "100000.00")
        self.assertEqual(rep["meta"]["net_change"], "-8800.00")
        self.assertEqual(rep["meta"]["closing"], "91200.00")

    def test_vat_report_15_percent(self):
        rep = services.vat_report(self.org, as_of=AS_OF)
        self.assertEqual(rep["meta"]["output_vat"], "150.00")
        self.assertEqual(rep["meta"]["standard_rated_sales"], "1000.00")  # 150 / 0.15
        self.assertEqual(rep["meta"]["input_vat"], "1200.00")
        self.assertEqual(rep["meta"]["net_vat_payable"], "-1050.00")
        self.assertEqual(rep["meta"]["vat_number"], "300000000000003")

    def test_general_ledger_runs(self):
        rep = services.general_ledger(self.org, end=AS_OF)
        self.assertTrue(any(r["style"] == "section" for r in rep["rows"]))

    # ---- export integrity ----
    def test_xlsx_export_opens(self):
        rep = services.trial_balance(self.org, end=AS_OF)
        data = exporters.to_xlsx(rep)
        wb = openpyxl.load_workbook(io.BytesIO(data))  # reopens → valid file
        self.assertEqual(wb.active["A1"].value, "Trial Balance")

    def test_pdf_export_opens(self):
        rep = services.trial_balance(self.org, end=AS_OF)
        data = exporters.to_pdf(rep)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", data[-1024:])
        self.assertGreater(len(data), 800)


class AgingTests(TestCase):
    def setUp(self):
        self.org, self.a = make_org(name="Aging Co")
        # AR invoices at varied ages (relative to AS_OF 2026-06-15).
        post(self.org, self.a, date(2026, 6, 10), [("ar", "100", "0"), ("sales", "0", "100")])   # 0-30
        post(self.org, self.a, date(2026, 5, 1), [("ar", "200", "0"), ("sales", "0", "200")])    # 31-60
        post(self.org, self.a, date(2026, 4, 20), [("ar", "50", "0"), ("sales", "0", "50")])     # 31-60
        post(self.org, self.a, date(2026, 4, 1), [("ar", "80", "0"), ("sales", "0", "80")])      # 61-90
        post(self.org, self.a, date(2026, 3, 15), [("ar", "300", "0"), ("sales", "0", "300")])   # 90+
        post(self.org, self.a, date(2026, 6, 12), [("cash", "100", "0"), ("ar", "0", "100")])    # FIFO→oldest
        # AP bill, very old.
        post(self.org, self.a, date(2026, 3, 1), [("rent", "400", "0"), ("ap", "0", "400")])     # 90+

    def test_ar_aging_buckets(self):
        rep = services.ar_aging(self.org, as_of=AS_OF)
        m = rep["meta"]
        # Payment 100 (FIFO) reduces the oldest invoice (300 → 200).
        self.assertEqual(m["0-30"], "100.00")
        self.assertEqual(m["31-60"], "250.00")
        self.assertEqual(m["61-90"], "80.00")
        self.assertEqual(m["90+"], "200.00")
        self.assertEqual(m["total"], "630.00")

    def test_ap_aging_buckets(self):
        rep = services.ap_aging(self.org, as_of=AS_OF)
        m = rep["meta"]
        self.assertEqual(m["90+"], "400.00")
        self.assertEqual(m["total"], "400.00")


class ReportEndpointTests(TestCase):
    def setUp(self):
        self.org, self.a = make_org(name="Endpoint Co")
        post(self.org, self.a, date(2026, 5, 1), [("cash", "500", "0"), ("capital", "0", "500")])

    def test_json_default(self):
        r = self.client.get("/api/reports/trial_balance/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["meta"]["balanced"])

    def test_xlsx_export(self):
        r = self.client.get("/api/reports/profit_and_loss/?export=xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertTrue(len(r.content) > 800)

    def test_pdf_export(self):
        r = self.client.get("/api/reports/balance_sheet/?export=pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_unknown_report_404(self):
        self.assertEqual(self.client.get("/api/reports/nope/").status_code, 404)

    def test_bad_export_format_400(self):
        self.assertEqual(
            self.client.get("/api/reports/trial_balance/?export=csv").status_code, 400
        )


class TenantScopingTests(TestCase):
    def test_reports_are_org_scoped(self):
        org_a, a = make_org(name="A")
        post(org_a, a, date(2026, 5, 1), [("cash", "500", "0"), ("capital", "0", "500")])
        org_b, b = make_org(name="B")
        post(org_b, b, date(2026, 5, 1), [("cash", "999999", "0"), ("capital", "0", "999999")])
        rep = services.trial_balance(org_a, end=AS_OF)
        self.assertEqual(rep["meta"]["total_debit"], "500.00")
