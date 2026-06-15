from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='CreditCard',
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
                ('due_date', models.IntegerField(
                    db_column='due_date',
                    help_text='Dia do vencimento da fatura (1-31)',
                )),
                ('best_purchase_date', models.IntegerField(
                    db_column='best_purchase_date',
                    help_text='Melhor dia para compra (1-31)',
                )),
                ('last_four_digits', models.CharField(db_column='last_four_digits', max_length=4)),
            ],
            options={
                'verbose_name': 'Credit Card',
                'verbose_name_plural': 'Credit Cards',
                'db_table': 'credit_cards',
            },
        ),
    ]
