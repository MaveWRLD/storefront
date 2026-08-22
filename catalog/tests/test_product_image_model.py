from django.db import IntegrityError
import pytest

from catalog.models import AxisValue, Collection, Product, ProductAxis, ProductImage, Variant


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def product(collection):
    return Product.objects.create(title='Test Shirt', slug='test-shirt', collection=collection)


@pytest.fixture
def axis_value(product):
    axis = ProductAxis.objects.create(product=product, name='Color')
    return AxisValue.objects.create(axis=axis, name='Red', code='red')


@pytest.fixture
def variant(product):
    return Variant.objects.create(product=product, sku='test-shirt-s', unit_price=1000)


@pytest.mark.django_db
class TestProductImageRole:
    def test_role_is_product_gallery_when_no_fk_set(self, product):
        image = ProductImage.objects.create(product=product, image_key='k.png')
        assert image.role == 'PRODUCT_GALLERY'

    def test_role_is_axis_value_gallery_when_axis_value_set(self, product, axis_value):
        image = ProductImage.objects.create(
            product=product, image_key='k.png', axis_value=axis_value)
        assert image.role == 'AXIS_VALUE_GALLERY'

    def test_role_is_variant_override_when_variant_set(self, product, variant):
        image = ProductImage.objects.create(
            product=product, image_key='k.png', variant=variant)
        assert image.role == 'VARIANT_OVERRIDE'


@pytest.mark.django_db
class TestProductImageAspectRatio:
    def test_aspect_ratio_none_when_dimensions_missing(self, product):
        image = ProductImage.objects.create(product=product, image_key='k.png')
        assert image.aspect_ratio is None

    def test_aspect_ratio_reduces_to_lowest_terms(self, product):
        image = ProductImage.objects.create(
            product=product, image_key='k.png', width=1600, height=1200)
        assert image.aspect_ratio == '4:3'

    def test_aspect_ratio_for_already_reduced_dimensions(self, product):
        image = ProductImage.objects.create(
            product=product, image_key='k.png', width=3, height=4)
        assert image.aspect_ratio == '3:4'


@pytest.mark.django_db
class TestProductImageConstraint:
    def test_db_rejects_both_axis_value_and_variant_set(self, product, axis_value, variant):
        with pytest.raises(IntegrityError):
            ProductImage.objects.create(
                product=product, image_key='k.png',
                axis_value=axis_value, variant=variant)
