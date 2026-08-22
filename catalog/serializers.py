import json
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.utils.text import slugify
from djmoney.money import Money
from rest_framework import serializers
from orders.models import Order, OrderItem
from media_storage.services.upload import delete_image, upload_image
from media_storage.services.image_url_builder import build_url
from .models import (
    AxisValue, Product, ProductAxis, ProductImage, Collection, Review, Variant,
)


def unique_slug_from(title, instance=None):
    base_slug = slugify(title)
    slug = base_slug
    qs = Product.objects.exclude(pk=instance.pk) if instance else Product.objects.all()
    suffix = 1
    while qs.filter(slug=slug).exists():
        suffix += 1
        slug = f'{base_slug}-{suffix}'
    return slug


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ['id', 'title', 'products_count']

    products_count = serializers.IntegerField(read_only=True)


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True)

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'sort_order', 'axis_value']

    def validate_axis_value(self, axis_value):
        # An image tagged to a swatch must be a value of an axis on this
        # same product — otherwise it could claim to swap in for a color
        # that has nothing to do with the product it's a photo of.
        product_id = self.context['product_id']
        if not axis_value.axis.product_id == int(product_id):
            raise serializers.ValidationError(
                'This axis value does not belong to this product.')
        return axis_value

    def create(self, validated_data):
        product_id = self.context['product_id']
        image_file = validated_data.pop('image')
        variant = validated_data.get('variant')
        image_key = upload_image(
            image_file, product_id=product_id,
            variant_id=variant.id if variant else None)
        return ProductImage.objects.create(
            product_id=product_id, image_key=image_key, **validated_data)

    def update(self, instance, validated_data):
        image_file = validated_data.pop('image', None)
        if image_file is not None:
            old_key = instance.image_key
            variant = validated_data.get('variant', instance.variant)
            instance.image_key = upload_image(
                image_file, product_id=instance.product_id,
                variant_id=variant.id if variant else None)
            instance.save(update_fields=['image_key'])
            delete_image(old_key)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['image'] = build_url(instance.image_key)
        return ret


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

    def create(self, validated_data):
        # Only hit when used standalone (VariantAdminViewSet) — the nested
        # product-create/update flow creates Variant rows itself and never
        # calls this.
        product_id = self.context['product_id']
        return Variant.objects.create(product_id=product_id, **validated_data)


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
    # Variants are display-only here — creation/update goes through the
    # products/{id}/variants/ sub-resource only (product+axes must exist
    # first), never through this payload.
    variants = VariantSerializer(many=True, read_only=True)
    axes = ProductAxisSerializer(many=True, required=False)
    # Auto-generated from title (like admin's prepopulated_fields) — never
    # accepted from the client.
    slug = serializers.SlugField(read_only=True)

    def _unique_slug_from(self, title, instance=None):
        base_slug = slugify(title)
        slug = base_slug
        qs = Product.objects.exclude(pk=instance.pk) if instance else Product.objects.all()
        suffix = 1
        while qs.filter(slug=slug).exists():
            suffix += 1
            slug = f'{base_slug}-{suffix}'
        return slug

    def create(self, validated_data):
        axes_data = validated_data.pop('axes', [])
        validated_data['slug'] = self._unique_slug_from(validated_data['title'])
        product = Product.objects.create(**validated_data)
        for axis_data in axes_data:
            values_data = axis_data.pop('values', [])
            axis = ProductAxis.objects.create(product=product, **axis_data)
            for value_data in values_data:
                AxisValue.objects.create(axis=axis, **value_data)
        return product

    def update(self, instance, validated_data):
        # Axes aren't re-written on a plain product update (US-21 is a
        # Catalog-field edit, not an axis-management story) — pop and
        # leave the existing rows alone. Variants are read_only here, so
        # they're never even in validated_data.
        validated_data.pop('axes', None)
        new_title = validated_data.get('title')
        if new_title and new_title != instance.title:
            validated_data['slug'] = self._unique_slug_from(new_title, instance=instance)
        return super().update(instance, validated_data)


class CreateProductSerializer(serializers.Serializer):
    """Admin product creation. Multipart request, two parts:
      - 'data': JSON string — {name, price: {amount, currency},
        axes: [{name, sortOrder, allowedValues: [{name, code}]}]}
      - 'images': one or more files (>=1 required)

    Unlike the plain ProductSerializer.create, axes+values aren't optional
    here — a product created through this endpoint must define its full
    set of variant dimensions (any axis names, not just size/color) up
    front, each with at least one allowed value, before any Variant can be
    added via the products/{id}/variants/ sub-resource. No `collection` is
    collected here — assign one afterwards via a plain update, if needed."""
    data = serializers.CharField(write_only=True)
    images = serializers.ListField(
        child=serializers.ImageField(), allow_empty=False, write_only=True,
        error_messages={'empty': 'At least one image is required.'})

    def validate_data(self, raw):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            raise serializers.ValidationError("'data' must be valid JSON.")
        if not isinstance(parsed, dict):
            raise serializers.ValidationError("'data' must be a JSON object.")

        errors = {}

        title = (parsed.get('name') or '').strip()
        if not title:
            errors['name'] = 'This field may not be blank.'
        elif Product.objects.filter(title=title).exists():
            errors['name'] = 'A product with this name already exists.'

        price = parsed.get('price') or {}
        amount = None
        try:
            amount = Decimal(str(price.get('amount')))
            if amount <= 0:
                raise InvalidOperation
        except (TypeError, InvalidOperation):
            errors.setdefault('price', {})['amount'] = 'Must be a number greater than 0.'
        currency = price.get('currency')
        if currency not in settings.CURRENCIES:
            errors.setdefault('price', {})['currency'] = (
                f"Must be one of: {', '.join(settings.CURRENCIES)}.")

        axes = parsed.get('axes') or []
        if not axes:
            errors['axes'] = 'At least one axis is required.'
        else:
            for i, axis in enumerate(axes):
                if not (axis.get('name') or '').strip():
                    errors[f'axes[{i}].name'] = 'This field may not be blank.'
                if axis.get('sortOrder', 0) < 0:
                    errors[f'axes[{i}].sortOrder'] = 'Must be >= 0.'
                values = axis.get('allowedValues') or []
                if not values:
                    errors[f'axes[{i}].allowedValues'] = 'At least one allowed value is required.'
                else:
                    for j, value in enumerate(values):
                        if not (value.get('name') or '').strip():
                            errors[f'axes[{i}].allowedValues[{j}].name'] = 'This field may not be blank.'

        if errors:
            raise serializers.ValidationError(errors)

        parsed['_title'] = title
        parsed['_amount'] = amount
        parsed['_currency'] = currency
        return parsed

    def create(self, validated_data):
        data = validated_data['data']
        images = validated_data['images']

        product = Product.objects.create(
            title=data['_title'],
            slug=unique_slug_from(data['_title']),
            price=Money(data['_amount'], data['_currency']))

        for axis in data['axes']:
            axis_obj = ProductAxis.objects.create(
                product=product, name=axis['name'].strip(),
                sort_order=axis.get('sortOrder', 0))
            for value in axis['allowedValues']:
                AxisValue.objects.create(
                    axis=axis_obj, name=value['name'].strip(),
                    code=value.get('code', ''))

        # bulk_create can't run per-row I/O — upload each file first
        # (sequentially; there's no async story here), then insert the
        # rows in one bulk statement with the resulting keys.
        image_keys = [
            upload_image(image, product_id=product.id)
            for image in images
        ]
        ProductImage.objects.bulk_create([
            ProductImage(product=product, image_key=key, sort_order=i)
            for i, key in enumerate(image_keys)
        ])
        return product


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
