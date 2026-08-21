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
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=9,
        choices=ProductStatus.choices,
        default=ProductStatus.PUBLISHED)
    last_update = models.DateTimeField(auto_now=True)
    collection = models.ForeignKey(
        Collection, on_delete=models.PROTECT, related_name='products')
    promotions = models.ManyToManyField(Promotion, blank=True)

    @property
    def is_available(self):
        return self.status == ProductStatus.PUBLISHED

    @property
    def in_stock(self):
        return self.variants.filter(
            models.Q(track_inventory=False) | models.Q(inventory__gt=0)
        ).exists()

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
        default_currency='USD',
        validators=[MinMoneyValidator(1)])
    compare_at_price = MoneyField(
        max_digits=6, decimal_places=2, default_currency='USD',
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


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products')
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Set only on an "image-bearing axis" (typically Color) — this photo
    # belongs to that specific swatch and is swapped in when the shopper
    # picks it. Null = an ordinary, axis-independent product photo.
    axis_value = models.ForeignKey(
        AxisValue, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')

    class Meta:
        ordering = ['sort_order', 'id']


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
