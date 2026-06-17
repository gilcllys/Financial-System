from rest_framework import serializers

from debts.models import VitoriaDebt
from expenses.models import Expense


class VitoriaDebtSerializer(serializers.ModelSerializer):
    """
    Serializer enriquecido para VitoriaDebt.

    Leitura  → inclui os campos da Expense inline (expense_id,
               expense_description, expense_amount, expense_date,
               expense_category_name).
    Escrita  → aceita `expense` como FK (PrimaryKey) e `is_paid`.
               tenant_id é injetado automaticamente pelo viewset via
               perform_create / perform_update.
    """

    # --- campos de escrita -------------------------------------------
    expense = serializers.PrimaryKeyRelatedField(
        queryset=Expense.objects.all(),
        write_only=True,
        help_text='ID da Expense vinculada a esta dívida.',
    )

    # --- campos de leitura (inline da Expense) -----------------------
    expense_id = serializers.IntegerField(
        source='expense.id',
        read_only=True,
    )
    expense_description = serializers.CharField(
        source='expense.description',
        read_only=True,
    )
    expense_amount = serializers.DecimalField(
        source='expense.amount',
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    expense_date = serializers.DateField(
        source='expense.date',
        read_only=True,
    )
    expense_category_name = serializers.CharField(
        source='expense.category.name',
        read_only=True,
    )

    class Meta:
        model = VitoriaDebt
        fields = [
            'id',
            # write-only
            'expense',
            # read-only (inline)
            'expense_id',
            'is_paid',
            'expense_description',
            'expense_amount',
            'expense_date',
            'expense_category_name',
        ]
        read_only_fields = [
            'id',
            'expense_id',
            'expense_description',
            'expense_amount',
            'expense_date',
            'expense_category_name',
        ]
