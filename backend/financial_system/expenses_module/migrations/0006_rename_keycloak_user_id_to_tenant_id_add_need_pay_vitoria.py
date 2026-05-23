from django.db import migrations, models


class Migration(migrations.Migration):
    """
    1. Rename keycloak_user_id → tenant_id (ORM-only; db_column permanece
       'keycloak_user_id', portanto nenhuma alteração de coluna no banco).
    2. Adiciona o campo need_pay_vitoria em Expense.
    """

    dependencies = [
        ('expenses_module', '0005_replace_user_fk_with_keycloak_user_id'),
    ]

    operations = [
        # --- CreditCard: renomeia o campo Python, sem tocar na coluna do DB ---
        migrations.RenameField(
            model_name='creditcard',
            old_name='keycloak_user_id',
            new_name='tenant_id',
        ),

        # --- Expense: renomeia o campo Python, sem tocar na coluna do DB ---
        migrations.RenameField(
            model_name='expense',
            old_name='keycloak_user_id',
            new_name='tenant_id',
        ),

        # --- Expense: adiciona o novo campo need_pay_vitoria ---
        migrations.AddField(
            model_name='expense',
            name='need_pay_vitoria',
            field=models.BooleanField(
                blank=True,
                db_column='need_pay_vitoria',
                default=False,
                help_text='Indica se essa despesa foi feita no lado da Vitória e precisa ser paga depois',
                null=True,
            ),
        ),
    ]
