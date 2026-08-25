from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from orders.models import Order

User = get_user_model()


@pytest.fixture
def guest_order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        shipping_address={
            'recipient_name': 'Guest One', 'email': 'guest1@example.com',
            'phone': '0800000000', 'street_address': '1 Test St',
            'city': 'Accra', 'region': 'Greater Accra',
            'coordinates': {'lat': 5.6, 'lng': -0.2},
        },
    )


@pytest.mark.django_db
class TestInvoiceDownload:
    def test_guest_can_download_invoice_with_correct_token(self, guest_order):
        client = APIClient()
        response = client.get(
            f'/store-front/orders/{guest_order.id}/invoice/',
            {'token': guest_order.guest_token})

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'

    def test_guest_is_rejected_with_wrong_token(self, guest_order):
        client = APIClient()
        response = client.get(
            f'/store-front/orders/{guest_order.id}/invoice/',
            {'token': 'wrong-token'})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_guest_is_rejected_with_no_token(self, guest_order):
        client = APIClient()
        response = client.get(f'/store-front/orders/{guest_order.id}/invoice/')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_customer_can_download_their_own_order_invoice(self):
        from customers.models import Customer
        user = User.objects.create_user(password='pw', email='shopper@example.com')
        customer = Customer.objects.get(user=user)
        order = Order.objects.create(
            customer=customer, fulfillment_method=Order.FULFILLMENT_PICKUP)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(f'/store-front/orders/{order.id}/invoice/')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'

    def test_customer_cannot_download_someone_elses_order_invoice(self, guest_order):
        from customers.models import Customer
        user = User.objects.create_user(password='pw', email='shopper@example.com')
        Customer.objects.get(user=user)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(f'/store-front/orders/{guest_order.id}/invoice/')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_download_any_order_invoice(self, guest_order):
        client = APIClient()
        client.force_authenticate(user=User(is_staff=True))
        response = client.get(f'/store-admin/orders/{guest_order.id}/invoice/')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
