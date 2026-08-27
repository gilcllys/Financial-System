# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debts', '0005_shared_entry_installment_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='sharedentry',
            name='paid',
            field=models.BooleanField(db_column='paid', default=False, help_text='Indica se esta despesa compartilhada ja foi paga/quitada.'),
        ),
    ]
