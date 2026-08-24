from django.db import migrations

from catalog.migration_support.vocab_backfill import SEED_VOCABULARIES


def seed(apps, schema_editor):
    """Seed the three vocabularies the catalog uses today.

    A data migration rather than a management command, because this is
    referential data the schema depends on: 0006 cannot match anything
    without it, and 0007 cannot tighten without 0006. A command someone has
    to remember to run between two migrations is a broken deploy waiting to
    happen — Railway deploys run `migrate`, not arbitrary commands. It also
    means pytest-django's test database (built by running migrations) has
    these available to every test for free.

    seed_db.py is not a candidate: it cursor.execute()s a 10k-line seed.sql
    that predates the axis models and contains zero axis references.
    """
    Vocabulary = apps.get_model('catalog', 'Vocabulary')
    VocabularyValue = apps.get_model('catalog', 'VocabularyValue')

    for spec in SEED_VOCABULARIES:
        vocabulary, _ = Vocabulary.objects.get_or_create(
            key=spec['key'],
            defaults={'label': spec['label'],
                      'description': spec['description']})
        for sort_order, (value, code, label) in enumerate(spec['values']):
            VocabularyValue.objects.get_or_create(
                vocabulary=vocabulary, value=value,
                defaults={'code': code, 'label': label,
                          'sort_order': sort_order})


def unseed(apps, schema_editor):
    """Remove only the seeded rows. 0006 reverses first and clears every
    AxisValue reference, so nothing is PROTECTing these by the time this
    runs."""
    Vocabulary = apps.get_model('catalog', 'Vocabulary')
    Vocabulary.objects.filter(
        key__in=[spec['key'] for spec in SEED_VOCABULARIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_vocabulary_registry'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
