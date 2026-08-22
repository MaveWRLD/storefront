from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductStatus, Variant


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def make_product(collection):
    def _make(inventory=10, **overrides):
        defaults = dict(title='Test Shirt', slug='test-shirt', collection=collection)
        defaults.update(overrides)
        product = Product.objects.create(**defaults)
        Variant.objects.create(
            product=product, sku=defaults['slug'], unit_price=1000,
            inventory=inventory)
        return product
    return _make


@pytest.mark.django_db
class TestBrowseProducts:
    def test_anonymous_can_list_products(self, make_product):
        make_product()
        client = APIClient()
        response = client.get('/store-front/products/')
        assert response.status_code == status.HTTP_200_OK

    def test_published_product_shows_name_price_and_is_available_true(self, make_product):
        make_product(title='Published Shirt', slug='published-shirt',
                     status=ProductStatus.PUBLISHED)
        client = APIClient()
        response = client.get('/store-front/products/')

        item = next(p for p in response.data['results']
                    if p['title'] == 'Published Shirt')
        assert item['is_available'] is True
        assert item['variants'][0]['unit_price'] == Decimal('1000.00')
        assert 'images' in item

    def test_draft_product_still_listed_but_marked_unavailable(self, make_product):
        make_product(title='Draft Shirt', slug='draft-shirt',
                     status=ProductStatus.DRAFT)
        client = APIClient()
        response = client.get('/store-front/products/')

        item = next(p for p in response.data['results']
                    if p['title'] == 'Draft Shirt')
        assert item['is_available'] is False

    def test_archived_product_still_listed_but_marked_unavailable(self, make_product):
        make_product(title='Archived Shirt', slug='archived-shirt',
                     status=ProductStatus.ARCHIVED)
        client = APIClient()
        response = client.get('/store-front/products/')

        item = next(p for p in response.data['results']
                    if p['title'] == 'Archived Shirt')
        assert item['is_available'] is False

    def test_new_product_defaults_to_published_available(self, make_product):
        product = make_product()
        assert product.status == ProductStatus.PUBLISHED

    def test_product_detail_includes_images_list(self, make_product):
        product = make_product()
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['images'] == []
