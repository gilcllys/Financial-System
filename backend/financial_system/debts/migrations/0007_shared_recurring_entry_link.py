import django.db.models.deletion
import django.db.models.functions.datetime
import calendar
from datetime import date
from django.db import migrations, models


def link_previous_generated_entries(apps, schema_editor):
    SharedEntry = apps.get_model('debts', 'SharedEntry')
    SharedEntryParticipant = apps.get_model('debts', 'SharedEntryParticipant')
    SharedRecurringTemplate = apps.get_model('debts', 'SharedRecurringTemplate')

    for template in SharedRecurringTemplate.objects.all().order_by('id').iterator():
        participants = set(template.participant_ids or [])
        entries = SharedEntry.objects.filter(
            shared_debt_id=template.shared_debt_id,
            recurring_template_id__isnull=True,
            description=template.description,
            amount=template.amount,
            paid_by_id=template.paid_by_id,
            payment_method=template.payment_method,
            category_id=template.category_id,
            created_at__gte=template.created_at,
        ).order_by('date', 'id')
        for entry in entries.iterator():
            last_day = calendar.monthrange(entry.date.year, entry.date.month)[1]
            expected_date = date(
                entry.date.year,
                entry.date.month,
                min(template.day_of_month, last_day),
            )
            if entry.date != expected_date:
                continue
            entry_participants = set(SharedEntryParticipant.objects.filter(
                entry_id=entry.id,
            ).values_list('member_id', flat=True))
            if entry_participants != participants:
                continue
            entry.recurring_template_id = template.id
            entry.is_recurrent = True
            entry.save(update_fields=['recurring_template', 'is_recurrent'])
            # The legacy generator allowed one entry per description/month.
            # Matching at most one row per template preserves that history.
            break


class Migration(migrations.Migration):
    dependencies = [
        ('cards', '0001_initial'),
        ('debts', '0006_sharedentry_paid'),
    ]

    operations = [
        migrations.AddField(
            model_name='sharedrecurringtemplate',
            name='credit_card',
            field=models.ForeignKey(
                blank=True,
                db_column='credit_card_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='shared_recurring_templates',
                to='cards.creditcard',
            ),
        ),
        migrations.AddField(
            model_name='sharedentry',
            name='recurring_template',
            field=models.ForeignKey(
                blank=True,
                db_column='recurring_template_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='generated_entries',
                to='debts.sharedrecurringtemplate',
            ),
        ),
        migrations.AddField(
            model_name='sharedentry',
            name='is_recurrent',
            field=models.BooleanField(
                db_column='is_recurrent',
                default=False,
                help_text='Indica se esta entrada compartilhada foi gerada por um gasto fixo.',
            ),
        ),
        migrations.RunPython(link_previous_generated_entries, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='sharedentry',
            constraint=models.UniqueConstraint(
                models.F('recurring_template'),
                django.db.models.functions.datetime.ExtractYear('date'),
                django.db.models.functions.datetime.ExtractMonth('date'),
                name='uniq_shr_entry_tpl_month',
            ),
        ),
    ]
