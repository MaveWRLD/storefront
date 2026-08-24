import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Deploy B — tightening. Ship ONLY after 0004-0006 are applied and
    `manage.py audit_axis_labels` exits 0 on the target database.

    Splitting this from the additive migrations means an unmatched row
    surfaces in an audit you ran deliberately, rather than as an
    IntegrityError that fails a deploy mid-transaction.

    Note both AlterFields issue SET NOT NULL, which takes ACCESS EXCLUSIVE
    and scans the table. Instantaneous at the current ~49 axis_value rows;
    worth planning around if the catalog grows orders of magnitude.
    """

    dependencies = [
        ('catalog', '0006_backfill_axis_vocabulary'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productaxis',
            name='vocabulary',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='axes', to='catalog.vocabulary'),
        ),
        migrations.AlterField(
            model_name='axisvalue',
            name='vocabulary_value',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='axis_values', to='catalog.vocabularyvalue'),
        ),
        migrations.AddConstraint(
            model_name='axisvalue',
            constraint=models.CheckConstraint(
                condition=~models.Q(label=''),
                name='axis_value_label_not_blank'),
        ),
    ]
