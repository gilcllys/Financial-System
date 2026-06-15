import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('expenses', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VitoriaDebt',
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
                ('expense', models.ForeignKey(
                    db_column='expense_id',
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vitoria_debts',
                    to='expenses.expense',
                )),
                ('is_paid', models.BooleanField(
                    db_column='is_paid',
                    default=False,
                    help_text='Indica se a dívida com a Vitória já foi paga',
                )),
            ],
            options={
                'verbose_name': 'Vitoria Debt',
                'verbose_name_plural': 'Vitoria Debts',
                'db_table': 'vitoria_debts',
            },
        ),
    ]
