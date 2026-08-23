# Drop axis-value image sharing; add publish-gate image rules

## Context

Current `ProductImage` model supports three ownership shapes:
`PRODUCT_GALLERY` (no FK set), `AXIS_VALUE_GALLERY` (tagged to an
`AxisValue`, e.g. every "Red" variant shares a swatch photo), and
`VARIANT_OVERRIDE` (tagged to one exact `Variant`, no sharing).

This mirrors a marketplace parent/child image model (e.g. Amazon ASIN
families) where the only sharing mechanism is family membership, not
attribute value — there is no equivalent of `AXIS_VALUE_GALLERY`. This
spec removes that one sharing tier and adds two validation rules that
model borrows: a listing needs at least one photo of its own before it
can be published, and so does each of its variants.

Everything else in that reference model already matches current
behavior and needs no change:
- Variant images are already strictly own-array (`variant.images.all()`,
  no fallback to product or sibling images) — no "retained image" bug
  exists here.
- Cross-family (cross-product) `owner_id` references are already
  rejected (`ProductImageSerializer.validate_variant`).
- No dedup/reference-counting exists or is being added — re-uploading
  the same binary to N variants creates N independent rows, as today.

Product/Variant/ProductImage keep their current names and URLs
(`/store-admin/products/{id}/images/`) — no rename to Parent/Child, no
new endpoint. Full scope decision trail is in this conversation's
brainstorming turns; not re-derived here.

## Changes

### 1. Model: `catalog/models.py`

- Remove `ProductImage.axis_value` FK entirely.
- Remove the `productimage_axis_value_or_variant_not_both`
  `CheckConstraint` (only `variant` remains optional-nullable now, no
  second exclusive field to guard against).
- `ProductImage.role` drops the `AXIS_VALUE_GALLERY` branch — only
  `VARIANT_OVERRIDE` (variant set) or `PRODUCT_GALLERY` (unset) remain.
- New migration dropping the column + constraint.

### 2. Serializers: `catalog/serializers.py`

- `ProductImageSerializer`: remove `axis_value` and `axis_value_id`
  fields, `validate_axis_value`, and the both-set check in `validate()`
  (nothing left to conflict with `variant`).
- `ProductAxisValueSerializer`: remove the `images` field and
  `get_images` (was `axis_value.images.all()` — relation no longer
  exists).

### 3. Publish-gate validation

`Product.status` is the existing sole purchasability signal (see
`ProductStatus` docstring: "Only PUBLISHED products are
purchasable/available"). Transitioning a product to `PUBLISHED` — on
create or update, wherever `status` is written — must now be rejected
unless:

- the product has ≥1 own-gallery image
  (`ProductImage.objects.filter(product=product, variant__isnull=True)`), **and**
- every one of the product's variants has ≥1 own image
  (`ProductImage.objects.filter(variant=variant)`).

This is enforced in code (serializer `validate`), not a DB constraint —
same pattern as the existing "one value per axis" / "no duplicate
variant combination" business rules, and consistent with the decision
that `status` (not a separate `buyable` flag) is what gates
purchasability, so no new field is introduced.

On violation: `400` with a message naming which side failed (product
has no gallery image, or which variant SKU(s) lack images).

### 4. Tests

- Delete `catalog/tests/test_axis_value_images.py` (4 tests for the
  removed feature).
- Update/remove any fixture or assertion elsewhere referencing
  `axis_value` on `ProductImage` (e.g. `test_product_image_model.py`'s
  `AXIS_VALUE_GALLERY` role test and the axis_value+variant
  IntegrityError test).
- Add tests for the publish-gate rule:
  - product with no own-gallery image → publish rejected.
  - product with a gallery image but a variant with none → rejected.
  - all variants + product covered → publish succeeds.
  - DRAFT/ARCHIVED transitions are unaffected (no image requirement).

## Out of scope

- Renaming Product/Variant to Parent/Child, or the `/catalog-items/`
  URL — explicitly declined.
- Any new `buyable` field on `Variant` — folded into existing `status`.
- Cart/orders changes — they reference `Variant`, untouched by this.
