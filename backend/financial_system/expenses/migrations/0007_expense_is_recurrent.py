from django.db import migrations, models


def mark_existing_recurring_expenses(apps, schema_editor):
    Expense = apps.get_model('expenses', 'Expense')
    Expense.objects.filter(recurring_template__isnull=False).update(is_recurrent=True)


class Migration(migrations.Migration):
    dependencies = [
        ('expenses', '0006_uniq_expense_per_template_month'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='is_recurrent',
            field=models.BooleanField(
                db_column='is_recurrent',
                default=False,
                help_text='Indica se a despesa foi gerada por um gasto fixo recorrente.',
            ),
        ),
        migrations.RunPython(mark_existing_recurring_expenses, migrations.RunPython.noop),
    ]
