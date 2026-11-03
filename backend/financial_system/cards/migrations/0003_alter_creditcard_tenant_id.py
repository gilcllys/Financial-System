from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0002_rename_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='creditcard',
            name='tenant_id',
            field=models.CharField(
                db_column='tenant_id',
                db_index=True,
                help_text='ID do tenant/usuario (Keycloak sub claim)',
                max_length=36,
            ),
        ),
    ]
