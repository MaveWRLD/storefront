import pytest

from catalog.models import Variant


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

    def test_available_is_inventory_minus_allocated(self, product):
        variant = Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000,
            inventory=5, allocated=2)

        assert variant.available == 3

    def test_available_is_none_when_inventory_not_tracked(self, product):
        made_to_order = Variant.objects.create(
            product=product, sku='test-shirt-mto', unit_price=1000,
            inventory=0, allocated=0, track_inventory=False)

        assert made_to_order.available is None

    def test_in_stock_is_false_once_fully_allocated_even_with_inventory_left(self, product):
        variant = Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000,
            inventory=5, allocated=5)

        assert variant.available == 0
        assert variant.in_stock is False

    def test_product_in_stock_false_once_every_variant_fully_allocated(self, product):
        """Product.in_stock must agree with Variant.in_stock/available
        (inventory - allocated), not raw inventory — a product with stock
        entirely allocated to pending orders has nothing left to sell."""
        Variant.objects.create(
            product=product, sku='test-shirt-s', unit_price=1000,
            inventory=5, allocated=5)

        assert product.in_stock is False

    def test_product_can_have_axes_with_values(
            self, product, size_axis, make_axis_value):
        make_axis_value(size_axis, 'S')
        make_axis_value(size_axis, 'L')

        assert product.axes.count() == 1
        assert list(size_axis.values.values_list('name', flat=True)) == ['S', 'L']
        # Display copy comes from the registry, never from the product.
        assert list(size_axis.values.values_list('label', flat=True)) == ['S', 'L']
