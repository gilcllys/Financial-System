from django.core.management.base import BaseCommand
from django.utils import timezone

from debts.behaviors import RecurringTemplateBehavior
from debts.models import SharedDebt


class Command(BaseCommand):
    help = 'Gera as despesas recorrentes dos grupos compartilhados no mês atual.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        groups = SharedDebt.objects.filter(
            recurring_templates__is_active=True,
        ).distinct().order_by('id')

        created_count = 0
        skipped_count = 0
        for group in groups.iterator():
            result = RecurringTemplateBehavior(
                group,
                None,
                'generate_month',
                month=today.month,
                year=today.year,
            ).run().data
            created_count += len(result['created'])
            skipped_count += len(result['skipped'])

        self.stdout.write(self.style.SUCCESS(
            f'Gastos compartilhados recorrentes: {created_count} criados, '
            f'{skipped_count} já existentes ou ignorados.'
        ))
