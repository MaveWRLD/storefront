from django.contrib import admin
from django.db.models.aggregates import Count
from django.utils.html import format_html, urlencode
from django.urls import reverse
from . import models


@admin.register(models.Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name',  'membership', 'orders']
    list_editable = ['membership']
    list_per_page = 10
    list_select_related = ['user']
    ordering = ['user__first_name', 'user__last_name']
    search_fields = ['user__first_name__istartswith', 'user__last_name__istartswith']

    @admin.display(ordering='orders_count')
    def orders(self, customer):
        url = (
            reverse('admin:orders_order_changelist')
            + '?'
            + urlencode({
                'customer__id': str(customer.id)
            }))
        return format_html('<a href="{}">{} Orders</a>', url, customer.orders_count)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            orders_count=Count('order')
        )
