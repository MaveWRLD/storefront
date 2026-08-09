from django.conf import settings
from django.db.models import Sum
from djmoney.money import Money
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem


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
