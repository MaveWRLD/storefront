from django.core.management.base import BaseCommand
from django.db.models import Count, F

from catalog.models import AxisValue, ProductAxis, VariantAxisValue


class Command(BaseCommand):
    """Read-only audit of the axis-value vocabulary registry.

    Run this between the additive migrations (0004-0006) and the tightening
    one (0007): it answers the same question 0007's NOT NULL would, but as a
    readable report rather than an IntegrityError that fails a deploy
    mid-transaction. Exits non-zero on any failure so it can gate CI.

    This is also the backend's answer to "how do we observe unlabelled
    values". The condition is state, not an event — "how many rows are
    unlabelled" is a query — so a metric would be the wrong instrument, and
    a per-product-labelled counter would be a cardinality problem against a
    hard active-series cap for a number that is provably zero once 0007's
    check constraint is in place.
    """
    help = 'Verify every axis value resolves to a vocabulary entry.'

    def handle(self, *args, **options):
        failures = []

        checks = [
            ('axis values with no vocabulary entry',
             AxisValue.objects.filter(vocabulary_value__isnull=True)),
            ('axis values with a blank label',
             AxisValue.objects.filter(label='')),
            ('axes with no vocabulary',
             ProductAxis.objects.filter(vocabulary__isnull=True)),
            ('axis values whose label drifted from the registry',
             AxisValue.objects.exclude(label=F('vocabulary_value__label'))),
            ('axis values whose name drifted from the registry',
             AxisValue.objects.exclude(name=F('vocabulary_value__value'))),
            ('axis values whose code drifted from the registry',
             AxisValue.objects.exclude(code=F('vocabulary_value__code'))),
            ('axis values drawing from another axis\'s vocabulary',
             AxisValue.objects.exclude(
                 vocabulary_value__vocabulary_id=F('axis__vocabulary_id'))),
            ('variant links with a blank label',
             VariantAxisValue.objects.filter(axis_value__label='')),
        ]

        for description, queryset in checks:
            count = queryset.count()
            if count:
                failures.append(f'{count} {description}')
                self.stderr.write(self.style.ERROR(f'FAIL  {count} {description}'))
                for row in queryset[:20]:
                    self.stderr.write(f'        {row!r} (pk={row.pk})')
            else:
                self.stdout.write(self.style.SUCCESS(f'ok    0 {description}'))

        # Proves 0007's unique_product_axis_vocabulary will apply cleanly.
        mixed = list(
            ProductAxis.objects.values('product', 'vocabulary')
            .annotate(n=Count('id')).filter(n__gt=1))
        if mixed:
            failures.append(f'{len(mixed)} products with a repeated axis vocabulary')
            self.stderr.write(self.style.ERROR(
                f'FAIL  {len(mixed)} products draw two axes from one vocabulary'))
            for row in mixed:
                self.stderr.write(f'        {row}')
        else:
            self.stdout.write(self.style.SUCCESS(
                'ok    0 products with a repeated axis vocabulary'))

        self.stdout.write('')
        self.stdout.write(
            f'{VariantAxisValue.objects.count()} variant axis links, '
            f'{AxisValue.objects.count()} axis values, '
            f'{ProductAxis.objects.count()} axes')
        self.stdout.write('')
        self.stdout.write('Values in use (vocabulary / value / code / label):')
        in_use = sorted({
            (av.vocabulary_value.vocabulary.key, av.name, av.code, av.label)
            for av in AxisValue.objects.select_related(
                'vocabulary_value__vocabulary')
            if av.vocabulary_value_id
        })
        for key, value, code, label in in_use:
            # The line that proves labels were authored, not derived: waist
            # labels match their code, colour labels match their value.
            self.stdout.write(f'  {key:16} {value:12} {code:6} {label}')

        if failures:
            self.stderr.write('')
            self.stderr.write(self.style.ERROR(
                f'{len(failures)} check(s) failed — do NOT apply '
                f'0007_require_axis_vocabulary yet.'))
            raise SystemExit(1)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('All checks passed.'))
