import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from catalog.models import (
    Product, ProductAxis, Variant, VariantAxisValue, Vocabulary,
)

User = get_user_model()


@pytest.fixture
def waist_product(collection, size_waist_vocab, make_axis_value):
    """A trousers-shaped product — the case the whole feature exists for.
    Its `value` is a bare '30', which means nothing to a shopper sitting
    next to an 'S'."""
    product = Product.objects.create(
        title='Test Chino', slug='test-chino', collection=collection)
    axis = ProductAxis.objects.create(
        product=product, name='Size', sort_order=0,
        vocabulary=size_waist_vocab)
    value = make_axis_value(axis, '30')
    variant = Variant.objects.create(
        product=product, sku='test-chino-w30', unit_price=1000)
    VariantAxisValue.objects.create(variant=variant, axis_value=value)
    return product


@pytest.mark.django_db
class TestVariantAxisValueLabels:
    def test_every_axis_value_carries_a_label(self, product, small, olive):
        variant = Variant.objects.create(
            product=product, sku='test-shirt-s-olv', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=small)
        VariantAxisValue.objects.create(variant=variant, axis_value=olive)

        response = APIClient().get(f'/store-front/products/{product.slug}/')

        rows = response.data['variants'][0]['axis_values']
        assert all(row['label'] for row in rows)
        assert {tuple(row) for row in [sorted(r) for r in rows]} == {
            ('axis', 'code', 'label', 'value')}

    def test_waist_label_is_the_code_not_the_bare_number(self, waist_product):
        response = APIClient().get(
            f'/store-front/products/{waist_product.slug}/')

        row = response.data['variants'][0]['axis_values'][0]
        assert row['value'] == '30'          # meaningless on its own
        assert row['label'] == 'W30'         # what the UI renders

    def test_colour_label_is_the_value_not_the_sku_token(self, product, olive):
        variant = Variant.objects.create(
            product=product, sku='test-shirt-olv', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=olive)

        response = APIClient().get(f'/store-front/products/{product.slug}/')

        row = response.data['variants'][0]['axis_values'][0]
        assert row['code'] == 'OLV'
        assert row['label'] == 'Olive'


@pytest.mark.django_db
class TestProductAxisLabels:
    """The second render surface: the axis picker, shown before any variant
    is chosen. Without a label here the storefront still needs a
    conditional."""

    def test_axis_values_carry_labels(self, waist_product):
        response = APIClient().get(
            f'/store-front/products/{waist_product.slug}/')

        value = response.data['axes'][0]['values'][0]
        assert value['name'] == '30'
        assert value['label'] == 'W30'

    def test_axis_exposes_its_vocabulary_key(self, waist_product):
        response = APIClient().get(
            f'/store-front/products/{waist_product.slug}/')

        assert response.data['axes'][0]['vocabulary'] == 'size_waist_in'


@pytest.mark.django_db
class TestLabelCostsNoQueries:
    def test_label_is_served_without_an_extra_join(self, product, small, olive):
        """Guards the entire rationale for denormalizing label onto
        AxisValue. If someone 'simplifies' the serializer source to
        axis_value.vocabulary_value.label, this catches the N+1 that
        reintroduces."""
        for i in range(3):
            variant = Variant.objects.create(
                product=product, sku=f'test-shirt-{i}', unit_price=1000)
            VariantAxisValue.objects.create(variant=variant, axis_value=small)

        client = APIClient()
        url = f'/store-front/products/{product.slug}/'
        client.get(url)  # warm any lazily-built caches

        with CaptureQueriesContext(connection) as captured:
            response = client.get(url)

        assert response.status_code == 200
        assert all(v['axis_values'][0]['label'] for v in response.data['variants'])
        # Reading label must not scale with the number of variants.
        vocabulary_joins = [
            q for q in captured.captured_queries
            if 'catalog_vocabularyvalue' in q['sql']]
        assert vocabulary_joins == []
