import pytest

from catalog.models import AxisValue, Collection, Product, ProductAxis, Variant


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def product(collection):
    return Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)


@pytest.mark.django_db
class TestCatalogVariantsAndAxes:
    """Domains — Catalog class diagram: Product 1-->0..* Variant,
    Product 1-->0..* ProductAxis 1-->0..* AxisValue."""

    def test_product_can_have_multiple_variants_each_with_own_price_and_stock(self, product):
        small = Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000, inventory=0)
        large = Variant.objects.create(
            product=product, sku='test-shirt-l', unit_price=1200, inventory=5)

        assert set(product.variants.all()) == {small, large}
        assert small.in_stock is False
        assert large.in_stock is True

    def test_product_in_stock_true_if_any_variant_has_stock(self, product):
        Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000, inventory=0)
        Variant.objects.create(
            product=product, sku='test-shirt-l', unit_price=1200, inventory=5)

        assert product.in_stock is True

    def test_product_in_stock_false_if_no_variant_has_stock(self, product):
        Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000, inventory=0)

        assert product.in_stock is False

    def test_variant_not_tracking_inventory_is_always_in_stock(self, product):
        made_to_order = Variant.objects.create(
            product=product, sku='test-shirt-mto', unit_price=1000,
            inventory=0, track_inventory=False)

        assert made_to_order.in_stock is True

    def test_product_can_have_axes_with_values(self, product):
        size_axis = ProductAxis.objects.create(
            product=product, name='Size', sort_order=0)
        AxisValue.objects.create(axis=size_axis, name='Small', code='S')
        AxisValue.objects.create(axis=size_axis, name='Large', code='L')

        assert product.axes.count() == 1
        assert list(size_axis.values.values_list('name', flat=True)) == ['Small', 'Large']
