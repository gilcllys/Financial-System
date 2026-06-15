import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0001_initial'),
        ('cards', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Expense',
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
                ('category', models.ForeignKey(
                    db_column='category_id',
                    db_index=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='expenses',
                    to='catalog.expensecategory',
                )),
                ('payment_method', models.CharField(
                    choices=[('dinheiro', 'Dinheiro'), ('cartao', 'Cartão')],
                    db_column='payment_method',
                    db_index=True,
                    default='dinheiro',
                    max_length=10,
                )),
                ('credit_card', models.ForeignKey(
                    blank=True,
                    db_column='credit_card_id',
                    db_index=True,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='expenses',
                    to='cards.creditcard',
                )),
                ('description', models.CharField(db_column='description', db_index=True, max_length=255)),
                ('quantity', models.IntegerField(db_column='quantity', db_index=True)),
                ('amount', models.DecimalField(
                    db_column='amount', db_index=True, decimal_places=2, max_digits=10,
                )),
                ('date', models.DateField(db_column='date', db_index=True)),
            ],
            options={
                'verbose_name': 'Expense',
                'verbose_name_plural': 'Expenses',
                'db_table': 'expenses',
            },
        ),
    ]
