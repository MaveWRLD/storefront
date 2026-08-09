from django.contrib import admin
from django.db.models.aggregates import Count
from django.utils.html import format_html, urlencode
from django.urls import reverse
from . import models


class VariantInline(admin.TabularInline):
    # Price/inventory now live on Variant (Catalog class diagram), not
    # Product — edit them here instead of the old Product list_editable.
    model = models.Variant
    extra = 1


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ['collection']
    prepopulated_fields = {
        'slug': ['title']
    }
    inlines = [VariantInline]
    list_display = ['title', 'collection_title']
    list_filter = ['collection', 'last_update']
    list_per_page = 10
    list_select_related = ['collection']
    search_fields = ['title']

    def collection_title(self, product):
        return product.collection.title


@admin.register(models.Variant)
class VariantAdmin(admin.ModelAdmin):
    autocomplete_fields = ['product']
    list_display = ['sku', 'product', 'unit_price', 'inventory']
    search_fields = ['sku']


@admin.register(models.Collection)
class CollectionAdmin(admin.ModelAdmin):
    autocomplete_fields = ['featured_product']
    list_display = ['title', 'products_count']
    search_fields = ['title']

    @admin.display(ordering='products_count')
    def products_count(self, collection):
        url = (
            reverse('admin:catalog_product_changelist')
            + '?'
            + urlencode({
                'collection__id': str(collection.id)
            }))
        return format_html('<a href="{}">{} Products</a>', url, collection.products_count)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            products_count=Count('products')
        )
