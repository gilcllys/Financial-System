from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0001_initial'),
    ]

    operations = [
        # 1. Rename columns in the DB
        migrations.RenameField(
            model_name='creditcard',
            old_name='due_date',
            new_name='due_day',
        ),
        migrations.RenameField(
            model_name='creditcard',
            old_name='best_purchase_date',
            new_name='closing_day',
        ),
        # 2. Data migration: closing_day = best_purchase_date - 1
        #    (stored value was "melhor dia", agora guardamos o dia real de fechamento)
        migrations.RunSQL(
            sql='UPDATE credit_cards SET closing_day = closing_day - 1',
            reverse_sql='UPDATE credit_cards SET closing_day = closing_day + 1',
        ),
        # 3. Update help_text (cosmetic, no DB change)
        migrations.AlterField(
            model_name='creditcard',
            name='due_day',
            field=models.IntegerField(
                db_column='due_day',
                help_text='Dia do vencimento da fatura (1-31)',
            ),
        ),
        migrations.AlterField(
            model_name='creditcard',
            name='closing_day',
            field=models.IntegerField(
                db_column='closing_day',
                help_text='Dia de fechamento da fatura (1-31). Ex: se fecha no dia 26, guarde 26.',
            ),
        ),
    ]