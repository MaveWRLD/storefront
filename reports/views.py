from collections import OrderedDict
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from djmoney.money import Money
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Variant
from customers.models import Customer
from orders.models import Order, OrderItem

DEFAULT_LOW_STOCK_THRESHOLD = 5
DEFAULT_CHART_DAYS = 30
DEFAULT_RECENT_LIMIT = 10


class SalesReportView(APIView):
    """US-29: 'they should see key metrics (sales, orders, top products)
    over a selected time range.' No Business Rules exist for this domain
    (Reporting is ApparelFit-specific, not a core Saleor domain) — built
    straight from the story's own acceptance criteria."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary='Sales report',
        description='Return order count, total sales, and top products, optionally filtered by a start/end date range. Staff-only.')
    def get(self, request):
        orders = Order.objects.filter(
            payment_status=Order.PAYMENT_STATUS_COMPLETE)

        start = request.query_params.get('start')
        end = request.query_params.get('end')
        if start:
            orders = orders.filter(placed_at__date__gte=start)
        if end:
            orders = orders.filter(placed_at__date__lte=end)

        total_sales = sum(
            (order.get_total() for order in orders),
            start=Money(0, settings.DEFAULT_CURRENCY))

        top_products = (
            OrderItem.objects
            .filter(order__in=orders)
            .values('variant__product_id', 'variant__product__title')
            .annotate(quantity_sold=Sum('quantity'))
            .order_by('-quantity_sold')[:5]
        )

        return Response({
            'order_count': orders.count(),
            'total_sales': total_sales.amount,
            'top_products': [
                {
                    'product_id': p['variant__product_id'],
                    'title': p['variant__product__title'],
                    'quantity_sold': p['quantity_sold'],
                }
                for p in top_products
            ],
        })


class DashboardSummaryView(APIView):
    """Admin dashboard stat tiles: total orders, total revenue (completed
    payments), total customers, low-stock variant count. Staff-only."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary='Dashboard summary',
        description=(
            'Return total orders, total revenue, total customers, and '
            'low-stock variant count for admin dashboard tiles. '
            'Optional `threshold` query param sets the low-stock cutoff '
            f'(default {DEFAULT_LOW_STOCK_THRESHOLD}). Staff-only.'))
    def get(self, request):
        completed_orders = Order.objects.filter(
            payment_status=Order.PAYMENT_STATUS_COMPLETE)
        total_revenue = sum(
            (order.get_total() for order in completed_orders),
            start=Money(0, settings.DEFAULT_CURRENCY))

        threshold = int(request.query_params.get(
            'threshold', DEFAULT_LOW_STOCK_THRESHOLD))
        low_stock_variants = Variant.objects.filter(
            track_inventory=True, inventory__lte=threshold)

        return Response({
            'total_orders': Order.objects.count(),
            'total_revenue': total_revenue.amount,
            'total_customers': Customer.objects.count(),
            'low_stock_variants': low_stock_variants.count(),
        })


class SalesChartView(APIView):
    """Daily order-count + revenue buckets for the dashboard trend chart.
    Staff-only."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary='Sales chart',
        description=(
            'Return per-day order count and revenue buckets for the last N '
            f'days (default {DEFAULT_CHART_DAYS}, via `days` query param). '
            'Days with no orders come back as zero, not omitted. Staff-only.'))
    def get(self, request):
        days = int(request.query_params.get('days', DEFAULT_CHART_DAYS))
        today = timezone.localdate()
        start_date = today - timedelta(days=days - 1)

        buckets = OrderedDict(
            (start_date + timedelta(days=i),
             {'order_count': 0, 'revenue': Money(0, settings.DEFAULT_CURRENCY)})
            for i in range(days)
        )

        orders = Order.objects.filter(
            payment_status=Order.PAYMENT_STATUS_COMPLETE,
            placed_at__date__gte=start_date,
            placed_at__date__lte=today,
        ).prefetch_related('items')

        for order in orders:
            bucket = buckets.get(timezone.localtime(order.placed_at).date())
            if bucket is None:
                continue
            bucket['order_count'] += 1
            bucket['revenue'] += order.get_total()

        return Response([
            {
                'date': date.isoformat(),
                'order_count': bucket['order_count'],
                'revenue': bucket['revenue'].amount,
            }
            for date, bucket in buckets.items()
        ])


class RecentOrdersView(APIView):
    """Latest orders table for the dashboard. Staff-only."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary='Recent orders',
        description=(
            'Return the most recent orders, newest first. `limit` query '
            f'param caps the row count (default {DEFAULT_RECENT_LIMIT}). '
            'Staff-only.'))
    def get(self, request):
        limit = int(request.query_params.get('limit', DEFAULT_RECENT_LIMIT))
        orders = (
            Order.objects
            .select_related('customer__user')
            .prefetch_related('items')
            .order_by('-placed_at')[:limit]
        )

        return Response([
            {
                'id': order.id,
                'customer_name': (
                    f'{order.customer.user.first_name} {order.customer.user.last_name}'.strip()
                    if order.customer_id else order.guest_name),
                'email': order.get_email(),
                'placed_at': order.placed_at,
                'total': order.get_total().amount,
                'payment_status': order.payment_status,
                'status': order.status,
            }
            for order in orders
        ])
