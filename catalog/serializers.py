from decimal import Decimal
from rest_framework import serializers
from orders.models import Order, OrderItem
from .models import (
    AxisValue, Product, ProductAxis, ProductImage, Collection, Review, Variant,
)


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ['id', 'title', 'products_count']

    products_count = serializers.IntegerField(read_only=True)


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'sort_order']

    def create(self, validated_data):
        product_id = self.context['product_id']
        return ProductImage.objects.create(product_id=product_id, **validated_data)


class SimpleProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title']


class VariantSerializer(serializers.ModelSerializer):
    """Domains — Catalog class diagram: Product 1-->0..* Variant. Writable
    so a product's variants can be created/replaced through the product
    endpoint (US-20/US-21) — there's no separate variant-management story yet."""
    price_with_tax = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Variant
        fields = ['id', 'sku', 'unit_price', 'price_with_tax',
                  'compare_at_price', 'weight', 'track_inventory',
                  'inventory', 'in_stock']

    def get_price_with_tax(self, variant: Variant):
        return variant.unit_price.amount * Decimal(1.1)


class SimpleVariantSerializer(serializers.ModelSerializer):
    """Used where an order/cart line just needs to show what was bought —
    the product it belongs to plus its own price, not the full catalog
    Variant surface."""
    product = SimpleProductSerializer(read_only=True)

    class Meta:
        model = Variant
        fields = ['id', 'sku', 'unit_price', 'product']


class ProductAxisValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AxisValue
        fields = ['id', 'name', 'code']


class ProductAxisSerializer(serializers.ModelSerializer):
    """Domains — Catalog class diagram: Product 1-->0..* ProductAxis
    1-->0..* AxisValue (e.g. a 'Size' axis with 'Small'/'Medium' values)."""
    values = ProductAxisValueSerializer(many=True, required=False)

    class Meta:
        model = ProductAxis
        fields = ['id', 'name', 'sort_order', 'values']


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'slug', 'collection',
                  'status', 'is_available', 'in_stock', 'images',
                  'variants', 'axes']

    is_available = serializers.BooleanField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = VariantSerializer(many=True)
    axes = ProductAxisSerializer(many=True, required=False)

    def create(self, validated_data):
        variants_data = validated_data.pop('variants')
        axes_data = validated_data.pop('axes', [])
        product = Product.objects.create(**validated_data)
        for variant_data in variants_data:
            Variant.objects.create(product=product, **variant_data)
        for axis_data in axes_data:
            values_data = axis_data.pop('values', [])
            axis = ProductAxis.objects.create(product=product, **axis_data)
            for value_data in values_data:
                AxisValue.objects.create(axis=axis, **value_data)
        return product

    def update(self, instance, validated_data):
        # Variants/axes aren't re-written on a plain product update (US-21
        # is a Catalog-field edit, not a variant-management story) — pop and
        # leave the existing rows alone.
        validated_data.pop('variants', None)
        validated_data.pop('axes', None)
        return super().update(instance, validated_data)


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'date', 'customer', 'rating', 'description']
        read_only_fields = ['customer']

    def validate(self, data):
        # Business Rule (Reviews): 'A customer should not be able to review
        # a product they have not purchased.'
        customer = self.context['customer']
        product_id = self.context['product_id']
        has_purchased = OrderItem.objects.filter(
            variant__product_id=product_id,
            order__customer=customer,
            order__status=Order.STATUS_COMPLETED,
        ).exists()
        if not has_purchased:
            raise serializers.ValidationError(
                'You can only review products from a completed order.')
        return data

    def create(self, validated_data):
        return Review.objects.create(
            product_id=self.context['product_id'],
            customer=self.context['customer'],
            **validated_data)
