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


class Vocabulary(models.Model):
    """Global, backend-owned taxonomy an axis draws its values from — e.g.
    'size_letter', 'size_waist_in', 'colour'. Unlike ProductAxis/AxisValue
    (which are per-product, so 'Size' exists once per product), there is
    exactly one row per taxonomy for the whole catalog. Structural
    precedent: Collection.

    This is what stops display copy being freehand-typed per product: an
    AxisValue may only ever copy its name/code/label from a registry entry.
    """
    key = models.SlugField(max_length=64, unique=True)
    # Human name for the admin selector, e.g. 'Letter size'.
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')

    def __str__(self) -> str:
        return self.key

    class Meta:
        ordering = ['key']
        verbose_name_plural = 'vocabularies'


class VocabularyValue(models.Model):
    """One resolvable value in a Vocabulary.

    The three text columns do three different jobs and are NOT derivable
    from each other — which is the whole reason `label` has to exist:

        vocabulary     value    code    label
        size_waist_in  '30'     'W30'   'W30'   <- label == code, != value
        size_letter    'S'      'S'     'S'     <- all three coincide
        colour         'Olive'  'OLV'   'Olive' <- label == value, != code

    `value` is the matching/filter key, `code` is the SKU token, `label` is
    the only field a UI may render. No derivation rule produces all three
    rows above, so `label` is authored per entry.
    """
    vocabulary = models.ForeignKey(
        Vocabulary, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, default='')
    label = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    # Soft-retire a discontinued value without breaking the historical
    # AxisValue rows that still point at it (those FKs are PROTECTed).
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f'{self.vocabulary.key}: {self.label}'

    class Meta:
        ordering = ['vocabulary__key', 'sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['vocabulary', 'value'],
                name='unique_vocabulary_value'),
            # Partial: a blank code stays legal (matches AxisValue.code's
            # existing default) but real SKU tokens can't collide.
            models.UniqueConstraint(
                fields=['vocabulary', 'code'],
                name='unique_vocabulary_code',
                condition=~models.Q(code='')),
            models.CheckConstraint(
                condition=~models.Q(label=''),
                name='vocabulary_value_label_not_blank'),
        ]


class ProductAxis(models.Model):
    """Domains — Catalog class diagram: e.g. 'Size' or 'Color'."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='axes')
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    # Which registry taxonomy this axis draws from. PROTECT because a
    # vocabulary in use by live product data must not be deletable — which
    # is also what makes VocabularyValue.vocabulary safe to CASCADE.
    # Migrations 0004/0006 add this nullable and backfill it; 0007 makes it
    # required. Every axis draws from the registry.
    vocabulary = models.ForeignKey(
        Vocabulary, on_delete=models.PROTECT, related_name='axes')

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [
            # A product may not draw two axes from the same vocabulary (a
            # 'Size' axis on size_letter plus a 'Waist' axis on
            # size_waist_in). Postgres treats NULLs as distinct, so this is
            # inert until 0008 makes the column NOT NULL.
            models.UniqueConstraint(
                fields=['product', 'vocabulary'],
                name='unique_product_axis_vocabulary'),
        ]


class AxisValue(models.Model):
    """Domains — Catalog class diagram: e.g. 'Small'/'S' under the 'Size' axis.

    name/code/label are denormalized copies of the referenced
    VocabularyValue's value/code/label. They are written ONLY from the
    registry, never from client input, so the storefront read path can
    serve `label` without joining through to Vocabulary on every variant.
    VocabularyValueAdminViewSet.perform_update is the one place that fans a
    registry edit back out to these copies.
    """
    axis = models.ForeignKey(
        ProductAxis, on_delete=models.CASCADE, related_name='values')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, default='')
    # The only field a UI may render. Added non-null with a blank default
    # (metadata-only ADD COLUMN on Postgres); the blank-rejecting check
    # constraint arrives in 0007, after the backfill has populated it.
    label = models.CharField(max_length=100, default='')
    vocabulary_value = models.ForeignKey(
        VocabularyValue, on_delete=models.PROTECT, related_name='axis_values')

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['axis', 'vocabulary_value'],
                name='unique_axis_vocabulary_value'),
            models.CheckConstraint(
                condition=~models.Q(label=''),
                name='axis_value_label_not_blank'),
        ]


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
    # Set to override the product gallery for one specific variant (e.g.
    # this exact SKU photographed on a model). Null = an ordinary,
    # variant-independent product photo.
    variant = models.ForeignKey(
        Variant, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')

    class Meta:
        ordering = ['sort_order', 'id']

    @property
    def role(self) -> str:
        if self.variant_id:
            return 'VARIANT_OVERRIDE'
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
