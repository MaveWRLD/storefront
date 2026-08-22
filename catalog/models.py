import math
from decimal import Decimal
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from djmoney.models.fields import MoneyField
from djmoney.models.validators import MinMoneyValidator


class Promotion(models.Model):
    description = models.CharField(max_length=255)
    discount = models.FloatField()


class Collection(models.Model):
    title = models.CharField(max_length=255)
    featured_product = models.ForeignKey(
        'Product', on_delete=models.SET_NULL, null=True, related_name='+', blank=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['title']


class ProductStatus(models.TextChoices):
    """Business Rule (Catalog): 'Availability controlled via ProductStatus,
    not a purchaseable flag'. Only PUBLISHED products are purchasable/available;
    DRAFT and ARCHIVED still show in listings but are marked unavailable."""
    DRAFT = 'draft', 'Draft'
    PUBLISHED = 'published', 'Published'
    ARCHIVED = 'archived', 'Archived'


class Product(models.Model):
    """Domains — Catalog class diagram: Product now only carries identity
    fields. Price and stock moved to Variant (a product can have more than
    one), matching the diagram's Product 1-->0..* Variant edge."""
    title = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=9,
        choices=ProductStatus.choices,
        default=ProductStatus.PUBLISHED)
    # Base/display price — informational (e.g. listing pages before a
    # variant is picked). The real sellable price is always Variant.unit_price;
    # a variant can differ from this (sale price, size upcharge, etc).
    # Nullable: older rows predate this field, and it's optional on the
    # plain admin update path — only the create-with-axes-and-images flow
    # (CreateProductSerializer) requires it.
    price = MoneyField(
        max_digits=10, decimal_places=2, default_currency='GHS',
        null=True, blank=True, validators=[MinMoneyValidator(Decimal('0.01'))])
    last_update = models.DateTimeField(auto_now=True)
    # Nullable: the create-with-axes-and-images flow (CreateProductSerializer)
    # doesn't collect a collection at creation time — assign one after, if needed.
    collection = models.ForeignKey(
        Collection, on_delete=models.PROTECT, related_name='products',
        null=True, blank=True)
    promotions = models.ManyToManyField(Promotion, blank=True)

    @property
    def is_available(self):
        return self.status == ProductStatus.PUBLISHED

    @property
    def in_stock(self):
        """Must agree with Variant.in_stock/available (inventory -
        allocated), not raw inventory — a variant with stock fully
        allocated to pending orders has nothing left to sell."""
        return any(variant.in_stock for variant in self.variants.all())

    @property
    def total_stock(self):
        """Sum of every variant's raw `inventory` — a stock count, not a
        sellable count, so unlike `in_stock`/Variant.available this doesn't
        subtract `allocated`."""
        return sum(variant.inventory for variant in self.variants.all())

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['title']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['collection', 'status']),
            models.Index(fields=['-last_update']),
        ]


class Variant(models.Model):
    """Domains — Catalog class diagram: sku/price/compareAtPrice/weight/
    trackInventory. `inventory` isn't on the diagram's Variant — it's a
    stand-in for the still-unbuilt Warehouse.Stock, same simplification
    already applied to the old Product.inventory field (see the Warehouse
    Business Rule 'Stock re-validated at checkout, not just add-to-cart')."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='variants')
    sku = models.CharField(max_length=64, unique=True)
    unit_price = MoneyField(
        max_digits=6,
        decimal_places=2,
        default_currency='GHS',
        validators=[MinMoneyValidator(1)])
    compare_at_price = MoneyField(
        max_digits=6, decimal_places=2, default_currency='GHS',
        null=True, blank=True)
    weight = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True)
    track_inventory = models.BooleanField(default=True)
    inventory = models.IntegerField(
        default=0, validators=[MinValueValidator(0)])
    allocated = models.IntegerField(
        default=0, validators=[MinValueValidator(0)])

    @property
    def available(self):
        """Business Rule (Warehouse): 'Stock decrements only on payment
        success, not at checkout' (US-32). Checkout allocates instead of
        decrementing `inventory`, so everywhere that needs to know
        available-to-sell stock must read `inventory - allocated`, not raw
        `inventory`. `None` (unlimited) when inventory isn't tracked."""
        if not self.track_inventory:
            return None
        return self.inventory - self.allocated

    @property
    def in_stock(self):
        return not self.track_inventory or self.available > 0

    def __str__(self) -> str:
        return self.sku

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(
                fields=['track_inventory', 'inventory', 'allocated'],
                condition=models.Q(track_inventory=True),
                name='variant_in_stock_idx',
            ),
        ]


class ProductAxis(models.Model):
    """Domains — Catalog class diagram: e.g. 'Size' or 'Color'."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='axes')
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ['sort_order', 'id']


class AxisValue(models.Model):
    """Domains — Catalog class diagram: e.g. 'Small'/'S' under the 'Size' axis."""
    axis = models.ForeignKey(
        ProductAxis, on_delete=models.CASCADE, related_name='values')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, default='')

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ['id']


class VariantAxisValue(models.Model):
    """Domains — Catalog class diagram: Variant 1-->0..* VariantAxisValue,
    one row per (variant, axis) pair recording which value that variant
    selected on that axis (e.g. this variant is 'Red' on the 'Color' axis,
    'M' on the 'Size' axis). Closes the previously-missing Variant<->AxisValue
    link — before this, a Variant carried no record of which size/color it was.

    The table only guarantees a variant can't repeat the exact same axis
    value row twice (unique_together below). It does NOT enforce "exactly
    one value per axis" or "no two variants share the same combination" —
    those are business rules enforced in code (VariantSerializer), same as
    the reference diagram notes ("enforced in code, not schema")."""
    variant = models.ForeignKey(
        Variant, on_delete=models.CASCADE, related_name='axis_values')
    axis_value = models.ForeignKey(
        AxisValue, on_delete=models.CASCADE, related_name='variant_links')

    def __str__(self) -> str:
        return f'{self.variant.sku}: {self.axis_value}'

    class Meta:
        ordering = ['axis_value__axis__sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['variant', 'axis_value'],
                name='unique_variant_axis_value'),
        ]


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images')
    image_key = models.CharField(max_length=512)
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Pixel dimensions captured at upload time (see media_storage.upload_image) —
    # null for rows created before this field existed; drives aspect_ratio.
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    # Plain flag, no uniqueness constraint — multiple images per product may
    # be marked hero. Not exposed in any serializer output yet.
    is_hero = models.BooleanField(default=False)
    # Set only on an "image-bearing axis" (typically Color) — this photo
    # belongs to that specific swatch and is swapped in when the shopper
    # picks it. Null = an ordinary, axis-independent product photo.
    axis_value = models.ForeignKey(
        AxisValue, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')
    # Set to override the product/swatch gallery for one specific variant
    # (e.g. this exact SKU photographed on a model). Mutually exclusive
    # with axis_value — enforced both here (DB) and in
    # ProductImageSerializer.validate (early, friendlier error).
    variant = models.ForeignKey(
        Variant, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')

    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(axis_value__isnull=True) | models.Q(variant__isnull=True),
                name='productimage_axis_value_or_variant_not_both'),
        ]

    @property
    def role(self) -> str:
        if self.variant_id:
            return 'VARIANT_OVERRIDE'
        if self.axis_value_id:
            return 'AXIS_VALUE_GALLERY'
        return 'PRODUCT_GALLERY'

    @property
    def aspect_ratio(self) -> str | None:
        if not self.width or not self.height:
            return None
        divisor = math.gcd(self.width, self.height)
        return f'{self.width // divisor}:{self.height // divisor}'


class Review(models.Model):
    """US-19: a review requires a verified purchase, so it's tied to a
    Customer (not the old free-text 'name') — Business Rule: 'A customer
    should not be able to review a product they have not purchased.' No
    Saleor equivalent (Reviews & Ratings isn't a core Saleor domain)."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)])
    description = models.TextField()
    date = models.DateField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', '-date']),
        ]
