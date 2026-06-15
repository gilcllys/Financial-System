from django.db import models
from financial_system.base_model import BaseModel


class CreditCard(BaseModel):
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
    due_date = models.IntegerField(
        db_column='due_date',
        null=False,
        help_text='Dia do vencimento da fatura (1-31)',
    )
    best_purchase_date = models.IntegerField(
        db_column='best_purchase_date',
        null=False,
        help_text='Melhor dia para compra (1-31)',
    )
    last_four_digits = models.CharField(
        max_length=4,
        db_column='last_four_digits',
        null=False,
    )

    class Meta:
        db_table = 'credit_cards'
        verbose_name = 'Credit Card'
        verbose_name_plural = 'Credit Cards'
