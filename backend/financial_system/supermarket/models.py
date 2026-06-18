from django.db import models
from financial_system.base_model import BaseModel


class SupermarketExpense(BaseModel):
    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
        help_text='Identificador único do tenant/usuário vindo do Keycloak (sub claim)',
    )
    store_name = models.CharField(
        max_length=100,
        db_column='store_name',
        db_index=True,
        null=False,
    )
    date = models.DateField(
        db_column='date',
        db_index=True,
        null=False,
    )
    address = models.CharField(
        max_length=100,
        db_column='address',
        db_index=True,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'supermarket_expenses'
        verbose_name = 'Supermarket Expense'
        verbose_name_plural = 'Supermarket Expenses'


class SupermarketExpenseItem(BaseModel):
    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
        help_text='Identificador único do tenant/usuário vindo do Keycloak (sub claim)',
    )
    supermarket_expense = models.ForeignKey(
        to='SupermarketExpense',
        db_column='supermarket_expense_id',
        db_index=True,
        null=False,
        on_delete=models.CASCADE,
        related_name='items',
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
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        db_column='unit_price',
        db_index=True,
        null=False,
        help_text='Preço unitário do item',
    )

    class Meta:
        db_table = 'supermarket_expense_items'
        verbose_name = 'Supermarket Expense Item'
        verbose_name_plural = 'Supermarket Expense Items'
