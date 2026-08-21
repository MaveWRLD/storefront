from djoser.views import UserViewSet
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CartMergingTokenObtainPairSerializer


class CartMergingTokenObtainPairView(TokenObtainPairView):
    """Drop-in replacement for djoser.urls.jwt's auth/jwt/create/ — same
    request/response shape, plus the guest-cart merge in the serializer.

    IP-keyed rate limit (gap-analysis doc: 'No rate limiting anywhere') —
    Spring runs 5/min on login, matched here via the 'auth' throttle scope.
    """
    serializer_class = CartMergingTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'


class ThrottledUserViewSet(UserViewSet):
    """Drop-in replacement for djoser.urls' users/ router — same behavior,
    plus a rate limit on registration only (Spring: 5/min on register,
    IP-keyed). Every other action (me, activation, set_password, ...)
    keeps djoser's defaults untouched."""

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'auth'
            return [ScopedRateThrottle()]
        return super().get_throttles()
