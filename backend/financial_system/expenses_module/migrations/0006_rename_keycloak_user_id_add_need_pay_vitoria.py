from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses_module', '0005_replace_user_fk_with_keycloak_user_id'),
    ]

    operations = [
        migrations.RenameField(
            model_name='creditcard',
            old_name='keycloak_user_id',
            new_name='tenant_id',
        ),
        migrations.RenameField(
            model_name='expense',
            old_name='keycloak_user_id',
            new_name='tenant_id',
        ),
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
