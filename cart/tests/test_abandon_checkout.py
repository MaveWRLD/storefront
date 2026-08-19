from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from cart.models import Cart, CartItem
from cart.test_helpers import bind_client_to_cart
from catalog.models import Collection, Product, Variant


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def variant(collection):
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=5)


@pytest.mark.django_db
class TestAbandonCheckout:
    def test_cart_with_items_is_still_retrievable_after_leaving_checkout(self, variant):
        """US-12: leaving checkout without paying must not delete the cart —
        the customer can come back and GET the same cart id to resume."""
        cart = Cart.objects.create()
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)

        client = APIClient()
        bind_client_to_cart(client, cart)
        response = client.get('/store-front/cart/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['items']) == 1

    def test_expire_abandoned_carts_command_deletes_carts_inactive_past_ttl(self, variant):
        stale_cart = Cart.objects.create()
        CartItem.objects.create(cart=stale_cart, variant=variant, quantity=1)
        Cart.objects.filter(pk=stale_cart.pk).update(
            last_activity=timezone.now() - timedelta(days=31))

        call_command('expire_abandoned_carts')

        assert not Cart.objects.filter(pk=stale_cart.pk).exists()

    def test_adding_item_bumps_cart_last_activity(self, variant):
        cart = Cart.objects.create()
        Cart.objects.filter(pk=cart.pk).update(
            last_activity=timezone.now() - timedelta(days=10))
        stale_activity = Cart.objects.get(pk=cart.pk).last_activity

        client = APIClient()
        bind_client_to_cart(client, cart)
        response = client.post(
            '/store-front/cart/items/',
            {'variant_id': variant.id, 'quantity': 1})

        assert response.status_code == status.HTTP_201_CREATED
        assert Cart.objects.get(pk=cart.pk).last_activity > stale_activity

    def test_expire_abandoned_carts_command_keeps_carts_within_ttl(self, variant):
        fresh_cart = Cart.objects.create()
        CartItem.objects.create(cart=fresh_cart, variant=variant, quantity=1)
        Cart.objects.filter(pk=fresh_cart.pk).update(
            last_activity=timezone.now() - timedelta(days=29))

        call_command('expire_abandoned_carts')

        assert Cart.objects.filter(pk=fresh_cart.pk).exists()
