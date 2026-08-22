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
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def variant(collection):
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=5)


@pytest.fixture
def make_order(variant):
    def _make(order_status=Order.STATUS_COMPLETED, customer=None, quantity=1, **kwargs):
        defaults = dict(
            fulfillment_method=Order.FULFILLMENT_PICKUP,
            payment_status=Order.PAYMENT_STATUS_COMPLETE,
            status=order_status,
            customer=customer,
        )
        if customer is None:
            defaults.update(shipping_address={
                'recipient_name': 'Guest', 'email': 'guest@example.com',
                'phone': '0800000000', 'street_address': '1 Test St',
                'city': 'Accra', 'region': 'Greater Accra',
                'coordinates': {'lat': 5.6, 'lng': -0.2},
            })
        defaults.update(kwargs)
        order = Order.objects.create(**defaults)
        item = OrderItem.objects.create(
            order=order, variant=variant, quantity=quantity,
            unit_price=variant.unit_price)
        return order, item
    return _make


@pytest.fixture
def customer_and_client():
    user = User.objects.create_user(
        email='shopper@example.com', password='pw12345')
    customer = Customer.objects.get(user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return customer, client


@pytest.mark.django_db
class TestRequestReturn:
    def test_customer_requests_return_on_completed_order(self, customer_and_client, make_order):
        customer, client = customer_and_client
        order, item = make_order(customer=customer)

        response = client.post('/store-front/returns/', {
            'order_id': order.id, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Wrong size',
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['status'] == Return.STATUS_PENDING_REVIEW
        assert 'instructions' in response.data
        assert Return.objects.filter(order_item=item).exists()

    def test_guest_requests_return_via_order_id_and_email(self, make_order):
        order, item = make_order(customer=None)
        client = APIClient()

        response = client.post('/store-front/returns/', {
            'order_id': order.id, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Damaged', 'email': 'guest@example.com',
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert Return.objects.filter(order_item=item).exists()

    def test_guest_return_rejected_with_wrong_email(self, make_order):
        order, item = make_order(customer=None)
        client = APIClient()

        response = client.post('/store-front/returns/', {
            'order_id': order.id, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Damaged', 'email': 'someoneelse@example.com',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Return.objects.filter(order_item=item).exists()

    def test_cannot_request_return_on_order_that_is_not_completed(self, customer_and_client, make_order):
        customer, client = customer_and_client
        order, item = make_order(customer=customer, order_status=Order.STATUS_CONFIRMED)

        response = client.post('/store-front/returns/', {
            'order_id': order.id, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Changed my mind',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Return.objects.filter(order_item=item).exists()

    def test_customer_cannot_request_return_on_someone_elses_order(self, customer_and_client, make_order):
        _, client = customer_and_client
        other_user = User.objects.create_user(
            email='other@example.com', password='pw12345')
        other_customer = Customer.objects.get(user=other_user)
        order, item = make_order(customer=other_customer)

        response = client.post('/store-front/returns/', {
            'order_id': order.id, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Not mine',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Return.objects.filter(order_item=item).exists()

    def test_cannot_request_return_for_more_than_ordered_quantity(self, customer_and_client, make_order):
        customer, client = customer_and_client
        order, item = make_order(customer=customer, quantity=1)

        response = client.post('/store-front/returns/', {
            'order_id': order.id, 'order_item_id': item.id,
            'quantity': 2, 'reason': 'Too many',
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
