from django.db import models
from financial_system.base_model import BaseModel


class SavingsGoal(BaseModel):
    """Cofrinho / meta de investimento do usuário."""
    tenant_id = models.CharField(max_length=36, db_column='tenant_id', db_index=True)
    name = models.CharField(max_length=120, db_column='name')
    target_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, db_column='target_amount',
        help_text='Meta opcional (NULL = sem meta definida).',
    )
    color = models.CharField(max_length=7, default='#6366f1', db_column='color')
    icon = models.CharField(max_length=10, default='🐷', db_column='icon')

    class Meta:
        db_table = 'savings_goals'
        verbose_name = 'Savings Goal'
        indexes = [models.Index(fields=['tenant_id'], name='savings_goal_tenant_idx')]


class SavingsDeposit(BaseModel):
    """Aporte (positivo) ou retirada (negativo) em um cofrinho."""
    goal = models.ForeignKey(
        SavingsGoal, on_delete=models.CASCADE,
        related_name='deposits', db_column='goal_id',
    )
    tenant_id = models.CharField(max_length=36, db_column='tenant_id', db_index=True)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, db_column='amount',
        help_text='Positivo = aporte, negativo = retirada.',
    )
    date = models.DateField(db_column='date')
    description = models.CharField(max_length=255, blank=True, default='', db_column='description')

    class Meta:
        db_table = 'savings_deposits'
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['tenant_id', 'date'], name='savings_dep_tenant_date_idx')]
