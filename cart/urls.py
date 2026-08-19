from rest_framework.routers import DefaultRouter
from django.urls import path
from . import views

router = DefaultRouter()
router.include_root_view = False
router.register('cart/items', views.CartItemViewSet, basename='cart-items')

urlpatterns = [
    path('cart/', views.CartView.as_view(), name='cart-detail'),
] + router.urls
