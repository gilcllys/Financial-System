import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Etapa 1 de 3: cria a coluna recurring_template_id, ainda sem constraint.

    A constraint de unicidade so entra na 0006, depois que a 0005 tiver
    ligado o historico existente. Aplicar a constraint antes do backfill
    seria seguro (NULL nunca conflita), mas separar as etapas deixa o
    diagnostico obvio caso alguma delas falhe em producao.
    """

    dependencies = [
        ('expenses', '0003_recurringexpensetemplate'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='recurring_template',
            field=models.ForeignKey(
                blank=True,
                db_column='recurring_template_id',
                help_text=(
                    'Template que gerou esta despesa. Nulo quando a despesa foi criada '
                    'manualmente. Usa SET_NULL porque a despesa e historico financeiro '
                    'real e deve sobreviver a exclusao do template.'
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='generated_expenses',
                to='expenses.recurringexpensetemplate',
            ),
        ),
    ]
