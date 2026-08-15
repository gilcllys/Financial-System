from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
        ('debts', '0002_shareddebt_shareddebtinvite_shareddebtmember_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sharedentry',
            name='category',
            field=models.ForeignKey(
                blank=True,
                db_column='category_id',
                help_text='Categoria opcional da despesa compartilhada.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='shared_entries',
                to='catalog.expensecategory',
            ),
        ),
    ]
