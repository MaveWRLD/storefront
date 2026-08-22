from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import AxisValue, Collection, Product, ProductAxis, ProductImage, Variant

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def product(collection):
    return Product.objects.create(title='Test Shirt', slug='test-shirt', collection=collection)


IMAGE_RESPONSE_KEYS = {
    'id', 'object_key', 'alt_text', 'position', 'aspect_ratio', 'role',
    'product_id', 'variant_id', 'axis_value_id', 'src', 'srcset',
}


@pytest.mark.django_db
class TestImageResponseShape:
    def test_plain_product_image_has_exact_shape(self, product):
        image = ProductImage.objects.create(
            product=product, image_key='products/1/photo.png',
            alt_text='Front', sort_order=2, width=1600, height=1200)

        from catalog.serializers import ProductImageSerializer
        data = ProductImageSerializer(image).data

        assert set(data.keys()) == IMAGE_RESPONSE_KEYS
        assert data['object_key'] == 'products/1/photo.png'
        assert data['alt_text'] == 'Front'
        assert data['position'] == 2
        assert data['aspect_ratio'] == '4:3'
        assert data['role'] == 'PRODUCT_GALLERY'
        assert data['product_id'] == product.id
        assert data['variant_id'] is None
        assert data['axis_value_id'] is None
        assert data['src'].endswith('products/1/photo.png') or 'width=' in data['src']
        assert '400w' in data['srcset']

    def test_axis_value_tagged_image_reports_correct_role_and_ids(self, product):
        axis = ProductAxis.objects.create(product=product, name='Color')
        red = AxisValue.objects.create(axis=axis, name='Red', code='red')
        image = ProductImage.objects.create(
            product=product, image_key='k.png', axis_value=red)

        from catalog.serializers import ProductImageSerializer
        data = ProductImageSerializer(image).data

        assert data['role'] == 'AXIS_VALUE_GALLERY'
        assert data['axis_value_id'] == red.id
        assert data['variant_id'] is None

    def test_variant_tagged_image_reports_correct_role_and_ids(self, product):
        variant = Variant.objects.create(product=product, sku='test-s', unit_price=1000)
        image = ProductImage.objects.create(
            product=product, image_key='k.png', variant=variant)

        from catalog.serializers import ProductImageSerializer
        data = ProductImageSerializer(image).data

        assert data['role'] == 'VARIANT_OVERRIDE'
        assert data['variant_id'] == variant.id
        assert data['axis_value_id'] is None

    def test_admin_upload_response_uses_position_not_sort_order(self, admin_client, product):
        from io import BytesIO
        from PIL import Image as PILImage
        buf = BytesIO()
        PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
        buf.seek(0)
        buf.name = 'test.png'

        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': buf, 'position': 3}, format='multipart')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['position'] == 3
        assert 'sort_order' not in response.data


@pytest.mark.django_db
class TestImageNestingByRole:
    def test_product_images_excludes_axis_value_and_variant_tagged(self, product):
        axis = ProductAxis.objects.create(product=product, name='Color')
        red = AxisValue.objects.create(axis=axis, name='Red', code='red')
        variant = Variant.objects.create(product=product, sku='test-s', unit_price=1000)
        ProductImage.objects.create(product=product, image_key='plain.png')
        ProductImage.objects.create(product=product, image_key='axis.png', axis_value=red)
        ProductImage.objects.create(product=product, image_key='variant.png', variant=variant)

        from catalog.serializers import ProductSerializer
        data = ProductSerializer(product).data

        assert [img['object_key'] for img in data['images']] == ['plain.png']

    def test_variant_serializer_exposes_only_its_own_images(self, product):
        variant = Variant.objects.create(product=product, sku='test-s', unit_price=1000)
        other_variant = Variant.objects.create(product=product, sku='test-l', unit_price=1000)
        ProductImage.objects.create(product=product, image_key='mine.png', variant=variant)
        ProductImage.objects.create(product=product, image_key='not-mine.png', variant=other_variant)

        from catalog.serializers import VariantSerializer
        data = VariantSerializer(variant).data

        assert [img['object_key'] for img in data['images']] == ['mine.png']

    def test_axis_value_serializer_exposes_only_its_own_images(self, product):
        axis = ProductAxis.objects.create(product=product, name='Color')
        red = AxisValue.objects.create(axis=axis, name='Red', code='red')
        blue = AxisValue.objects.create(axis=axis, name='Blue', code='blue')
        ProductImage.objects.create(product=product, image_key='red.png', axis_value=red)
        ProductImage.objects.create(product=product, image_key='blue.png', axis_value=blue)

        from catalog.serializers import ProductAxisValueSerializer
        data = ProductAxisValueSerializer(red).data

        assert [img['object_key'] for img in data['images']] == ['red.png']
