import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses_module', '0002_populate_categories'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditCard',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(db_column='name', db_index=True, max_length=100)),
                ('due_date', models.IntegerField(db_column='due_date', help_text='Dia do vencimento da fatura (1-31)')),
                ('best_purchase_date', models.IntegerField(db_column='best_purchase_date', help_text='Melhor dia para compra (1-31)')),
                ('last_four_digits', models.CharField(db_column='last_four_digits', max_length=4)),
                ('user_id', models.ForeignKey(
                    db_column='user_id',
                    db_index=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Credit Card',
                'verbose_name_plural': 'Credit Cards',
                'db_table': 'credit_cards',
            },
        ),
        migrations.AddField(
            model_name='expense',
            name='payment_method',
            field=models.CharField(
                choices=[('dinheiro', 'Dinheiro'), ('cartao', 'Cartão')],
                db_column='payment_method',
                db_index=True,
                default='dinheiro',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='expense',
            name='credit_card',
            field=models.ForeignKey(
                blank=True,
                db_column='credit_card_id',
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                to='expenses_module.creditcard',
            ),
        ),
    ]
