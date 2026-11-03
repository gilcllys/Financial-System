from django.db import migrations, models


INCOME_CATEGORIES = [
    ('Salário', 'salary'),
    ('Renda extra', 'extra_income'),
    ('Rendimentos', 'returns'),
    ('Reembolso', 'reimbursement'),
    ('Outras receitas', 'other_income'),
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model('catalog', 'ExpenseCategory')
    Category.objects.filter(tenant_id='system', name='Sem categoria').update(key='uncategorized')
    Category.objects.filter(tenant_id='system', name__iexact='Receita').update(kind='receita')
    for name, key in INCOME_CATEGORIES:
        Category.objects.get_or_create(
            tenant_id='system', key=key,
            defaults={'name': name, 'description': 'Categoria padrão de receita', 'kind': 'receita'},
        )


class Migration(migrations.Migration):
    dependencies = [('catalog', '0002_populate_default_categories')]

    operations = [
        migrations.AddField(
            model_name='expensecategory', name='kind',
            field=models.CharField(choices=[('despesa', 'Despesa'), ('receita', 'Receita')], db_index=True, default='despesa', max_length=10),
        ),
        migrations.AddField(
            model_name='expensecategory', name='key',
            field=models.CharField(blank=True, db_index=True, max_length=40, null=True),
        ),
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
