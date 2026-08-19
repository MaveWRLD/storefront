from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=10)


def paid_order(variant, quantity=1, placed_at=None):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        payment_status=Order.PAYMENT_STATUS_COMPLETE,
        status=Order.STATUS_COMPLETED,
        guest_name='Guest', guest_email='guest@example.com',
        guest_phone='0800000000',
    )
    OrderItem.objects.create(
        order=order, variant=variant, quantity=quantity, unit_price=variant.unit_price)
    order.subtotal = quantity * variant.unit_price
    order.save(update_fields=['subtotal'])
    if placed_at is not None:
        Order.objects.filter(pk=order.pk).update(placed_at=placed_at)
    return order


@pytest.mark.django_db
class TestViewReports:
    """US-29: 'they should see key metrics (sales, orders, top products)
    over a selected time range.'"""

    def test_reports_show_order_count_and_total_sales(self, admin_client, variant):
        paid_order(variant, quantity=1)
        paid_order(variant, quantity=2)

        response = admin_client.get('/store-admin/reports/sales/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['order_count'] == 2
        assert response.data['total_sales'] == Decimal('3000.00')

    def test_reports_show_top_products_by_quantity_sold(self, admin_client, variant):
        other_product = Product.objects.create(
            title='Other Shirt', slug='other-shirt',
            collection=Collection.objects.create(title='Other'))
        other_variant = Variant.objects.create(
            product=other_product, sku='other-shirt', unit_price=500, inventory=10)
        paid_order(variant, quantity=5)
        paid_order(other_variant, quantity=1)

        response = admin_client.get('/store-admin/reports/sales/')

        top = response.data['top_products']
        assert top[0]['title'] == 'Test Shirt'
        assert top[0]['quantity_sold'] == 5

    def test_unpaid_orders_excluded_from_reports(self, admin_client, variant):
        unpaid = Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_PICKUP,
            guest_name='Guest', guest_email='guest@example.com',
            guest_phone='0800000000',
        )
        OrderItem.objects.create(
            order=unpaid, variant=variant, quantity=1, unit_price=variant.unit_price)

        response = admin_client.get('/store-admin/reports/sales/')

        assert response.data['order_count'] == 0

    def test_reports_filtered_by_time_range(self, admin_client, variant):
        paid_order(variant, quantity=1, placed_at='2020-01-01T00:00:00Z')
        paid_order(variant, quantity=1, placed_at='2026-01-01T00:00:00Z')

        response = admin_client.get(
            '/store-admin/reports/sales/', {'start': '2025-01-01', 'end': '2026-12-31'})

        assert response.data['order_count'] == 1

    def test_non_admin_cannot_view_reports(self):
        client = APIClient()
        client.force_authenticate(user=User())
        response = client.get('/store-admin/reports/sales/')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_view_reports(self):
        client = APIClient()
        response = client.get('/store-admin/reports/sales/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
