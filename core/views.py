from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CartMergingTokenObtainPairSerializer


class CartMergingTokenObtainPairView(TokenObtainPairView):
    """Drop-in replacement for djoser.urls.jwt's auth/jwt/create/ — same
    request/response shape, plus the guest-cart merge in the serializer."""
    serializer_class = CartMergingTokenObtainPairSerializer
