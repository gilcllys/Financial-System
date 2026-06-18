from django.db import models
from financial_system.base_model import BaseModel


class VitoriaDebt(BaseModel):
    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
        help_text='Identificador único do tenant/usuário vindo do Keycloak (sub claim)',
    )
    expense = models.ForeignKey(
        to='expenses.Expense',
        db_column='expense_id',
        db_index=True,
        null=False,
        on_delete=models.CASCADE,
        related_name='vitoria_debts',
    )
    is_paid = models.BooleanField(
        db_column='is_paid',
        null=False,
        default=False,
        help_text='Indica se a dívida com a Vitória já foi paga',
    )

    class Meta:
        db_table = 'vitoria_debts'
        verbose_name = 'Vitoria Debt'
        verbose_name_plural = 'Vitoria Debts'
