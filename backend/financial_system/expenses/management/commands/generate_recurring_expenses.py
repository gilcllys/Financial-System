from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.behaviors import RecurringExpenseBehavior
from expenses.models import RecurringExpenseTemplate


class Command(BaseCommand):
    help = 'Gera as despesas do mês atual para todos os gastos fixos ativos.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        tenants = RecurringExpenseTemplate.objects.filter(
            is_active=True,
        ).values_list('tenant_id', flat=True).distinct()

        created_count = 0
        skipped_count = 0
        invalid_count = 0
        for tenant_id in tenants.iterator():
            result = RecurringExpenseBehavior(
                tenant_id,
                'generate_month',
                month=today.month,
                year=today.year,
            ).run().data
            created_count += len(result['created'])
            skipped_count += len(result['skipped'])
            invalid_count += len(result['skipped_invalid'])

        self.stdout.write(self.style.SUCCESS(
            f'Gastos fixos: {created_count} criados, {skipped_count} já existentes, '
            f'{invalid_count} ignorados por falta de cartão.'
        ))
