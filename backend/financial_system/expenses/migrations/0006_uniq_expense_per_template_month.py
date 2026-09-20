import django.db.models.functions.datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Etapa 3 de 3: trava no banco a regra "um template gera no maximo uma
    despesa por mes".

    Despesas manuais tem recurring_template NULL e NULL nunca conflita em
    indice unico (Postgres e SQLite), entao elas continuam livres para se
    repetir quantas vezes o usuario quiser no mesmo mes.
    """

    dependencies = [
        ('expenses', '0005_backfill_recurring_template'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='expense',
            constraint=models.UniqueConstraint(
                models.F('recurring_template'),
                django.db.models.functions.datetime.ExtractYear('date'),
                django.db.models.functions.datetime.ExtractMonth('date'),
                name='uniq_expense_per_template_month',
            ),
        ),
    ]
