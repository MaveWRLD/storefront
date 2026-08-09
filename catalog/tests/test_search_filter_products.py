from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant


@pytest.fixture
def collections():
    return {
        'shirts': Collection.objects.create(title='Shirts'),
        'pants': Collection.objects.create(title='Pants'),
    }


def _product_with_variant(title, slug, description, unit_price, collection):
    product = Product.objects.create(
        title=title, slug=slug, description=description, collection=collection)
    Variant.objects.create(
        product=product, sku=slug, unit_price=unit_price, inventory=5)
    return product


@pytest.fixture
def products(collections):
    return [
        _product_with_variant(
            'Blue Denim Jacket', 'blue-denim-jacket', 'A warm jacket',
            5000, collections['shirts']),
        _product_with_variant(
            'Red T-Shirt', 'red-t-shirt', 'A cotton shirt',
            1500, collections['shirts']),
        _product_with_variant(
            'Black Jeans', 'black-jeans', 'Slim fit',
            3000, collections['pants']),
    ]


@pytest.mark.django_db
class TestSearchFilterProducts:
    def test_search_by_title_returns_only_matching_products(self, products):
        client = APIClient()
        response = client.get('/store/products/', {'search': 'Jacket'})

        assert response.status_code == status.HTTP_200_OK
        titles = [p['title'] for p in response.data['results']]
        assert titles == ['Blue Denim Jacket']

    def test_search_is_case_insensitive_and_matches_description(self, products):
        client = APIClient()
        response = client.get('/store/products/', {'search': 'cotton'})

        titles = [p['title'] for p in response.data['results']]
        assert titles == ['Red T-Shirt']

    def test_filter_by_category_returns_only_that_categorys_products(self, products, collections):
        client = APIClient()
        response = client.get(
            '/store/products/', {'collection_id': collections['pants'].id})

        titles = [p['title'] for p in response.data['results']]
        assert titles == ['Black Jeans']

    def test_filter_by_price_range(self, products):
        client = APIClient()
        response = client.get(
            '/store/products/', {'unit_price__lt': 4000, 'unit_price__gt': 2000})

        titles = [p['title'] for p in response.data['results']]
        assert titles == ['Black Jeans']

    def test_no_match_returns_empty_list_not_error(self, products):
        client = APIClient()
        response = client.get('/store/products/', {'search': 'nonexistentitem'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['results'] == []
