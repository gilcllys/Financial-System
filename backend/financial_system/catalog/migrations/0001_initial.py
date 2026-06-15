from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ExpenseCategory',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.CharField(
                    db_column='tenant_id',
                    db_index=True,
                    help_text='Identificador único do tenant/usuário vindo do Keycloak (sub claim)',
                    max_length=36,
                )),
                ('name', models.CharField(db_column='name', db_index=True, max_length=100)),
                ('description', models.TextField(blank=True, db_column='description', null=True)),
            ],
            options={
                'verbose_name': 'Expense Category',
                'verbose_name_plural': 'Expense Categories',
                'db_table': 'expense_categories',
            },
        ),
    ]
