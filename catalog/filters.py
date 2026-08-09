from django_filters.rest_framework import FilterSet, NumberFilter
from .models import Product


class ProductFilter(FilterSet):
    # Price now lives on Variant (Catalog class diagram), so filtering by
    # price range crosses the relation instead of using a direct model field.
    unit_price__gt = NumberFilter(
        field_name='variants__unit_price', lookup_expr='gt')
    unit_price__lt = NumberFilter(
        field_name='variants__unit_price', lookup_expr='lt')

    class Meta:
        model = Product
        fields = {
            'collection_id': ['exact'],
        }
