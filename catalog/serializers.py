import json
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from djmoney.money import Money
from rest_framework import serializers
from orders.models import Order, OrderItem
from media_storage.services.upload import (
    InvalidImageError, delete_image, upload_image, validate_image_bytes,
)
from media_storage.services.image_url_builder import DEFAULT_SRC_WIDTH, build_srcset, build_url
from .models import (
    AxisValue, Product, ProductAxis, ProductImage, Collection, Review, Variant,
    VariantAxisValue,
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
    axis_value = serializers.PrimaryKeyRelatedField(
        queryset=AxisValue.objects.all(), required=False, allow_null=True,
        write_only=True)
    variant = serializers.PrimaryKeyRelatedField(
        queryset=Variant.objects.all(), required=False, allow_null=True,
        write_only=True)
    position = serializers.IntegerField(source='sort_order', required=False)
    object_key = serializers.CharField(source='image_key', read_only=True)
    aspect_ratio = serializers.ReadOnlyField()
    role = serializers.ReadOnlyField()
    product_id = serializers.IntegerField(read_only=True)
    variant_id = serializers.IntegerField(read_only=True)
    axis_value_id = serializers.IntegerField(read_only=True)
    src = serializers.SerializerMethodField()
    srcset = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'position', 'object_key',
                  'aspect_ratio', 'role', 'product_id', 'variant_id',
                  'axis_value_id', 'src', 'srcset', 'axis_value', 'variant']

    def get_src(self, obj):
        return build_url(obj.image_key, width=DEFAULT_SRC_WIDTH)

    def get_srcset(self, obj):
        return build_srcset(obj.image_key)

    def validate_image(self, image_file):
        data = image_file.read()
        image_file.seek(0)
        try:
            validate_image_bytes(data)
        except InvalidImageError as e:
            raise serializers.ValidationError(str(e))
        return image_file

    def validate_axis_value(self, axis_value):
        # An image tagged to a swatch must be a value of an axis on this
        # same product — otherwise it could claim to swap in for a color
        # that has nothing to do with the product it's a photo of.
        product_id = self.context['product_id']
        if not axis_value.axis.product_id == int(product_id):
            raise serializers.ValidationError(
                'This axis value does not belong to this product.')
        return axis_value

    def validate_variant(self, variant):
        # Same idea as axis_value above: an override photo must actually
        # belong to a variant of this same product.
        product_id = self.context['product_id']
        if not variant.product_id == int(product_id):
            raise serializers.ValidationError(
                'This variant does not belong to this product.')
        return variant

    def validate(self, attrs):
        if attrs.get('axis_value') and attrs.get('variant'):
            raise serializers.ValidationError(
                'An image can be tagged to an axis value (swatch) or a '
                'variant (override), not both.')
        return attrs

    def create(self, validated_data):
        product_id = self.context['product_id']
        image_file = validated_data.pop('image')
        variant = validated_data.get('variant')
        result = upload_image(
            image_file, product_id=product_id,
            variant_id=variant.id if variant else None)
        return ProductImage.objects.create(
            product_id=product_id, image_key=result.key,
            width=result.width, height=result.height, **validated_data)

    def update(self, instance, validated_data):
        image_file = validated_data.pop('image', None)
        if image_file is not None:
            old_key = instance.image_key
            variant = validated_data.get('variant', instance.variant)
            result = upload_image(
                image_file, product_id=instance.product_id,
                variant_id=variant.id if variant else None)
            instance.image_key = result.key
            instance.width = result.width
            instance.height = result.height
            instance.save(update_fields=['image_key', 'width', 'height'])
            delete_image(old_key)
        return super().update(instance, validated_data)


class SimpleProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title']


class VariantAxisValueSerializer(serializers.ModelSerializer):
    """Read shape for a variant's selected axis values — e.g.
    {'axis': 'Size', 'value': 'Medium', 'code': 'M'} — so a client can build
    a 'Size: Medium / Color: Red' selector without a second round-trip to
    /products/{slug}/ to cross-reference axis names."""
    axis = serializers.CharField(source='axis_value.axis.name', read_only=True)
    value = serializers.CharField(source='axis_value.name', read_only=True)
    code = serializers.CharField(source='axis_value.code', read_only=True)

    class Meta:
        model = VariantAxisValue
        fields = ['axis', 'value', 'code']


class VariantSerializer(serializers.ModelSerializer):
    """Domains — Catalog class diagram: Product 1-->0..* Variant. Writable
    so a product's variants can be created/replaced through the product
    endpoint (US-20/US-21) — there's no separate variant-management story yet."""
    price_with_tax = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    axis_values = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    # Write side: exactly one AxisValue id per axis defined on the parent
    # product. Named distinctly from the read-only `axis_values` above so
    # input/output don't collide on shape (ids in, expanded objects out).
    axis_value_ids = serializers.PrimaryKeyRelatedField(
        queryset=AxisValue.objects.all(), many=True, required=False,
        write_only=True,
        help_text="One AxisValue id per axis defined on this variant's product.")

    class Meta:
        model = Variant
        fields = ['id', 'sku', 'unit_price', 'price_with_tax',
                  'compare_at_price', 'weight', 'track_inventory',
                  'inventory', 'in_stock', 'axis_values', 'images',
                  'axis_value_ids']

    def get_price_with_tax(self, variant: Variant):
        return variant.unit_price.amount * Decimal(1.1)

    def get_axis_values(self, variant: Variant):
        return VariantAxisValueSerializer(
            variant.axis_values.select_related('axis_value__axis'),
            many=True).data

    def get_images(self, variant: Variant):
        return ProductImageSerializer(variant.images.all(), many=True).data

    def _resolve_axis_values(self, product_id, axis_values):
        """Business Rule (Catalog): a variant must select exactly one
        AxisValue per axis defined on its product — no axis left unpicked,
        no axis picked twice. Enforced here, not by the schema (the
        VariantAxisValue table only stops the identical row repeating)."""
        for axis_value in axis_values:
            if axis_value.axis.product_id != int(product_id):
                raise serializers.ValidationError(
                    {'axis_value_ids': f"'{axis_value.name}' does not belong to this product."})

        axis_ids = [axis_value.axis_id for axis_value in axis_values]
        if len(axis_ids) != len(set(axis_ids)):
            raise serializers.ValidationError(
                {'axis_value_ids': 'Only one value per axis is allowed.'})

        product_axis_ids = set(
            ProductAxis.objects.filter(product_id=product_id).values_list('id', flat=True))
        if set(axis_ids) != product_axis_ids:
            raise serializers.ValidationError(
                {'axis_value_ids': 'A value must be provided for every axis on this product.'})

    def _ensure_no_duplicate_variant(self, product_id, axis_values, exclude_variant_id=None):
        """Business Rule (Catalog): no two variants of the same product may
        select the identical combination of axis values."""
        wanted = {axis_value.id for axis_value in axis_values}
        siblings = Variant.objects.filter(product_id=product_id)
        if exclude_variant_id:
            siblings = siblings.exclude(pk=exclude_variant_id)
        for sibling in siblings.prefetch_related('axis_values'):
            existing = {link.axis_value_id for link in sibling.axis_values.all()}
            if existing == wanted:
                raise serializers.ValidationError(
                    {'axis_value_ids': 'Another variant already uses this exact combination of axis values.'})

    def create(self, validated_data):
        # Only hit when used standalone (VariantAdminViewSet) — the nested
        # product-create/update flow creates Variant rows itself and never
        # calls this.
        product_id = self.context['product_id']
        axis_values = validated_data.pop('axis_value_ids', [])
        self._resolve_axis_values(product_id, axis_values)
        self._ensure_no_duplicate_variant(product_id, axis_values)
        variant = Variant.objects.create(product_id=product_id, **validated_data)
        VariantAxisValue.objects.bulk_create([
            VariantAxisValue(variant=variant, axis_value=axis_value)
            for axis_value in axis_values
        ])
        return variant

    def update(self, instance, validated_data):
        axis_values = validated_data.pop('axis_value_ids', None)
        if axis_values is not None:
            self._resolve_axis_values(instance.product_id, axis_values)
            self._ensure_no_duplicate_variant(
                instance.product_id, axis_values, exclude_variant_id=instance.pk)
            instance.axis_values.all().delete()
            VariantAxisValue.objects.bulk_create([
                VariantAxisValue(variant=instance, axis_value=axis_value)
                for axis_value in axis_values
            ])
        return super().update(instance, validated_data)


class SimpleVariantSerializer(serializers.ModelSerializer):
    """Used where an order/cart line just needs to show what was bought —
    the product it belongs to plus its own price, not the full catalog
    Variant surface."""
    product = SimpleProductSerializer(read_only=True)

    class Meta:
        model = Variant
        fields = ['id', 'sku', 'unit_price', 'product']


class ProductAxisValueSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()

    class Meta:
        model = AxisValue
        fields = ['id', 'name', 'code', 'images']

    def get_images(self, axis_value):
        return ProductImageSerializer(axis_value.images.all(), many=True).data


class ProductAxisSerializer(serializers.ModelSerializer):
    """Domains — Catalog class diagram: Product 1-->0..* ProductAxis
    1-->0..* AxisValue (e.g. a 'Size' axis with 'Small'/'Medium' values)."""
    values = ProductAxisValueSerializer(many=True, required=False)

    class Meta:
        model = ProductAxis
        fields = ['id', 'name', 'sort_order', 'values']


class ProductSerializer(serializers.ModelSerializer):
    """Read/plain-update shape. Creation goes through
    CreateProductSerializer instead (see ProductAdminViewSet.create) — this
    serializer's own `create()` is unused in practice but left working for
    any direct/test use."""
    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'slug', 'collection', 'price',
                  'status', 'is_available', 'in_stock', 'images',
                  'variants', 'axes']

    is_available = serializers.BooleanField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    images = serializers.SerializerMethodField()
    # Variants are display-only here — creation/update goes through the
    # products/{id}/variants/ sub-resource only (product+axes must exist
    # first), never through this payload.
    variants = VariantSerializer(many=True, read_only=True)
    axes = ProductAxisSerializer(many=True, required=False)
    # Auto-generated from title (like admin's prepopulated_fields) — never
    # accepted from the client.
    slug = serializers.SlugField(read_only=True)

    def get_images(self, product):
        gallery = [img for img in product.images.all() if img.role == 'PRODUCT_GALLERY']
        return ProductImageSerializer(gallery, many=True).data

    def create(self, validated_data):
        axes_data = validated_data.pop('axes', [])
        validated_data['slug'] = unique_slug_from(validated_data['title'])
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
            validated_data['slug'] = unique_slug_from(new_title, instance=instance)
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

    def validate_images(self, images):
        for image_file in images:
            data = image_file.read()
            image_file.seek(0)
            try:
                validate_image_bytes(data)
            except InvalidImageError as e:
                raise serializers.ValidationError(str(e))
        return images

    def create(self, validated_data):
        with transaction.atomic():
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
            # rows in one bulk statement with the resulting keys/dimensions.
            upload_results = [
                upload_image(image, product_id=product.id)
                for image in images
            ]
            ProductImage.objects.bulk_create([
                ProductImage(product=product, image_key=result.key,
                             width=result.width, height=result.height,
                             sort_order=i)
                for i, result in enumerate(upload_results)
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
