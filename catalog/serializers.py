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
    AxisValue, Product, ProductAxis, ProductImage, ProductStatus, Collection,
    Review, Variant, VariantAxisValue, Vocabulary, VocabularyValue,
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
    variant = serializers.PrimaryKeyRelatedField(
        queryset=Variant.objects.all(), required=False, allow_null=True,
        write_only=True)
    position = serializers.IntegerField(source='sort_order', required=False)
    object_key = serializers.CharField(source='image_key', read_only=True)
    aspect_ratio = serializers.ReadOnlyField()
    role = serializers.ReadOnlyField()
    product_id = serializers.IntegerField(read_only=True)
    variant_id = serializers.IntegerField(read_only=True)
    src = serializers.SerializerMethodField()
    srcset = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'position', 'object_key',
                  'aspect_ratio', 'role', 'product_id', 'variant_id',
                  'src', 'srcset', 'variant']

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

    def validate_variant(self, variant):
        # An override photo must actually belong to a variant of this same
        # product.
        product_id = self.context['product_id']
        if not variant.product_id == int(product_id):
            raise serializers.ValidationError(
                'This variant does not belong to this product.')
        return variant

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
    {'axis': 'Size', 'value': '30', 'code': 'W30', 'label': 'W30'} — so a
    client can build a 'Size: W30 / Colour: Olive' selector without a second
    round-trip to /products/{slug}/ to cross-reference axis names.

    `label` is the only field a UI may render. `value` and `code` mean
    different things per vocabulary ('30' is a bare number, 'OLV' is an SKU
    token), so interpolating either into user-facing copy is a bug — that's
    what `label` exists to prevent.

    Sourced from the denormalized AxisValue.label, NOT through
    vocabulary_value: the join would add a query per variant on every list
    page. See test_axis_value_labels.py's query-count test.
    """
    axis = serializers.CharField(source='axis_value.axis.name', read_only=True)
    value = serializers.CharField(source='axis_value.name', read_only=True)
    code = serializers.CharField(source='axis_value.code', read_only=True)
    label = serializers.CharField(source='axis_value.label', read_only=True)

    class Meta:
        model = VariantAxisValue
        fields = ['axis', 'value', 'code', 'label']


class VariantSerializer(serializers.ModelSerializer):
    """Domains — Catalog class diagram: Product 1-->0..* Variant. Writable
    so a product's variants can be created/replaced through the product
    endpoint (US-20/US-21) — there's no separate variant-management story yet."""
    price_with_tax = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    # Real sellable stock (inventory - allocated; None when inventory isn't
    # tracked) — raw `inventory` alone reads wrong once stock is allocated
    # to pending orders (allocated bumps at checkout, before payment).
    available = serializers.IntegerField(read_only=True, allow_null=True)
    axis_values = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    # Write side: exactly one AxisValue id per axis defined on the parent
    # product. Named distinctly from the read-only `axis_values` above so
    # input/output don't collide on shape (ids in, expanded objects out).
    axis_value_ids = serializers.PrimaryKeyRelatedField(
        queryset=AxisValue.objects.select_related(
            'axis__vocabulary', 'vocabulary_value'),
        many=True, required=False, write_only=True,
        help_text="One AxisValue id per axis defined on this variant's product.")

    class Meta:
        model = Variant
        fields = ['id', 'sku', 'unit_price', 'price_with_tax',
                  'compare_at_price', 'weight', 'track_inventory',
                  'inventory', 'available', 'in_stock', 'axis_values',
                  'images', 'axis_value_ids']

    def get_price_with_tax(self, variant: Variant):
        # Money math first (currency-aware, exact), .amount only at the
        # output boundary — matches the pattern used everywhere else
        # (cart/order/report totals). `Decimal(1.1)` from a float literal
        # would carry float-precision error; `Decimal('1.1')` is exact.
        return (variant.unit_price * Decimal('1.1')).amount

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
            # Can only fire on corrupted data, but it is the assertion that
            # keeps the denormalized name/code/label honest — a value whose
            # registry entry drifted away from its axis's vocabulary would
            # otherwise serve display copy from the wrong taxonomy.
            if axis_value.vocabulary_value.vocabulary_id != axis_value.axis.vocabulary_id:
                raise serializers.ValidationError(
                    {'axis_value_ids':
                        f"'{axis_value.name}' does not belong to its axis's vocabulary."})

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
    """The axis picker's options on product detail. Carries `label` for the
    same reason VariantAxisValueSerializer does — this surface renders
    before any variant is selected, so without it the storefront still needs
    a conditional render path."""
    class Meta:
        model = AxisValue
        fields = ['id', 'name', 'code', 'label']


class ProductAxisSerializer(serializers.ModelSerializer):
    """Domains — Catalog class diagram: Product 1-->0..* ProductAxis
    1-->0..* AxisValue (e.g. a 'Size' axis with 'S'/'M' values)."""
    values = ProductAxisValueSerializer(many=True, required=False)
    # The key string, not the id — keeps the response self-describing and
    # lets an admin UI pre-select the right registry when editing.
    vocabulary = serializers.SlugRelatedField(slug_field='key', read_only=True)

    class Meta:
        model = ProductAxis
        fields = ['id', 'name', 'sort_order', 'vocabulary', 'values']


class VocabularyValueSerializer(serializers.ModelSerializer):
    """A single resolvable entry in a vocabulary — what the admin axis-value
    selector reads, and the only sanctioned source of an AxisValue's
    name/code/label."""

    class Meta:
        model = VocabularyValue
        fields = ['id', 'value', 'code', 'label', 'sort_order', 'is_active']

    def validate_value(self, value):
        # `value` is this row's identity in the URL
        # (/vocabularies/{key}/values/{value}/), so a path separator would
        # make the row unroutable. Rejecting at the write boundary keeps the
        # detail route total for every row that can ever exist.
        illegal = [c for c in '/?#' if c in value]
        if illegal:
            raise serializers.ValidationError(
                "Value may not contain '/', '?' or '#' — it is used as a URL "
                "path segment.")
        return value

    def validate(self, attrs):
        vocabulary = self.context.get('vocabulary')
        if vocabulary is None:
            return attrs

        # `vocabulary` comes from the URL, not the payload, so DRF cannot
        # auto-generate the UniqueTogetherValidator for it.
        value = attrs.get('value')
        if value is not None:
            clash = VocabularyValue.objects.filter(
                vocabulary=vocabulary, value=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {'value': f"'{value}' is already a value of vocabulary "
                              f"'{vocabulary.key}'."})

        code = attrs.get('code')
        if code:
            clash = VocabularyValue.objects.filter(
                vocabulary=vocabulary, code=code)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            owner = clash.first()
            if owner is not None:
                raise serializers.ValidationError(
                    {'code': f"Code '{code}' is already used by "
                             f"'{owner.value}' in vocabulary "
                             f"'{vocabulary.key}'."})
        return attrs


class VocabularyValueUpdateSerializer(VocabularyValueSerializer):
    """PATCH shape. `value` is immutable: it is the row's URL identity and
    the source of every denormalized AxisValue.name, so editing it would
    strand the URL and drift the copies. Only code/label/sort_order/is_active
    are editable — which is exactly the 'edit an entry's code or label'
    operation."""

    class Meta(VocabularyValueSerializer.Meta):
        read_only_fields = ['value']


class VocabularyValueCreateSerializer(VocabularyValueSerializer):
    """Create shape, with the escape hatch for adding a value to a
    vocabulary that existing products must immediately be able to use.

    Without `axis_ids` there is no way to get a new value onto an
    already-created product: ProductSerializer discards `axes`, and
    VariantSerializer only accepts ids of AxisValue rows that already exist.
    """
    axis_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProductAxis.objects.select_related('vocabulary'),
        many=True, required=False, write_only=True,
        help_text='Optional: also create an AxisValue for this new value on '
                  'each listed axis, in the same transaction.')

    class Meta(VocabularyValueSerializer.Meta):
        fields = VocabularyValueSerializer.Meta.fields + ['axis_ids']

    def validate_axis_ids(self, axes):
        vocabulary = self.context['vocabulary']
        mismatched = [
            f"Axis {axis.id} draws from "
            f"'{axis.vocabulary.key if axis.vocabulary else None}', not "
            f"'{vocabulary.key}'."
            for axis in axes if axis.vocabulary_id != vocabulary.id
        ]
        if mismatched:
            raise serializers.ValidationError(mismatched)
        return axes

    def create(self, validated_data):
        axes = validated_data.pop('axis_ids', [])
        with transaction.atomic():
            vocabulary_value = VocabularyValue.objects.create(**validated_data)
            AxisValue.objects.bulk_create([
                AxisValue(axis=axis, vocabulary_value=vocabulary_value,
                          name=vocabulary_value.value,
                          code=vocabulary_value.code,
                          label=vocabulary_value.label)
                for axis in axes
            ])
        return vocabulary_value


class VocabularySerializer(serializers.ModelSerializer):
    values = VocabularyValueSerializer(many=True, required=False)

    class Meta:
        model = Vocabulary
        fields = ['id', 'key', 'label', 'description', 'values']

    def validate_values(self, values):
        errors = [{} for _ in values]
        seen_values, seen_codes = {}, {}
        for i, entry in enumerate(values):
            value = entry.get('value')
            if value in seen_values:
                errors[i]['value'] = f"'{value}' is repeated in this payload."
            else:
                seen_values[value] = i

            code = entry.get('code')
            if code:
                if code in seen_codes:
                    errors[i]['code'] = (
                        f"Code '{code}' is repeated in this payload.")
                else:
                    seen_codes[code] = i
        if any(errors):
            raise serializers.ValidationError(errors)
        return values

    def create(self, validated_data):
        values = validated_data.pop('values', [])
        with transaction.atomic():
            vocabulary = Vocabulary.objects.create(**validated_data)
            VocabularyValue.objects.bulk_create([
                VocabularyValue(vocabulary=vocabulary, **entry)
                for entry in values
            ])
        return vocabulary


class ProductImageListSerializer(serializers.ModelSerializer):
    """Slim image shape for ProductListSerializer — the list table only
    ever renders the first gallery image, and only its src/alt_text."""
    src = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['src', 'alt_text']

    def get_src(self, obj):
        return build_url(obj.image_key, width=DEFAULT_SRC_WIDTH)


class VariantListSerializer(serializers.ModelSerializer):
    """Slim variant shape for ProductListSerializer — just what the list
    table's price column needs (low-stock calc uses total_stock instead)."""
    class Meta:
        model = Variant
        fields = ['unit_price', 'track_inventory']


class ProductListSerializer(serializers.ModelSerializer):
    """Trimmed shape for the products list table (admin dashboard) — drops
    everything list.tsx doesn't render (description, slug, top-level price,
    is_available/in_stock, axes, and most variant/image fields) so the list
    response doesn't ship the full detail payload for every row."""
    class Meta:
        model = Product
        fields = ['id', 'title', 'collection', 'status', 'total_stock',
                  'images', 'variants']

    total_stock = serializers.IntegerField(read_only=True)
    images = serializers.SerializerMethodField()
    variants = VariantListSerializer(many=True, read_only=True)

    def get_images(self, product):
        gallery = [img for img in product.images.all() if img.role == 'PRODUCT_GALLERY']
        return ProductImageListSerializer(gallery, many=True).data


class ProductSerializer(serializers.ModelSerializer):
    """Read/plain-update shape. Creation goes through
    CreateProductSerializer instead (see ProductAdminViewSet.create) — this
    serializer's own `create()` is unused in practice but left working for
    any direct/test use."""
    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'slug', 'collection', 'price',
                  'status', 'is_available', 'in_stock', 'total_stock',
                  'images', 'variants', 'axes']

    is_available = serializers.BooleanField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    total_stock = serializers.IntegerField(read_only=True)
    images = serializers.SerializerMethodField()
    # Variants are display-only here — creation/update goes through the
    # products/{id}/variants/ sub-resource only (product+axes must exist
    # first), never through this payload.
    variants = VariantSerializer(many=True, read_only=True)
    # Read-only for the same reason `variants` above is: axes must exist
    # before variants can reference them, and axis values may only be
    # authored against the vocabulary registry. Product creation
    # (CreateProductSerializer) is the single authoring path — a second,
    # registry-unaware one here would be a documented bypass around every
    # validation rule the registry exists to enforce.
    axes = ProductAxisSerializer(many=True, read_only=True)
    # Auto-generated from title (like admin's prepopulated_fields) — never
    # accepted from the client.
    slug = serializers.SlugField(read_only=True)

    def get_images(self, product):
        gallery = [img for img in product.images.all() if img.role == 'PRODUCT_GALLERY']
        return ProductImageSerializer(gallery, many=True).data

    def validate(self, attrs):
        if attrs.get('status') == ProductStatus.PUBLISHED:
            instance = self.instance
            own_images = (
                ProductImage.objects.filter(product=instance, variant__isnull=True).count()
                if instance else 0)
            if own_images == 0:
                raise serializers.ValidationError(
                    {'status': 'Product needs at least one image before it can be published.'})
            if instance:
                missing = [
                    v.sku for v in instance.variants.all()
                    if not ProductImage.objects.filter(variant=v).exists()]
                if missing:
                    raise serializers.ValidationError(
                        {'status': 'These variants need at least one image before '
                                   f'publishing: {", ".join(missing)}.'})
        return attrs

    def create(self, validated_data):
        validated_data['slug'] = unique_slug_from(validated_data['title'])
        return Product.objects.create(**validated_data)

    def update(self, instance, validated_data):
        # Axes and variants are both read_only here, so neither reaches
        # validated_data — a plain product update (US-21) is a Catalog-field
        # edit, not an axis-management story.
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

    def _validate_axis_vocabulary(self, axis, i, axes, seen_vocabularies, errors):
        """Resolve `axes[i].vocabulary` to a Vocabulary, or record an error.

        Declaring the vocabulary on the axis rather than per value is what
        makes "no mixed vocabulary within a product" structural: every value
        under an axis draws from one registry by construction. The residual
        reachable failure is a product carrying two axes backed by two size
        vocabularies, which is what `seen_vocabularies` catches here (and
        the unique_product_axis_vocabulary constraint catches in the DB).
        """
        key = (axis.get('vocabulary') or '').strip()
        if not key:
            errors[f'axes[{i}].vocabulary'] = 'This field may not be blank.'
            return None

        vocabulary = Vocabulary.objects.filter(key=key).first()
        if vocabulary is None:
            errors[f'axes[{i}].vocabulary'] = f"No vocabulary with key '{key}'."
            return None

        if key in seen_vocabularies:
            first = axes[seen_vocabularies[key]].get('name', '?')
            errors[f'axes[{i}].vocabulary'] = (
                f"Vocabulary '{key}' is already used by axis '{first}' on "
                f"this product. An axis may not repeat a vocabulary.")
            return None

        seen_vocabularies[key] = i
        axis['_vocabulary_id'] = vocabulary.id
        return vocabulary

    def _validate_allowed_values(self, values, i, vocabulary, errors):
        """Resolve each allowed value against the registry.

        Freehand labels are rejected outright: a value either already exists
        in the vocabulary (in which case its code/label come from there, and
        contradicting them is an error, not an override) or it is explicitly
        being added to the vocabulary via `newValue`. There is no third path
        that writes an AxisValue with client-supplied display copy.
        """
        existing = {
            vv.value: vv for vv in vocabulary.values.filter(is_active=True)}
        taken_codes = {vv.code: vv.value for vv in existing.values() if vv.code}
        new_codes = {}

        for j, value in enumerate(values):
            field = f'axes[{i}].allowedValues[{j}]'
            name = (value.get('name') or '').strip()
            if not name:
                errors[f'{field}.name'] = 'This field may not be blank.'
                continue

            vv = existing.get(name)
            if vv is not None:
                self._reject_registry_overrides(value, vv, field, vocabulary, errors)
                value['_vocabulary_value_id'] = vv.id
                continue

            if not value.get('newValue'):
                errors[f'{field}.name'] = (
                    f"'{name}' is not a value of vocabulary "
                    f"'{vocabulary.key}'. To add it, set \"newValue\": true "
                    f"and supply a \"label\".")
                continue

            label = (value.get('label') or '').strip()
            if not label:
                errors[f'{field}.label'] = (
                    'This field is required when newValue is true.')
                continue

            code = (value.get('code') or '').strip()
            if code and (code in taken_codes or code in new_codes):
                owner = taken_codes.get(code) or new_codes.get(code)
                errors[f'{field}.code'] = (
                    f"Code '{code}' is already used by '{owner}' in "
                    f"vocabulary '{vocabulary.key}'.")
                continue
            if code:
                new_codes[code] = name

            value['_new'] = {'value': name, 'code': code, 'label': label,
                             'sort_order': value.get('sortOrder', 0)}

    def _reject_registry_overrides(self, value, vv, field, vocabulary, errors):
        """A payload may echo a registry entry's code/label, but may not
        contradict it — relabelling is global and goes through PATCH."""
        label = (value.get('label') or '').strip()
        if label and label != vv.label:
            errors[f'{field}.label'] = (
                f"'{vv.value}' is already labelled '{vv.label}' in "
                f"vocabulary '{vocabulary.key}'. Relabelling is global — use "
                f"PATCH /store-admin/vocabularies/{vocabulary.key}/values/"
                f"{vv.value}/.")
        code = (value.get('code') or '').strip()
        if code and code != vv.code:
            errors[f'{field}.code'] = (
                f"'{vv.value}' already has code '{vv.code}' in vocabulary "
                f"'{vocabulary.key}'. Changing it is global — use PATCH "
                f"/store-admin/vocabularies/{vocabulary.key}/values/"
                f"{vv.value}/.")

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
            seen_vocabularies = {}
            for i, axis in enumerate(axes):
                if not (axis.get('name') or '').strip():
                    errors[f'axes[{i}].name'] = 'This field may not be blank.'
                if axis.get('sortOrder', 0) < 0:
                    errors[f'axes[{i}].sortOrder'] = 'Must be >= 0.'

                vocabulary = self._validate_axis_vocabulary(
                    axis, i, axes, seen_vocabularies, errors)

                values = axis.get('allowedValues') or []
                if not values:
                    errors[f'axes[{i}].allowedValues'] = 'At least one allowed value is required.'
                elif vocabulary is not None:
                    self._validate_allowed_values(
                        values, i, vocabulary, errors)

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

    def _resolve_vocabulary_value(self, value, vocabulary_id):
        """Return the VocabularyValue this allowed value refers to, creating
        it first if the payload is adding it to the vocabulary.

        The registry write happens inside create()'s existing
        transaction.atomic(), which is what makes "add a new value and use
        it in one atomic step" true for free: if anything later in create()
        raises — an image upload, say — the new vocabulary entry rolls back
        with the product rather than orphaning itself in the registry.
        """
        spec = value.get('_new')
        if spec is None:
            return VocabularyValue.objects.get(pk=value['_vocabulary_value_id'])
        return VocabularyValue.objects.create(
            vocabulary_id=vocabulary_id, value=spec['value'],
            code=spec['code'], label=spec['label'],
            sort_order=spec['sort_order'])

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
                    sort_order=axis.get('sortOrder', 0),
                    vocabulary_id=axis['_vocabulary_id'])
                for value in axis['allowedValues']:
                    vv = self._resolve_vocabulary_value(
                        value, axis['_vocabulary_id'])
                    # name/code/label are copied FROM the registry, never
                    # from the request — even a well-formed payload cannot
                    # inject display copy that diverges from the vocabulary.
                    AxisValue.objects.create(
                        axis=axis_obj, vocabulary_value=vv,
                        name=vv.value, code=vv.code, label=vv.label)

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
