from django.db import models
from django.db.models.functions import ExtractMonth, ExtractYear
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
    recurring_template = models.ForeignKey(
        to='expenses.RecurringExpenseTemplate',
        db_column='recurring_template_id',
        db_index=True,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='generated_expenses',
        help_text=(
            'Template que gerou esta despesa. Nulo quando a despesa foi criada '
            'manualmente. Usa SET_NULL porque a despesa e historico financeiro '
            'real e deve sobreviver a exclusao do template.'
        ),
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
        constraints = [
            # Um template so pode gerar UMA despesa por mes/ano. Despesas manuais
            # tem recurring_template NULL e NULL nunca conflita em UNIQUE, entao
            # elas permanecem livres para repetir a vontade.
            models.UniqueConstraint(
                'recurring_template',
                ExtractYear('date'),
                ExtractMonth('date'),
                name='uniq_expense_per_template_month',
            ),
        ]


class RecurringExpenseTemplate(BaseModel):
    """
    Gasto fixo mensal individual.

    Ao ser materializado (via generate_month), cria uma Expense real
    para o mês/ano solicitado, caso ainda não exista.
    """

    PAYMENT_METHOD_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao', 'Cartão'),
    ]

    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=False,
    )
    category = models.ForeignKey(
        to='catalog.ExpenseCategory',
        db_column='category_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recurring_expense_templates',
    )
    credit_card = models.ForeignKey(
        to='cards.CreditCard',
        db_column='credit_card_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recurring_expense_templates',
    )
    description = models.CharField(max_length=255, db_column='description')
    amount = models.DecimalField(max_digits=10, decimal_places=2, db_column='amount')
    day_of_month = models.PositiveSmallIntegerField(
        db_column='day_of_month',
        default=1,
        help_text='Dia do mês em que o gasto se repete (1–28).',
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        db_column='payment_method',
        default='dinheiro',
    )
    is_active = models.BooleanField(
        db_column='is_active',
        default=True,
    )

    class Meta:
        db_table = 'recurring_expense_templates'
        verbose_name = 'Recurring Expense Template'
        verbose_name_plural = 'Recurring Expense Templates'
        indexes = [
            models.Index(fields=['tenant_id', 'is_active'], name='recexp_tenant_active_idx'),
        ]
