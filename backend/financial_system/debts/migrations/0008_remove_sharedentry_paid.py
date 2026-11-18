from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('debts', '0007_shared_recurring_entry_link'),
    ]

    # The reimbursement column is retained; only its table column was removed from the UI.
    operations = []
