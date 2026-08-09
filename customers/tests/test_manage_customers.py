from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from customers.models import Customer
from orders.models import Order

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def customer():
    user = User.objects.create_user(
        email='jane@example.com', password='pw12345',
        first_name='Jane', last_name='Doe')
    return Customer.objects.get(user=user)


@pytest.mark.django_db
class TestManageCustomers:
    """US-27: 'admin searches for a customer... opens a customer's profile...
    sees the customer's details and order history.'"""

    def test_admin_searches_customers_by_name(self, admin_client, customer):
        other_user = User.objects.create_user(
            email='bob@example.com', password='pw12345',
            first_name='Bob', last_name='Smith')
        Customer.objects.get(user=other_user)

        response = admin_client.get('/store/customers/', {'search': 'Jane'})

        assert response.status_code == status.HTTP_200_OK
        user_ids = [c['user_id'] for c in response.data]
        assert user_ids == [customer.user_id]

    def test_admin_searches_customers_by_email(self, admin_client, customer):
        response = admin_client.get('/store/customers/', {'search': 'jane@example.com'})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_admin_opens_customer_profile(self, admin_client, customer):
        response = admin_client.get(f'/store/customers/{customer.id}/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == customer.id

    def test_admin_sees_customer_order_history(self, admin_client, customer):
        Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_PICKUP,
            payment_status=Order.PAYMENT_STATUS_COMPLETE,
            status=Order.STATUS_COMPLETED,
            customer=customer,
        )
        Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_DELIVERY,
            customer=customer,
        )

        response = admin_client.get(f'/store/customers/{customer.id}/history/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_order_history_only_includes_that_customers_orders(self, admin_client, customer):
        other_user = User.objects.create_user(
            email='bob@example.com', password='pw12345')
        other_customer = Customer.objects.get(user=other_user)
        Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_PICKUP, customer=other_customer)

        response = admin_client.get(f'/store/customers/{customer.id}/history/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_non_admin_cannot_manage_customers(self, customer):
        client = APIClient()
        client.force_authenticate(user=User())
        response = client.get('/store/customers/')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_manage_customers(self, customer):
        client = APIClient()
        response = client.get('/store/customers/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
