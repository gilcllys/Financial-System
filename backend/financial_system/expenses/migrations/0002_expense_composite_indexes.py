"""
Migration 0002 — Índices compostos para performance no EC2.

Contexto:
  - expenses_tenant_date_idx : acelera filtros por (tenant_id, date__year/month)
    usados em get_queryset() e em todos os endpoints analytics.
  - expenses_tenant_card_idx : acelera filtros por (tenant_id, credit_card_id)
    usados em expenses_per_credit_card e analytics/by-card.

Rollback seguro: RemoveIndex não apaga dados.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0001_initial'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(
                fields=['tenant_id', 'date'],
                name='expenses_tenant_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(
                fields=['tenant_id', 'credit_card'],
                name='expenses_tenant_card_idx',
            ),
        ),
    ]
