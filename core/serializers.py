from djoser.serializers import UserSerializer as BaseUserSerializer, UserCreateSerializer as BaseUserCreateSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from cart.services import merge_cart_into_user


class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        fields = ['id', 'password', 'email', 'first_name', 'last_name']


class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ['id', 'email', 'first_name', 'last_name']


class CartMergingTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login (auth/jwt/create/), with one addition: fold the guest
    session's cart into the now-authenticated user's cart before the tokens
    go out. JWT login is stateless — no django.contrib.auth signal fires
    here — so this is the only hook point available."""

    def validate(self, attrs):
        data = super().validate(attrs)
        # Same endpoint serves the store-admin (Refine) login too — staff
        # accounts never shop, so skip conjuring a Cart row for them.
        if not self.user.is_staff:
            merge_cart_into_user(self.context['request'], self.user)
        return data
