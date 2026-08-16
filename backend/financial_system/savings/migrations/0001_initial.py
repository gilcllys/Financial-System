from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SavingsGoal',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.CharField(db_column='tenant_id', db_index=True, max_length=36)),
                ('name', models.CharField(db_column='name', max_length=120)),
                ('target_amount', models.DecimalField(blank=True, db_column='target_amount', decimal_places=2, max_digits=12, null=True)),
                ('color', models.CharField(db_column='color', default='#6366f1', max_length=7)),
                ('icon', models.CharField(db_column='icon', default='🐷', max_length=10)),
            ],
            options={'db_table': 'savings_goals', 'verbose_name': 'Savings Goal'},
        ),
        migrations.CreateModel(
            name='SavingsDeposit',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.CharField(db_column='tenant_id', db_index=True, max_length=36)),
                ('amount', models.DecimalField(db_column='amount', decimal_places=2, help_text='Positivo = aporte, negativo = retirada.', max_digits=12)),
                ('date', models.DateField(db_column='date')),
                ('description', models.CharField(blank=True, db_column='description', default='', max_length=255)),
                ('goal', models.ForeignKey(db_column='goal_id', on_delete=django.db.models.deletion.CASCADE, related_name='deposits', to='savings.savingsgoal')),
            ],
            options={'db_table': 'savings_deposits', 'ordering': ['-date', '-id']},
        ),
        migrations.AddIndex(
            model_name='savingsgoal',
            index=models.Index(fields=['tenant_id'], name='savings_goal_tenant_idx'),
        ),
        migrations.AddIndex(
            model_name='savingsdeposit',
            index=models.Index(fields=['tenant_id', 'date'], name='savings_dep_tenant_date_idx'),
        ),
    ]
