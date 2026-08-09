from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Review, Variant
from customers.models import Customer
from orders.models import Order, OrderItem

User = get_user_model()


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def product(collection):
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)
    product.variant = Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=5)
    return product


@pytest.fixture
def customer_and_client():
    user = User.objects.create_user(
        email='shopper@example.com', password='pw12345')
    customer = Customer.objects.get(user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return customer, client


def complete_order_for(customer, product, quantity=1):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        payment_status=Order.PAYMENT_STATUS_COMPLETE,
        status=Order.STATUS_COMPLETED,
        customer=customer,
    )
    OrderItem.objects.create(
        order=order, variant=product.variant, quantity=quantity,
        unit_price=product.variant.unit_price)
    return order


@pytest.mark.django_db
class TestLeaveProductReview:
    """US-19: 'A customer should not be able to review a product they have
    not purchased.'"""

    def test_customer_reviews_a_purchased_product(self, customer_and_client, product):
        customer, client = customer_and_client
        complete_order_for(customer, product)

        response = client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 5, 'description': 'Great fit!'})

        assert response.status_code == status.HTTP_201_CREATED
        review = Review.objects.get(product=product, customer=customer)
        assert review.rating == 5
        assert review.description == 'Great fit!'

    def test_review_is_visible_on_the_product_page(self, customer_and_client, product):
        customer, client = customer_and_client
        complete_order_for(customer, product)
        client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 4, 'description': 'Nice.'})

        response = APIClient().get(f'/store-front/products/{product.id}/reviews/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['description'] == 'Nice.'

    def test_cannot_review_a_product_never_purchased(self, customer_and_client, product):
        _, client = customer_and_client

        response = client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 5, 'description': 'Nice.'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Review.objects.filter(product=product).exists()

    def test_cannot_review_a_product_from_an_order_still_pending(self, customer_and_client, product):
        customer, client = customer_and_client
        complete_order_for(customer, product)
        Order.objects.filter(customer=customer).update(status=Order.STATUS_CONFIRMED)

        response = client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 5, 'description': 'Nice.'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_anonymous_cannot_leave_a_review(self, product):
        client = APIClient()

        response = client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 5, 'description': 'Nice.'})

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_rating_must_be_between_one_and_five(self, customer_and_client, product):
        customer, client = customer_and_client
        complete_order_for(customer, product)

        response = client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 6, 'description': 'Too high.'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_anonymous_can_view_reviews(self, customer_and_client, product):
        customer, client = customer_and_client
        complete_order_for(customer, product)
        client.post(
            f'/store-front/products/{product.id}/reviews/',
            {'rating': 3, 'description': 'Ok.'})

        response = APIClient().get(f'/store-front/products/{product.id}/reviews/')

        assert response.status_code == status.HTTP_200_OK
