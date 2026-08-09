from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductStatus, Variant

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
    product = Product.objects.create(
        title='Old Title', slug='old-title', collection=collection)
    Variant.objects.create(
        product=product, sku='old-title', unit_price=1000, inventory=5)
    return product


@pytest.mark.django_db
class TestUpdateProduct:
    def test_admin_update_is_reflected_immediately_on_storefront(self, admin_client, product):
        response = admin_client.patch(
            f'/store/products/{product.id}/', {'title': 'New Title'})
        assert response.status_code == status.HTTP_200_OK

        storefront_view = APIClient().get(f'/store/products/{product.id}/')
        assert storefront_view.data['title'] == 'New Title'

    def test_admin_can_toggle_availability_via_update(self, admin_client, product):
        response = admin_client.patch(
            f'/store/products/{product.id}/', {'status': ProductStatus.DRAFT})
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_available'] is False

    def test_anonymous_cannot_update_product(self, product):
        client = APIClient()
        response = client.patch(f'/store/products/{product.id}/', {'title': 'x'})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_admin_cannot_update_product(self, product):
        client = APIClient()
        client.force_authenticate(user=User())
        response = client.patch(f'/store/products/{product.id}/', {'title': 'x'})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_update_returns_400(self, admin_client, product):
        # unit_price now lives on Variant, not Product — a plain product
        # update can still be invalid via an unknown status choice.
        response = admin_client.patch(
            f'/store/products/{product.id}/', {'status': 'not-a-real-status'})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
