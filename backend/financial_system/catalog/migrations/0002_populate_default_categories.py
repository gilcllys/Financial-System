from django.db import migrations

DEFAULT_CATEGORIES = [
    ('Supermercado', 'Gastos com supermercado e alimentação'),
    ('Farmácia', 'Gastos com medicamentos e farmácia'),
    ('Lazer', 'Gastos com entretenimento e lazer'),
    ('Lanche', 'Gastos com lanches e delivery'),
    ('Roupas', 'Gastos com vestuário'),
    ('Eletrônicos', 'Gastos com eletrônicos e tecnologia'),
    ('Contas de casa', 'Gastos com contas domésticas (água, luz, internet...)'),
    ('Assinaturas', 'Gastos com serviços de assinatura'),
    ('Gastos com carro', 'Gastos com combustível, manutenção e IPVA'),
    ('Diversos', 'Outros gastos não categorizados'),
    ('Sem categoria', 'Gastos que ainda não foram categorizados'),
    ('Transporte', 'Gastos com transporte público e deslocamento'),
]


def populate(apps, schema_editor):
    ExpenseCategory = apps.get_model('catalog', 'ExpenseCategory')
    for name, description in DEFAULT_CATEGORIES:
        ExpenseCategory.objects.get_or_create(
            name=name,
            tenant_id='system',
            defaults={'description': description},
        )


def depopulate(apps, schema_editor):
    ExpenseCategory = apps.get_model('catalog', 'ExpenseCategory')
    ExpenseCategory.objects.filter(tenant_id='system').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populate, depopulate),
    ]
