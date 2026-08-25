from django.template.loader import render_to_string
from weasyprint import HTML

from .serializers import OrderSerializer


def render_invoice_pdf(order):
    """Render the invoice for `order` to PDF bytes.

    Shared by OrderViewSet.invoice and OrderAdminViewSet.invoice (orders/
    views.py) so the two access-controlled endpoints don't duplicate the
    template rendering.
    """
    line_items = [
        {
            'title': item.variant.product.title,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'line_total': item.quantity * item.unit_price,
        }
        for item in order.items.select_related('variant__product')
    ]
    # Reuse OrderSerializer's name/email derivation (customer vs. guest
    # shipping_address) instead of duplicating that split here.
    serializer = OrderSerializer(order)
    html = render_to_string('orders/invoice.html', {
        'order': order,
        'name': serializer.get_name(order),
        'email': serializer.get_email(order),
        'address': order.shipping_address,
        'line_items': line_items,
    })
    return HTML(string=html).write_pdf()
