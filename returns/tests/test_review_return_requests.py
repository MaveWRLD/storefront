from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from customers.models import Customer
from orders.models import Order, OrderItem
from returns.models import Return

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def customer_and_client():
    user = User.objects.create_user(
        email='shopper@example.com', password='pw12345')
    customer = Customer.objects.get(user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return customer, client


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=5)


@pytest.fixture
def make_return(variant):
    def _make(customer):
        order = Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_PICKUP,
            payment_status=Order.PAYMENT_STATUS_COMPLETE,
            status=Order.STATUS_COMPLETED,
            customer=customer,
        )
        item = OrderItem.objects.create(
            order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
        return Return.objects.create(order_item=item, quantity=1, reason='Wrong size')
    return _make


@pytest.mark.django_db
class TestReviewReturnRequests:
    """US-26: 'When the admin inspects the item' — the admin needs to be
    able to find pending return requests, not just look one up by id
    (which only US-16/17's own requester could already do)."""

    def test_admin_can_list_all_returns(self, admin_client, customer_and_client, make_return):
        customer, _ = customer_and_client
        make_return(customer)
        make_return(customer)

        response = admin_client.get('/store/returns/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_non_admin_cannot_list_all_returns(self, customer_and_client, make_return):
        customer, client = customer_and_client
        make_return(customer)

        response = client.get('/store/returns/')

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_list_all_returns(self):
        client = APIClient()

        response = client.get('/store/returns/')

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
