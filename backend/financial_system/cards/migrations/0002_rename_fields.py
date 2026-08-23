from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Renomeia best_purchase_date -> closing_day e due_date -> due_day.

    Ordem importa:
      1. RenameField  -> renomeia apenas o atributo Python (db_column ainda eh o antigo)
      2. AlterField   -> muda db_column, renomeando a coluna no banco
      3. RunSQL       -> SÓ AGORA a coluna se chama closing_day no banco
    """

    dependencies = [
        ('cards', '0001_initial'),
    ]

    operations = [
        # 1. Renomear atributos Python
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
        # 2. Atualizar db_column (renomeia a coluna fisicamente no banco)
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
                help_text='Dia de fechamento da fatura (1-31). Ex: fecha no dia 26, guarde 26.',
            ),
        ),
        # 3. Agora closing_day existe no banco: ajusta o valor armazenado
        #    (best_purchase_date guardava "melhor dia" = dia apos o fechamento,
        #     closing_day deve guardar o dia REAL de fechamento = valor - 1)
        migrations.RunSQL(
            sql='UPDATE credit_cards SET closing_day = closing_day - 1',
            reverse_sql='UPDATE credit_cards SET closing_day = closing_day + 1',
        ),
    ]