from django.db import models
from financial_system.base_model import BaseModel


class Expense(BaseModel):
    PAYMENT_METHOD_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao', 'Cartão'),
    ]

    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
        help_text='Identificador único do tenant/usuário vindo do Keycloak (sub claim)',
    )
    category = models.ForeignKey(
        to='catalog.ExpenseCategory',
        db_column='category_id',
        db_index=True,
        null=False,
        on_delete=models.DO_NOTHING,
        related_name='expenses',
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        db_column='payment_method',
        db_index=True,
        default='dinheiro',
        null=False,
    )
    credit_card = models.ForeignKey(
        to='cards.CreditCard',
        db_column='credit_card_id',
        db_index=True,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name='expenses',
    )
    description = models.CharField(
        max_length=255,
        db_column='description',
        db_index=True,
        null=False,
    )
    quantity = models.IntegerField(
        db_column='quantity',
        db_index=True,
        null=False,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        db_column='amount',
        db_index=True,
        null=False,
    )
    date = models.DateField(
        db_column='date',
        db_index=True,
        null=False,
    )

    class Meta:
        db_table = 'expenses'
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'
        indexes = [
            # Filtros mais frequentes: tenant + mês/ano (analytics, listagem)
            models.Index(fields=['tenant_id', 'date'], name='expenses_tenant_date_idx'),
            # Filtros por cartão: tenant + credit_card (fatura, analytics by-card)
            models.Index(fields=['tenant_id', 'credit_card'], name='expenses_tenant_card_idx'),
        ]
