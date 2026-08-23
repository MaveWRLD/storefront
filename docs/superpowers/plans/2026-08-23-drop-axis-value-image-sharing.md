# Drop axis-value image sharing; add publish-gate image rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `AXIS_VALUE_GALLERY` image-sharing tier from `ProductImage` (only `PRODUCT_GALLERY` / `VARIANT_OVERRIDE` remain), and add a code-enforced rule that a product can't move to `PUBLISHED` status unless it and every one of its variants has at least one own image.

**Architecture:** `ProductImage.axis_value` FK is dropped from the model (migration), removed from `ProductImageSerializer` and `ProductAxisValueSerializer`, and its dedicated test file deleted. A new `validate()` check is added to `ProductSerializer` that runs whenever a write includes `status: PUBLISHED`, querying the product's own-gallery image count and each variant's own image count directly (no new fields).

**Tech Stack:** Django, Django REST Framework, pytest + pytest-django, PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-08-23-drop-axis-value-image-sharing-design.md`

## Global Constraints

- Keep existing `Product`/`Variant`/`ProductImage` names and URLs — no rename to Parent/Child, no `/catalog-items/` endpoint.
- No new `buyable` field — publish-gate check uses the existing `Product.status` field only.
- Enforcement is code-level (serializer `validate`), not a DB constraint.
- Run tests with `pipenv run pytest <path> -q`. The Postgres container must be up: `docker compose up -d db` (service name may show as `storefront_postgres`; if `docker compose up -d db` errors because the service key differs, run `docker compose up -d` instead).

---

### Task 1: Remove `ProductImage.axis_value` from the model

**Files:**
- Modify: `catalog/models.py:204-245` (`ProductImage` class)
- Modify: `catalog/views.py:38-39` and `catalog/views.py:81-82` (`ProductViewSet` and `ProductAdminViewSet` querysets)
- Create: new migration under `catalog/migrations/` (via `makemigrations`)
- Modify: `catalog/tests/test_product_image_model.py`
- Delete: `catalog/tests/test_axis_value_images.py`

**Interfaces:**
- Produces: `ProductImage.role` now returns only `'VARIANT_OVERRIDE'` or `'PRODUCT_GALLERY'` (never `'AXIS_VALUE_GALLERY'`). `ProductImage` no longer has an `axis_value` / `axis_value_id` attribute. `AxisValue` no longer has an `images` reverse relation.

- [ ] **Step 1: Confirm baseline — run the tests this task will change**

Run: `pipenv run pytest catalog/tests/test_product_image_model.py catalog/tests/test_axis_value_images.py -q`
Expected: all currently pass (baseline before removal).

- [ ] **Step 2: Remove the field, constraint, and role branch from the model**

In `catalog/models.py`, inside `class ProductImage(models.Model):`, delete this block entirely:

```python
    # Set only on an "image-bearing axis" (typically Color) — this photo
    # belongs to that specific swatch and is swapped in when the shopper
    # picks it. Null = an ordinary, axis-independent product photo.
    axis_value = models.ForeignKey(
        AxisValue, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')
```

Replace the comment above the `variant` field (which currently references the now-removed mutual-exclusion rule) — change:

```python
    # Set to override the product/swatch gallery for one specific variant
    # (e.g. this exact SKU photographed on a model). Mutually exclusive
    # with axis_value — enforced both here (DB) and in
    # ProductImageSerializer.validate (early, friendlier error).
    variant = models.ForeignKey(
        Variant, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')
```

to:

```python
    # Set to override the product gallery for one specific variant (e.g.
    # this exact SKU photographed on a model). Null = an ordinary,
    # variant-independent product photo.
    variant = models.ForeignKey(
        Variant, on_delete=models.CASCADE, null=True, blank=True,
        related_name='images')
```

Replace the `Meta` class:

```python
    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(axis_value__isnull=True) | models.Q(variant__isnull=True),
                name='productimage_axis_value_or_variant_not_both'),
        ]
```

with:

```python
    class Meta:
        ordering = ['sort_order', 'id']
```

Replace the `role` property:

```python
    @property
    def role(self) -> str:
        if self.variant_id:
            return 'VARIANT_OVERRIDE'
        if self.axis_value_id:
            return 'AXIS_VALUE_GALLERY'
        return 'PRODUCT_GALLERY'
```

with:

```python
    @property
    def role(self) -> str:
        if self.variant_id:
            return 'VARIANT_OVERRIDE'
        return 'PRODUCT_GALLERY'
```

- [ ] **Step 3: Drop the now-dead `axes__values__images` prefetch**

`AxisValue.images` (the reverse of the FK just removed) no longer exists, so the `axes__values__images` prefetch in both product querysets would raise `FieldError`. In `catalog/views.py`, there are two identical occurrences — one in `ProductViewSet`, one in `ProductAdminViewSet`. Change both from:

```python
    queryset = Product.objects.all().distinct().prefetch_related(
        'images', 'variants__images', 'axes__values__images')
```

to:

```python
    queryset = Product.objects.all().distinct().prefetch_related(
        'images', 'variants__images')
```

- [ ] **Step 4: Generate and apply the migration**

Run: `docker compose up -d db || docker compose up -d`
Run: `pipenv run python manage.py makemigrations catalog`
Expected: a new file, e.g. `catalog/migrations/0003_remove_productimage_productimage_axis_value_or_va_and_more.py`, removing the `axis_value` field and the `productimage_axis_value_or_variant_not_both` constraint.

Run: `pipenv run python manage.py migrate`
Expected: migration applies with no errors.

- [ ] **Step 5: Delete the axis-value-images test file**

Run: `rm catalog/tests/test_axis_value_images.py`

- [ ] **Step 6: Update `test_product_image_model.py`**

In `catalog/tests/test_product_image_model.py`, remove this test from `TestProductImageRole`:

```python
    def test_role_is_axis_value_gallery_when_axis_value_set(self, product, axis_value):
        image = ProductImage.objects.create(
            product=product, image_key='k.png', axis_value=axis_value)
        assert image.role == 'AXIS_VALUE_GALLERY'
```

Remove the now-unused `axis_value` fixture:

```python
@pytest.fixture
def axis_value(product):
    axis = ProductAxis.objects.create(product=product, name='Color')
    return AxisValue.objects.create(axis=axis, name='Red', code='red')
```

Remove the `TestProductImageConstraint` class entirely (the constraint it tests no longer exists):

```python
@pytest.mark.django_db
class TestProductImageConstraint:
    def test_db_rejects_both_axis_value_and_variant_set(self, product, axis_value, variant):
        with pytest.raises(IntegrityError):
            ProductImage.objects.create(
                product=product, image_key='k.png',
                axis_value=axis_value, variant=variant)
```

Remove the now-unused imports `AxisValue, ProductAxis` and `IntegrityError` from the top of the file — the remaining imports should be:

```python
import pytest

from catalog.models import Collection, Product, ProductImage, Variant
```

- [ ] **Step 7: Run tests to verify green**

Run: `pipenv run pytest catalog/tests/test_product_image_model.py -q`
Expected: all pass (fewer tests than baseline — the two removed ones are gone, not failing).

Run: `pipenv run pytest catalog/tests/test_axis_value_images.py -q`
Expected: `no tests ran` (file no longer exists) — this confirms the delete took effect rather than erroring.

Run: `pipenv run pytest catalog/ -q`
Expected: all pass — this is the real check that removing `axes__values__images` didn't break any other product-listing test.

- [ ] **Step 8: Commit**

```bash
git add catalog/models.py catalog/views.py catalog/migrations/ catalog/tests/test_product_image_model.py
git rm catalog/tests/test_axis_value_images.py
git commit -m "feat(catalog): drop ProductImage.axis_value sharing tier

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Remove `axis_value` from serializers

**Files:**
- Modify: `catalog/serializers.py` (`ProductImageSerializer`, `ProductAxisValueSerializer`)
- Modify: `catalog/tests/test_image_response_shape.py`
- Modify: `catalog/tests/test_variant_batch_and_images.py`

**Interfaces:**
- Consumes: `ProductImage.role` from Task 1 (only `'VARIANT_OVERRIDE'` / `'PRODUCT_GALLERY'`).
- Produces: `ProductImageSerializer(...).data` no longer has `axis_value` (write) or `axis_value_id` (read) keys. `ProductAxisValueSerializer(...).data` no longer has an `images` key.

- [ ] **Step 1: Confirm baseline**

Run: `pipenv run pytest catalog/tests/test_image_response_shape.py catalog/tests/test_variant_batch_and_images.py -q`
Expected: all pass.

- [ ] **Step 2: Update `ProductImageSerializer`**

In `catalog/serializers.py`, remove the `axis_value` and `axis_value_id` field declarations:

```python
    axis_value = serializers.PrimaryKeyRelatedField(
        queryset=AxisValue.objects.all(), required=False, allow_null=True,
        write_only=True)
```

```python
    axis_value_id = serializers.IntegerField(read_only=True)
```

In `Meta.fields`, change:

```python
        fields = ['id', 'image', 'alt_text', 'position', 'object_key',
                  'aspect_ratio', 'role', 'product_id', 'variant_id',
                  'axis_value_id', 'src', 'srcset', 'axis_value', 'variant']
```

to:

```python
        fields = ['id', 'image', 'alt_text', 'position', 'object_key',
                  'aspect_ratio', 'role', 'product_id', 'variant_id',
                  'src', 'srcset', 'variant']
```

Remove the `validate_axis_value` method:

```python
    def validate_axis_value(self, axis_value):
        # An image tagged to a swatch must be a value of an axis on this
        # same product — otherwise it could claim to swap in for a color
        # that has nothing to do with the product it's a photo of.
        product_id = self.context['product_id']
        if not axis_value.axis.product_id == int(product_id):
            raise serializers.ValidationError(
                'This axis value does not belong to this product.')
        return axis_value
```

Replace the `validate` method (the both-set check has nothing left to compare against):

```python
    def validate(self, attrs):
        if attrs.get('axis_value') and attrs.get('variant'):
            raise serializers.ValidationError(
                'An image can be tagged to an axis value (swatch) or a '
                'variant (override), not both.')
        return attrs
```

Delete it entirely (no replacement needed — `ModelSerializer` provides a working default `validate`).

- [ ] **Step 3: Update `ProductAxisValueSerializer`**

In `catalog/serializers.py`, change:

```python
class ProductAxisValueSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()

    class Meta:
        model = AxisValue
        fields = ['id', 'name', 'code', 'images']

    def get_images(self, axis_value):
        return ProductImageSerializer(axis_value.images.all(), many=True).data
```

to:

```python
class ProductAxisValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AxisValue
        fields = ['id', 'name', 'code']
```

- [ ] **Step 4: Update `test_image_response_shape.py`**

In `catalog/tests/test_image_response_shape.py`, change `IMAGE_RESPONSE_KEYS`:

```python
IMAGE_RESPONSE_KEYS = {
    'id', 'object_key', 'alt_text', 'position', 'aspect_ratio', 'role',
    'product_id', 'variant_id', 'axis_value_id', 'src', 'srcset',
}
```

to:

```python
IMAGE_RESPONSE_KEYS = {
    'id', 'object_key', 'alt_text', 'position', 'aspect_ratio', 'role',
    'product_id', 'variant_id', 'src', 'srcset',
}
```

In `test_plain_product_image_has_exact_shape`, remove the line `assert data['axis_value_id'] is None`.

Remove the `test_axis_value_tagged_image_reports_correct_role_and_ids` test entirely:

```python
    def test_axis_value_tagged_image_reports_correct_role_and_ids(self, product):
        axis = ProductAxis.objects.create(product=product, name='Color')
        red = AxisValue.objects.create(axis=axis, name='Red', code='red')
        image = ProductImage.objects.create(
            product=product, image_key='k.png', axis_value=red)

        from catalog.serializers import ProductImageSerializer
        data = ProductImageSerializer(image).data

        assert data['role'] == 'AXIS_VALUE_GALLERY'
        assert data['axis_value_id'] == red.id
        assert data['variant_id'] is None
```

In `test_variant_tagged_image_reports_correct_role_and_ids`, remove the line `assert data['axis_value_id'] is None`.

In `test_product_images_excludes_axis_value_and_variant_tagged`, remove the axis-value setup line and rename the test since it now only tests variant exclusion:

```python
    def test_product_images_excludes_axis_value_and_variant_tagged(self, product):
        axis = ProductAxis.objects.create(product=product, name='Color')
        red = AxisValue.objects.create(axis=axis, name='Red', code='red')
        variant = Variant.objects.create(product=product, sku='test-s', unit_price=1000)
        ProductImage.objects.create(product=product, image_key='plain.png')
        ProductImage.objects.create(product=product, image_key='axis.png', axis_value=red)
        ProductImage.objects.create(product=product, image_key='variant.png', variant=variant)

        from catalog.serializers import ProductSerializer
        data = ProductSerializer(product).data

        assert [img['object_key'] for img in data['images']] == ['plain.png']
```

becomes:

```python
    def test_product_images_excludes_variant_tagged(self, product):
        variant = Variant.objects.create(product=product, sku='test-s', unit_price=1000)
        ProductImage.objects.create(product=product, image_key='plain.png')
        ProductImage.objects.create(product=product, image_key='variant.png', variant=variant)

        from catalog.serializers import ProductSerializer
        data = ProductSerializer(product).data

        assert [img['object_key'] for img in data['images']] == ['plain.png']
```

Remove the `test_axis_value_serializer_exposes_only_its_own_images` test entirely:

```python
    def test_axis_value_serializer_exposes_only_its_own_images(self, product):
        axis = ProductAxis.objects.create(product=product, name='Color')
        red = AxisValue.objects.create(axis=axis, name='Red', code='red')
        blue = AxisValue.objects.create(axis=axis, name='Blue', code='blue')
        ProductImage.objects.create(product=product, image_key='red.png', axis_value=red)
        ProductImage.objects.create(product=product, image_key='blue.png', axis_value=blue)

        from catalog.serializers import ProductAxisValueSerializer
        data = ProductAxisValueSerializer(red).data

        assert [img['object_key'] for img in data['images']] == ['red.png']
```

- [ ] **Step 5: Update `test_variant_batch_and_images.py`**

In `catalog/tests/test_variant_batch_and_images.py`, remove this test from `TestPerVariantImages` (the field it exercises no longer exists on the serializer):

```python
    def test_rejects_both_axis_value_and_variant_on_same_image(
            self, admin_client, product, small, size_axis):
        variant = Variant.objects.create(product=product, sku='test-shirt-s', unit_price=1000)

        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': make_image(), 'variant': variant.id, 'axis_value': small.id},
            format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
```

- [ ] **Step 6: Run tests to verify green**

Run: `pipenv run pytest catalog/tests/test_image_response_shape.py catalog/tests/test_variant_batch_and_images.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add catalog/serializers.py catalog/tests/test_image_response_shape.py catalog/tests/test_variant_batch_and_images.py
git commit -m "feat(catalog): remove axis_value field from image serializers

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Publish-gate validation on `ProductSerializer`

**Files:**
- Modify: `catalog/serializers.py` (`ProductSerializer`, and its imports)
- Test: `catalog/tests/test_product_publish_gate.py` (new)

**Interfaces:**
- Consumes: `ProductImage` (Task 1), `Product.variants` reverse relation, `ProductStatus` (`catalog/models.py`, values `DRAFT`/`PUBLISHED`/`ARCHIVED`).
- Produces: `PATCH`/`PUT` to `/store-admin/products/{id}/` (or any write through `ProductSerializer`) with `status: 'published'` now returns `400` with an error under the `status` key when the product has no own-gallery image or any variant lacks an image.

- [ ] **Step 1: Write the failing tests**

Create `catalog/tests/test_product_publish_gate.py`:

```python
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductImage, ProductStatus, Variant

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def draft_product(collection):
    return Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection,
        status=ProductStatus.DRAFT)


@pytest.mark.django_db
class TestProductPublishGate:
    def test_publish_rejected_when_product_has_no_own_image(self, admin_client, draft_product):
        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'status': 'published'}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'image' in str(response.data['status']).lower()
        draft_product.refresh_from_db()
        assert draft_product.status == ProductStatus.DRAFT

    def test_publish_rejected_when_a_variant_has_no_image(self, admin_client, draft_product):
        ProductImage.objects.create(product=draft_product, image_key='gallery.png')
        variant = Variant.objects.create(
            product=draft_product, sku='test-shirt-s', unit_price=1000)

        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'status': 'published'}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert variant.sku in str(response.data['status'])

    def test_publish_succeeds_when_product_and_every_variant_have_images(
            self, admin_client, draft_product):
        ProductImage.objects.create(product=draft_product, image_key='gallery.png')
        variant = Variant.objects.create(
            product=draft_product, sku='test-shirt-s', unit_price=1000)
        ProductImage.objects.create(
            product=draft_product, image_key='variant.png', variant=variant)

        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'status': 'published'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        draft_product.refresh_from_db()
        assert draft_product.status == ProductStatus.PUBLISHED

    def test_updating_unrelated_field_without_touching_status_is_unaffected(
            self, admin_client, draft_product):
        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'title': 'Renamed Shirt'}, format='json')

        assert response.status_code == status.HTTP_200_OK
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pipenv run pytest catalog/tests/test_product_publish_gate.py -v`
Expected: `test_publish_rejected_when_product_has_no_own_image` and `test_publish_rejected_when_a_variant_has_no_image` FAIL (currently return 200, no gate exists yet); the other two already pass by coincidence.

- [ ] **Step 3: Implement the validation**

In `catalog/serializers.py`, add `ProductStatus` to the existing model import:

```python
from .models import (
    AxisValue, Product, ProductAxis, ProductImage, Collection, Review, Variant,
    VariantAxisValue,
)
```

becomes:

```python
from .models import (
    AxisValue, Product, ProductAxis, ProductImage, ProductStatus, Collection,
    Review, Variant, VariantAxisValue,
)
```

In `class ProductSerializer(serializers.ModelSerializer):`, add a `validate` method (placed after `get_images`, before `create`):

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pipenv run pytest catalog/tests/test_product_publish_gate.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add catalog/serializers.py catalog/tests/test_product_publish_gate.py
git commit -m "feat(catalog): gate product publish on product+variant images

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full catalog test suite**

Run: `pipenv run pytest catalog/ -q`
Expected: all tests pass, none skipped/errored.

- [ ] **Step 2: Run the full project test suite**

Run: `pipenv run pytest -q`
Expected: all tests pass (confirms no other app — `cart`, `orders` — touches `ProductImage.axis_value`).

- [ ] **Step 3: Grep for any remaining `axis_value` reference tied to images**

Run: `grep -rn "axis_value" --include=*.py . | grep -vi "variant_axis_value\|axis_value_ids\|axis_value__\|axis_value=axis_value\|VariantAxisValue"`
Expected: no hits inside `catalog/models.py`, `catalog/serializers.py`, or `catalog/views.py` referring to `ProductImage.axis_value` (only unrelated `VariantAxisValue`/`axis_value_ids` matches, if any, from the variant-attribute-selection feature, which is untouched).

- [ ] **Step 4: Final commit if anything was left uncommitted**

```bash
git status
```

If clean, nothing further to do.
