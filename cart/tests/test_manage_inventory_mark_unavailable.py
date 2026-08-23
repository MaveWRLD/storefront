from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductImage, ProductStatus, Variant
from cart.models import Cart

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
def make_product(collection):
    def _make(inventory=5, status=ProductStatus.PUBLISHED, **overrides):
        defaults = dict(title='Test Shirt', slug='test-shirt', collection=collection)
        defaults.update(overrides)
        product = Product.objects.create(status=status, **defaults)
        product.variant = Variant.objects.create(
            product=product, sku=defaults['slug'], unit_price=1000,
            inventory=inventory)
        return product
    return _make


@pytest.fixture
def cart():
    return Cart.objects.create()


@pytest.mark.django_db
class TestManageInventoryMarkUnavailable:
    def test_out_of_stock_product_blocked_from_cart(self, cart, make_product):
        product = make_product(inventory=0)
        client = APIClient()
        response = client.post(
            '/store-front/cart/items/',
            {'variant_id': product.variant.id, 'quantity': 1})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_marking_product_unavailable_blocks_it_from_cart(self, admin_client, cart, make_product):
        product = make_product(inventory=10, status=ProductStatus.PUBLISHED)

        patch_response = admin_client.patch(
            f'/store-admin/products/{product.id}/', {'status': ProductStatus.ARCHIVED})
        assert patch_response.status_code == status.HTTP_200_OK

        client = APIClient()
        response = client.post(
            '/store-front/cart/items/',
            {'variant_id': product.variant.id, 'quantity': 1})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unavailable_product_shown_as_unavailable_on_storefront(self, make_product):
        product = make_product(status=ProductStatus.ARCHIVED)
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.data['is_available'] is False

    def test_replenished_and_republished_product_can_be_added_to_cart_again(self, admin_client, cart, make_product):
        product = make_product(inventory=0, status=ProductStatus.ARCHIVED)
        ProductImage.objects.create(product=product, image_key='gallery.png')
        ProductImage.objects.create(
            product=product, image_key='variant.png', variant=product.variant)

        admin_client.patch(
            f'/store-admin/products/{product.id}/', {'status': ProductStatus.PUBLISHED})
        Variant.objects.filter(pk=product.variant.id).update(inventory=10)

        client = APIClient()
        response = client.post(
            '/store-front/cart/items/',
            {'variant_id': product.variant.id, 'quantity': 1})
        assert response.status_code == status.HTTP_201_CREATED

    def test_published_in_stock_product_still_addable(self, cart, make_product):
        product = make_product(inventory=5, status=ProductStatus.PUBLISHED)
        client = APIClient()
        response = client.post(
            '/store-front/cart/items/',
            {'variant_id': product.variant.id, 'quantity': 1})
        assert response.status_code == status.HTTP_201_CREATED
