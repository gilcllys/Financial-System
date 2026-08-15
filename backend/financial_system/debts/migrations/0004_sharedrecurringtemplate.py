from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
        ('debts', '0003_sharedentry_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='SharedRecurringTemplate',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('description', models.CharField(db_column='description', max_length=255)),
                ('amount', models.DecimalField(db_column='amount', decimal_places=2, max_digits=10)),
                ('participant_ids', models.JSONField(db_column='participant_ids', default=list)),
                ('payment_method', models.CharField(
                    choices=[('dinheiro', 'Dinheiro'), ('cartao', 'Cartao')],
                    db_column='payment_method', default='dinheiro', max_length=10,
                )),
                ('day_of_month', models.PositiveSmallIntegerField(db_column='day_of_month', default=1)),
                ('is_active', models.BooleanField(db_column='is_active', default=True)),
                ('category', models.ForeignKey(
                    blank=True, db_column='category_id', null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='recurring_templates', to='catalog.expensecategory',
                )),
                ('paid_by', models.ForeignKey(
                    db_column='paid_by_id', on_delete=django.db.models.deletion.PROTECT,
                    related_name='recurring_templates', to='debts.shareddebtmember',
                )),
                ('shared_debt', models.ForeignKey(
                    db_column='shared_debt_id', on_delete=django.db.models.deletion.CASCADE,
                    related_name='recurring_templates', to='debts.shareddebt',
                )),
            ],
            options={'db_table': 'shared_recurring_templates',
                     'verbose_name': 'Shared Recurring Template',
                     'verbose_name_plural': 'Shared Recurring Templates'},
        ),
    ]
