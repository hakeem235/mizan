from django.db import models


class Organization(models.Model):
    """
    A tenant. Every financial record is scoped to exactly one Organization;
    cross-org reads are a hard security boundary (enforced in querysets and
    explicitly tested in Issue 7.3).
    """

    name = models.CharField(max_length=200)
    # ISO 4217 code the org keeps its books in. All reports reconcile in this
    # currency; foreign-currency entries carry an FX rate back to it.
    base_currency = models.CharField(max_length=3, default="SAR")
    # Saudi VAT registration number (15 digits) — used on ZATCA reports.
    vat_number = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
