from django.db import migrations


def update_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model('expenses_module', 'ExpenseCategory')
    ExpenseCategory.objects.filter(name='Cartão de crédito').delete()
    ExpenseCategory.objects.get_or_create(
        name='Contas e Assinaturas',
        defaults={'description': 'Despesas com contas e assinaturas'},
    )


def reverse_update_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model('expenses_module', 'ExpenseCategory')
    ExpenseCategory.objects.filter(name='Contas e Assinaturas').delete()
    ExpenseCategory.objects.get_or_create(
        name='Cartão de crédito',
        defaults={'description': 'Despesas com cartão de crédito'},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('expenses_module', '0003_creditcard_expense_payment_method'),
    ]

    operations = [
        migrations.RunPython(update_categories, reverse_update_categories),
    ]
