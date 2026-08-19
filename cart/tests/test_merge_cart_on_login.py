from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from cart.models import Cart, CartItem
from cart.services import CART_SESSION_KEY
from cart.test_helpers import bind_client_to_cart

User = get_user_model()


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def make_variant(collection):
    def _make(slug='test-shirt', inventory=10, allocated=0, track_inventory=True):
        product = Product.objects.create(
            title=slug, slug=slug, collection=collection)
        return Variant.objects.create(
            product=product, sku=slug, unit_price=1000,
            track_inventory=track_inventory, inventory=inventory, allocated=allocated)
    return _make


@pytest.fixture
def user():
    return User.objects.create_user(email='shopper@example.com', password='s3cret-pw')


def login(client, user):
    return client.post('/auth/jwt/create/', {
        'email': user.email,
        'password': 's3cret-pw',
    })


@pytest.mark.django_db
class TestMergeCartOnLogin:
    def test_no_guest_cart_nothing_to_merge(self, user):
        client = APIClient()
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        assert not Cart.objects.filter(user=user).exists()

    def test_guest_items_merged_into_new_account_cart(self, user, make_variant):
        variant = make_variant(inventory=5)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=2)

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        account_cart = Cart.objects.get(user=user)
        assert account_cart.items.get(variant=variant).quantity == 2

    def test_overlapping_variant_quantities_add_and_cap_at_available_stock(self, user, make_variant):
        variant = make_variant(inventory=5)
        account_cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=account_cart, variant=variant, quantity=3)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=4)

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        # stock=5, account already holds 3 -> remainder=2 -> merged=5, not 7.
        assert account_cart.items.get(variant=variant).quantity == 5

    def test_stock_drop_does_not_shrink_an_already_held_line(self, user, make_variant):
        variant = make_variant(inventory=5)
        account_cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=account_cart, variant=variant, quantity=3)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=4)

        # Stock drops below what the account cart already holds after both
        # carts were built.
        Variant.objects.filter(pk=variant.pk).update(inventory=2)

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        # remainder = max(2 - 3, 0) = 0 -> nothing transferred, existing
        # quantity must not be clamped down to the new stock figure.
        assert account_cart.items.get(variant=variant).quantity == 3

    def test_new_line_capped_at_available_stock(self, user, make_variant):
        variant = make_variant(inventory=2)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=5)

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        assert Cart.objects.get(user=user).items.get(variant=variant).quantity == 2

    def test_new_line_dropped_silently_when_no_stock_remains(self, user, make_variant):
        variant = make_variant(inventory=0)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=3)

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        account_cart = Cart.objects.get(user=user)
        assert not account_cart.items.filter(variant=variant).exists()

    def test_untracked_inventory_transfers_full_guest_quantity(self, user, make_variant):
        variant = make_variant(inventory=0, track_inventory=False)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=9)

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        assert Cart.objects.get(user=user).items.get(variant=variant).quantity == 9

    def test_guest_cart_deleted_and_session_pointer_cleared_after_merge(self, user, make_variant):
        variant = make_variant(inventory=5)
        guest_cart = Cart.objects.create()
        CartItem.objects.create(cart=guest_cart, variant=variant, quantity=1)
        guest_cart_id = guest_cart.id

        client = APIClient()
        bind_client_to_cart(client, guest_cart)
        response = login(client, user)

        assert response.status_code == status.HTTP_200_OK
        assert not Cart.objects.filter(pk=guest_cart_id).exists()
        assert CART_SESSION_KEY not in client.session
