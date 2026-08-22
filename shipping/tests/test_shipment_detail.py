from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem
from shipping.models import Shipment


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(product=product, sku='test-shirt', unit_price=1000, inventory=5)


@pytest.fixture
def delivery_order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_address={'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000', 'street_address': '1 Test St', 'city': 'Accra', 'region': 'Greater Accra', 'coordinates': {'lat': 5.6, 'lng': -0.2}})
    OrderItem.objects.create(order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
    return order


@pytest.fixture
def pickup_order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        shipping_address={'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000', 'street_address': '1 Test St', 'city': 'Accra', 'region': 'Greater Accra', 'coordinates': {'lat': 5.6, 'lng': -0.2}})
    OrderItem.objects.create(order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
    return order


@pytest.mark.django_db
class TestShipmentDetail:
    """FR-011: read-only tracking/carrier/status for an order's shipment."""

    def test_returns_tracking_carrier_and_status(self, delivery_order):
        Shipment.objects.create(
            order=delivery_order, tracking_reference='sb_track_789',
            carrier_name='GIG Logistics', status=Shipment.STATUS_OUT_FOR_DELIVERY)

        response = APIClient().get(f'/store-front/shipping/shipments/{delivery_order.id}/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['tracking_reference'] == 'sb_track_789'
        assert response.data['carrier_name'] == 'GIG Logistics'
        assert response.data['status'] == Shipment.STATUS_OUT_FOR_DELIVERY

    def test_pickup_order_has_no_shipment(self, pickup_order):
        response = APIClient().get(f'/store-front/shipping/shipments/{pickup_order.id}/')

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delivery_order_not_yet_booked_has_no_shipment(self, delivery_order):
        response = APIClient().get(f'/store-front/shipping/shipments/{delivery_order.id}/')

        assert response.status_code == status.HTTP_404_NOT_FOUND
