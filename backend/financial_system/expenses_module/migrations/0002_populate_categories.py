from django.db import migrations


def populate_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model('expenses_module', 'ExpenseCategory')
    categories = [
        {'name': 'Salário', 'description': 'Receitas de salário'},
        {'name': 'Extra', 'description': 'Receitas extras'},
        {'name': 'Moradia', 'description': 'Despesas com moradia'},
        {'name': 'Alimentação', 'description': 'Despesas com alimentação'},
        {'name': 'Transporte', 'description': 'Despesas com transporte'},
        {'name': 'Lazer', 'description': 'Despesas com lazer'},
        {'name': 'Saúde', 'description': 'Despesas com saúde'},
        {'name': 'Educação', 'description': 'Despesas com educação'},
        {'name': 'Cartão de crédito', 'description': 'Despesas com cartão de crédito'},
        {'name': 'Outros', 'description': 'Outras despesas'},
    ]
    for cat in categories:
        ExpenseCategory.objects.get_or_create(name=cat['name'], defaults=cat)


def reverse_populate(apps, schema_editor):
    ExpenseCategory = apps.get_model('expenses_module', 'ExpenseCategory')
    ExpenseCategory.objects.filter(name__in=[
        'Salário', 'Extra', 'Moradia', 'Alimentação', 'Transporte',
        'Lazer', 'Saúde', 'Educação', 'Cartão de crédito', 'Outros',
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('expenses_module', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populate_categories, reverse_populate),
    ]
