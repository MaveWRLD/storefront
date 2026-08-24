import logging

from django.db import migrations

from catalog.migration_support.vocab_backfill import (
    build_vocab_code_signatures, build_vocab_signatures, choose_vocabulary,
    codes_are_usable,
)

logger = logging.getLogger('catalog.migrations')


def backfill(apps, schema_editor):
    """Point every existing AxisValue at a registry entry and copy its label.

    Matching is by the set of (name, code) pairs on each axis — see
    catalog/migration_support/vocab_backfill.py for why the pair, and not
    either column alone, is the key.

    Unmatched rows raise. A silent partial backfill is exactly the failure
    this work exists to prevent, and 0007's SET NOT NULL would abort on
    those rows anyway — better a readable error naming them than an opaque
    IntegrityError during a deploy.
    """
    ProductAxis = apps.get_model('catalog', 'ProductAxis')
    VocabularyValue = apps.get_model('catalog', 'VocabularyValue')

    vocabulary_values = list(
        VocabularyValue.objects.select_related('vocabulary'))
    if not vocabulary_values:
        return

    signatures = build_vocab_signatures(vocabulary_values)
    code_signatures = build_vocab_code_signatures(vocabulary_values)
    vocabulary_ids = {vv.vocabulary.key: vv.vocabulary_id for vv in vocabulary_values}
    by_key_pair = {
        (vv.vocabulary.key, vv.value, vv.code): vv
        for vv in vocabulary_values
    }
    by_key_code = {
        (vv.vocabulary.key, vv.code): vv
        for vv in vocabulary_values if vv.code
    }

    failures = []
    for axis in ProductAxis.objects.select_related('product').prefetch_related('values'):
        values = list(axis.values.all())
        if not values:
            continue

        axis_signature = {(v.name, v.code) for v in values}
        key = choose_vocabulary(axis_signature, signatures)

        # Fallback: the same size is spelled 'S' in some products and
        # 'Small' in others, so the pair pass misses the long-word rows even
        # though their codes match. Retry on codes alone and let the
        # registry's `value` win — normalizing that drift is the point of
        # having a registry.
        matched_on_code = False
        if key is None and codes_are_usable(values):
            key = choose_vocabulary({v.code for v in values}, code_signatures)
            matched_on_code = key is not None

        if key is None:
            failures.append(
                f'product {axis.product_id} ({axis.product.title!r}) '
                f'axis {axis.id} ({axis.name!r}): no single vocabulary covers '
                f'{sorted(axis_signature)}')
            continue

        axis.vocabulary_id = vocabulary_ids[key]
        axis.save(update_fields=['vocabulary'])

        renamed = []
        for value in values:
            if matched_on_code:
                vv = by_key_code[(key, value.code)]
            else:
                vv = by_key_pair[(key, value.name, value.code)]
            if value.name != vv.value:
                renamed.append(f'{value.name!r}->{vv.value!r}')
            value.vocabulary_value_id = vv.id
            value.name = vv.value
            value.code = vv.code
            value.label = vv.label
            value.save(
                update_fields=['vocabulary_value', 'name', 'code', 'label'])

        logger.info(
            'Backfilled axis %s (%r) on product %s to vocabulary %r (%d values)',
            axis.id, axis.name, axis.product_id, key, len(values))
        if renamed:
            logger.warning(
                'Normalized axis %s (%r) on product %s to vocabulary %r '
                'canonical values: %s',
                axis.id, axis.name, axis.product_id, key, ', '.join(renamed))

    if failures:
        raise RuntimeError(
            'Cannot backfill axis vocabularies — no registry entry covers '
            'these axes. Add the missing vocabulary/values in a follow-up '
            'data migration, then re-run:\n  ' + '\n  '.join(failures))


def unbackfill(apps, schema_editor):
    """Lossless reverse — clears the references, deletes nothing."""
    ProductAxis = apps.get_model('catalog', 'ProductAxis')
    AxisValue = apps.get_model('catalog', 'AxisValue')

    AxisValue.objects.update(vocabulary_value=None, label='')
    ProductAxis.objects.update(vocabulary=None)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_seed_core_vocabularies'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
