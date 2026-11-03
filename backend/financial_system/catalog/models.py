from django.db import models
from financial_system.base_model import BaseModel


class ExpenseCategory(BaseModel):
    KIND_CHOICES = [('despesa', 'Despesa'), ('receita', 'Receita')]
    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
        help_text='Identificador único do tenant/usuário vindo do Keycloak (sub claim)',
    )
    name = models.CharField(
        max_length=100,
        db_column='name',
        db_index=True,
        null=False,
    )
    description = models.TextField(
        db_column='description',
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='despesa', db_index=True)
    key = models.CharField(max_length=40, null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'expense_categories'
        verbose_name = 'Expense Category'
        verbose_name_plural = 'Expense Categories'
