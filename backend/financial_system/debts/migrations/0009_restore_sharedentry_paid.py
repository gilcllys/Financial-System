from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('debts', '0008_remove_sharedentry_paid'),
    ]

    # The field already exists since migration 0006; do not drop and recreate its data.
    operations = []
