import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SupermarketExpense',
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
                ('store_name', models.CharField(db_column='store_name', db_index=True, max_length=100)),
                ('date', models.DateField(db_column='date', db_index=True)),
                ('address', models.CharField(
                    blank=True, db_column='address', db_index=True, max_length=100, null=True,
                )),
            ],
            options={
                'verbose_name': 'Supermarket Expense',
                'verbose_name_plural': 'Supermarket Expenses',
                'db_table': 'supermarket_expenses',
            },
        ),
        migrations.CreateModel(
            name='SupermarketExpenseItem',
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
                ('supermarket_expense', models.ForeignKey(
                    db_column='supermarket_expense_id',
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='supermarket.supermarketexpense',
                )),
                ('description', models.CharField(db_column='description', db_index=True, max_length=255)),
                ('quantity', models.IntegerField(db_column='quantity', db_index=True)),
                ('unit_price', models.DecimalField(
                    db_column='unit_price',
                    db_index=True,
                    decimal_places=2,
                    max_digits=10,
                    help_text='Preço unitário do item',
                )),
            ],
            options={
                'verbose_name': 'Supermarket Expense Item',
                'verbose_name_plural': 'Supermarket Expense Items',
                'db_table': 'supermarket_expense_items',
            },
        ),
    ]
