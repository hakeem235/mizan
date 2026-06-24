from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Account, JournalEntry, JournalLine, Transaction
from . import services


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ["id", "code", "name", "type", "role", "is_active", "balance"]

    def get_balance(self, obj):
        return str(services.account_balance(obj))


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)

    class Meta:
        model = JournalLine
        fields = ["id", "account", "account_code", "debit", "credit"]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id", "date", "description", "currency", "fx_rate",
            "status", "lines", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_lines(self, value):
        if len(value) < 2:
            raise serializers.ValidationError(
                "A journal entry needs at least two lines."
            )
        return value

    def create(self, validated_data):
        organization = self.context["organization"]
        lines = validated_data.pop("lines")
        # Re-bind account ids to this org and reject cross-org accounts.
        prepared = []
        for ln in lines:
            account = ln["account"]
            prepared.append({
                "account": account,
                "debit": ln.get("debit") or Decimal("0"),
                "credit": ln.get("credit") or Decimal("0"),
            })
        try:
            return services.post_journal_entry(
                organization=organization,
                date=validated_data["date"],
                description=validated_data.get("description", ""),
                currency=validated_data.get("currency") or organization.base_currency,
                fx_rate=validated_data.get("fx_rate") or Decimal("1"),
                status=validated_data.get("status", JournalEntry.Status.POSTED),
                lines=prepared,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id", "date", "description", "amount", "currency", "category",
            "confidence", "status", "is_duplicate", "duplicate_of", "created_at",
        ]
        read_only_fields = [
            "category", "confidence", "status", "is_duplicate",
            "duplicate_of", "created_at",
        ]

    def create(self, validated_data):
        organization = self.context["organization"]
        return services.ingest_transaction(
            organization=organization,
            date=validated_data["date"],
            description=validated_data["description"],
            amount=validated_data["amount"],
            currency=validated_data.get("currency") or organization.base_currency,
        )
