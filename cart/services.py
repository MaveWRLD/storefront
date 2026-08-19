from django.db import transaction
from .models import Cart, CartItem

# The only thing the guest session carries — an id pointing at a Cart row.
# Session engine is signed_cookies (storefront/settings.py), so this lives
# entirely in the signed cookie, never in a server-side session table.
CART_SESSION_KEY = 'cart_id'


def get_current_cart(request):
    if request.user.is_authenticated:
        return Cart.objects.filter(user=request.user).first()

    cart_id = request.session.get(CART_SESSION_KEY)
    if not cart_id:
        return None
    return Cart.objects.filter(pk=cart_id, user__isnull=True).first()


def get_or_create_cart(request):
    cart = get_current_cart(request)
    if cart is not None:
        return cart

    if request.user.is_authenticated:
        return Cart.objects.create(user=request.user)

    cart = Cart.objects.create()
    request.session[CART_SESSION_KEY] = str(cart.id)
    return cart


def merge_cart_into_user(request, user):
    cart_id = request.session.get(CART_SESSION_KEY)
    if not cart_id:
        return

    with transaction.atomic():
        anon_cart = Cart.objects.filter(
            pk=cart_id, user__isnull=True
        ).prefetch_related('items__variant').first()
        if anon_cart is not None:
            user_cart, _ = Cart.objects.get_or_create(user=user)
            for item in anon_cart.items.all():
                existing = CartItem.objects.filter(
                    cart=user_cart, variant_id=item.variant_id).first()
                already_claimed = existing.quantity if existing is not None else 0

                if item.variant.track_inventory:
                    remainder = max(item.variant.available - already_claimed, 0)
                    transferable = min(item.quantity, remainder)
                else:
                    transferable = item.quantity

                if transferable <= 0:
                    continue

                if existing is not None:
                    existing.quantity = already_claimed + transferable
                    existing.save()
                else:
                    CartItem.objects.create(
                        cart=user_cart, variant_id=item.variant_id,
                        quantity=transferable)
            anon_cart.delete()

    request.session.pop(CART_SESSION_KEY, None)
