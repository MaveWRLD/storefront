import pytest
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Product, ProductAxis, Variant, VariantAxisValue


@pytest.mark.django_db
class TestVariantAxisValueModel:
    def test_variant_records_one_value_per_axis(self, product, small, olive):
        variant = Variant.objects.create(
            product=product, sku='test-shirt-s-r', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=small)
        VariantAxisValue.objects.create(variant=variant, axis_value=olive)

        assert set(variant.axis_values.values_list('axis_value__name', flat=True)) == {
            'S', 'Olive'}

    def test_same_variant_axis_value_pair_cannot_repeat(self, product, small):
        variant = Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=small)

        with pytest.raises(Exception):
            VariantAxisValue.objects.create(variant=variant, axis_value=small)


@pytest.mark.django_db
class TestVariantAxisValueApi:
    def test_admin_creates_variant_with_axis_values(self, admin_client, product, small, olive):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/',
            {'sku': 'test-shirt-s-r', 'unit_price': 1000,
             'axis_value_ids': [small.id, olive.id]},
        )
        assert response.status_code == status.HTTP_201_CREATED
        variant = Variant.objects.get(sku='test-shirt-s-r')
        got = {(row['axis'], row['value']) for row in response.data['axis_values']}
        assert got == {('Size', 'S'), ('Colour', 'Olive')}
        assert set(variant.axis_values.values_list('axis_value_id', flat=True)) == {
            small.id, olive.id}

    def test_rejects_axis_value_from_another_product(
            self, admin_client, product, collection, small, olive,
            size_letter_vocab, make_axis_value):
        other_product = Product.objects.create(
            title='Other', slug='other', collection=collection)
        other_axis = ProductAxis.objects.create(
            product=other_product, name='Size', vocabulary=size_letter_vocab)
        other_value = make_axis_value(other_axis, 'S')

        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/',
            {'sku': 'bad-sku', 'unit_price': 1000,
             'axis_value_ids': [other_value.id, olive.id]},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_two_values_from_the_same_axis(self, admin_client, product, small, large):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/',
            {'sku': 'bad-sku', 'unit_price': 1000,
             'axis_value_ids': [small.id, large.id]},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_missing_axis(self, admin_client, product, small, color_axis):
        # product has both Size and Color axes (color_axis forces the
        # second axis to exist); only Size supplied.
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/',
            {'sku': 'bad-sku', 'unit_price': 1000, 'axis_value_ids': [small.id]},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_duplicate_variant_combination(self, admin_client, product, small, olive, rust):
        Variant.objects.create(product=product, sku='existing', unit_price=1000)
        existing = Variant.objects.get(sku='existing')
        VariantAxisValue.objects.create(variant=existing, axis_value=small)
        VariantAxisValue.objects.create(variant=existing, axis_value=olive)

        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/',
            {'sku': 'dup', 'unit_price': 1000,
             'axis_value_ids': [small.id, olive.id]},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # A different color for the same size is fine — different combination.
        ok_response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/',
            {'sku': 'not-dup', 'unit_price': 1000,
             'axis_value_ids': [small.id, rust.id]},
        )
        assert ok_response.status_code == status.HTTP_201_CREATED

    def test_admin_can_update_a_variants_axis_values(self, admin_client, product, small, large, olive):
        variant = Variant.objects.create(product=product, sku='test-shirt', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=small)
        VariantAxisValue.objects.create(variant=variant, axis_value=olive)

        response = admin_client.patch(
            f'/store-admin/products/{product.id}/variants/{variant.id}/',
            {'axis_value_ids': [large.id, olive.id]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert set(variant.axis_values.values_list('axis_value_id', flat=True)) == {
            large.id, olive.id}

    def test_storefront_product_detail_exposes_variant_axis_values(self, product, small, olive):
        variant = Variant.objects.create(product=product, sku='test-shirt', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=small)
        VariantAxisValue.objects.create(variant=variant, axis_value=olive)

        response = APIClient().get(f'/store-front/products/{product.slug}/')
        assert response.status_code == status.HTTP_200_OK
        [variant_data] = response.data['variants']
        got = {(row['axis'], row['value']) for row in variant_data['axis_values']}
        assert got == {('Size', 'S'), ('Colour', 'Olive')}
