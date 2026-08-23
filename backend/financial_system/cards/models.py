from django.db import models
from financial_system.base_model import BaseModel


class CreditCard(BaseModel):
    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
        help_text='ID do tenant/usuario (Keycloak sub claim)',
    )
    name = models.CharField(
        max_length=100,
        db_column='name',
        db_index=True,
        null=False,
    )
    due_day = models.IntegerField(
        db_column='due_day',
        null=False,
        help_text='Dia do vencimento da fatura (1-31)',
    )
    closing_day = models.IntegerField(
        db_column='closing_day',
        null=False,
        help_text='Dia de fechamento da fatura (1-31). Ex: fecha no dia 26, guarde 26.',
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
