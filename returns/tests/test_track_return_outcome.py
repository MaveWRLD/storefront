from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from customers.models import Customer
from orders.models import Order, OrderItem
from payment.models import Payment
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
def customer_and_client():
    user = User.objects.create_user(
        email='shopper@example.com', password='pw12345')
    customer = Customer.objects.get(user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return customer, client


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def pending_return(variant, customer_and_client):
    customer, _ = customer_and_client
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        payment_status=Order.PAYMENT_STATUS_COMPLETE,
        status=Order.STATUS_COMPLETED,
        customer=customer,
    )
    item = OrderItem.objects.create(
        order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
    Payment.objects.create(
        order=order, reference='pay_ref_123', amount=variant.unit_price,
        status=Payment.STATUS_SUCCESS)
    return Return.objects.create(
        order_item=item, quantity=1, reason='Wrong size')


@pytest.mark.django_db
class TestTrackReturnOutcome:
    """US-17: Business Rule (Returns & Refunds) 'Rejected return: item back
    to customer, no refund; approved: Paystack refund'."""

    def test_admin_approving_a_return_issues_a_paystack_refund(self, admin_client, pending_return):
        with patch('payment.gateways.paystack.PaystackGateway.refund_transaction') as mocked:
            mocked.return_value = {'status': 'success'}
            response = admin_client.patch(
                f'/store-admin/returns/{pending_return.id}/', {'action': 'approve'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == Return.STATUS_APPROVED
        mocked.assert_called_once_with('pay_ref_123')
        pending_return.refresh_from_db()
        assert pending_return.status == Return.STATUS_APPROVED

    def test_admin_rejecting_a_return_requires_a_reason_and_issues_no_refund(self, admin_client, pending_return):
        with patch('payment.gateways.paystack.PaystackGateway.refund_transaction') as mocked:
            response = admin_client.patch(
                f'/store-admin/returns/{pending_return.id}/',
                {'action': 'reject', 'reason': 'Item shows signs of wear'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == Return.STATUS_REJECTED
        assert response.data['resolution_reason'] == 'Item shows signs of wear'
        mocked.assert_not_called()

    def test_rejecting_without_a_reason_is_rejected(self, admin_client, pending_return):
        response = admin_client.patch(
            f'/store-admin/returns/{pending_return.id}/', {'action': 'reject'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        pending_return.refresh_from_db()
        assert pending_return.status == Return.STATUS_PENDING_REVIEW

    def test_non_admin_cannot_approve_or_reject_a_return(self, customer_and_client, pending_return):
        _, client = customer_and_client

        response = client.patch(
            f'/store-admin/returns/{pending_return.id}/', {'action': 'approve'})

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        pending_return.refresh_from_db()
        assert pending_return.status == Return.STATUS_PENDING_REVIEW

    def test_cannot_review_a_return_that_was_already_reviewed(self, admin_client, pending_return):
        with patch('payment.gateways.paystack.PaystackGateway.refund_transaction'):
            admin_client.patch(
                f'/store-admin/returns/{pending_return.id}/', {'action': 'approve'})

        response = admin_client.patch(
            f'/store-admin/returns/{pending_return.id}/',
            {'action': 'reject', 'reason': 'Too late'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_can_track_their_return_outcome(self, customer_and_client, pending_return):
        _, client = customer_and_client
        with patch('payment.gateways.paystack.PaystackGateway.refund_transaction'):
            admin = APIClient()
            admin.force_authenticate(user=User(is_staff=True))
            admin.patch(f'/store-admin/returns/{pending_return.id}/', {'action': 'approve'})

        response = client.get(f'/store-front/returns/{pending_return.id}/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == Return.STATUS_APPROVED

    def test_customer_cannot_track_someone_elses_return(self, pending_return):
        other_user = User.objects.create_user(
            email='other@example.com', password='pw12345')
        client = APIClient()
        client.force_authenticate(user=other_user)

        response = client.get(f'/store-front/returns/{pending_return.id}/')

        assert response.status_code in (
            status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


@pytest.mark.django_db
def test_return_decision_notifies_customer(admin_client, pending_return):
    from notifications.models import Notification

    with patch('payment.gateways.paystack.PaystackGateway.refund_transaction'):
        admin_client.patch(
            f'/store-admin/returns/{pending_return.id}/', {'action': 'approve'})

    assert Notification.objects.filter(
        order=pending_return.order_item.order,
        event_type=Notification.EVENT_REFUND_DECISION).exists()
