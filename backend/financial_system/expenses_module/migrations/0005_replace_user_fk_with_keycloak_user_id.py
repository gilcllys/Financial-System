import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses_module', '0004_update_categories'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- CreditCard: add keycloak_user_id, remove user_id FK ---
        migrations.AddField(
            model_name='creditcard',
            name='keycloak_user_id',
            field=models.CharField(
                db_column='keycloak_user_id',
                db_index=True,
                default='',
                help_text='UUID do usuário no Keycloak (sub claim)',
                max_length=36,
            ),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='creditcard',
            name='user_id',
        ),

        # --- Expense: add keycloak_user_id, remove user_id FK ---
        migrations.AddField(
            model_name='expense',
            name='keycloak_user_id',
            field=models.CharField(
                db_column='keycloak_user_id',
                db_index=True,
                default='',
                help_text='UUID do usuário no Keycloak (sub claim)',
                max_length=36,
            ),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='expense',
            name='user_id',
        ),
    ]
