from datetime import timedelta

from django.db import migrations

# Uma despesa criada muito antes do template nao pode ter sido gerada por ele.
# A folga existe porque, ao criar um template, o sistema ja materializa o mes
# corrente na mesma transacao e a despesa chega a receber um created_at alguns
# milissegundos ANTES do template (observado em producao).
TOLERANCIA_ANTERIOR = timedelta(days=1)


def _melhor_candidata(template, candidatas):
    """Escolhe uma unica despesa do mes para o template.

    Preferencia: valor identico ao do template; depois, dia mais proximo do
    day_of_month. Contas variaveis (ex: telefone) mudam de valor todo mes,
    entao o valor e criterio de desempate, nunca de exclusao.
    """
    def chave(expense):
        valor_bate = abs(expense.amount) == abs(template.amount)
        distancia_dia = abs(expense.date.day - template.day_of_month)
        return (0 if valor_bate else 1, distancia_dia, expense.id)

    return sorted(candidatas, key=chave)[0]


def ligar_historico(apps, schema_editor):
    Expense = apps.get_model('expenses', 'Expense')
    RecurringExpenseTemplate = apps.get_model('expenses', 'RecurringExpenseTemplate')

    for template in RecurringExpenseTemplate.objects.all().iterator():
        candidatas = Expense.objects.filter(
            tenant_id=template.tenant_id,
            description=template.description,
            recurring_template__isnull=True,
        )

        limite = template.created_at - TOLERANCIA_ANTERIOR
        por_mes = {}
        for expense in candidatas:
            if expense.created_at < limite:
                # Nasceu antes do template existir: e lancamento manual.
                continue
            por_mes.setdefault((expense.date.year, expense.date.month), []).append(expense)

        for _mes, expenses_do_mes in por_mes.items():
            # No maximo uma por mes, senao a constraint da 0006 quebraria.
            escolhida = _melhor_candidata(template, expenses_do_mes)
            escolhida.recurring_template = template
            escolhida.save(update_fields=['recurring_template'])


def desligar_historico(apps, schema_editor):
    Expense = apps.get_model('expenses', 'Expense')
    Expense.objects.filter(recurring_template__isnull=False).update(recurring_template=None)


class Migration(migrations.Migration):
    """
    Etapa 2 de 3: liga as despesas ja existentes ao template que as gerou.

    Sem isso a trava nova nao enxergaria o historico e o proximo
    generate_month duplicaria todos os gastos fixos do mes corrente.
    """

    dependencies = [
        ('expenses', '0004_expense_recurring_template'),
    ]

    operations = [
        migrations.RunPython(ligar_historico, desligar_historico),
    ]
