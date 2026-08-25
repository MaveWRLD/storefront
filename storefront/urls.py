"""storefront URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView,
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import DefaultRouter
from core import views as core_views

# Overrides djoser.urls' own 'users' router registration (djoser/urls/base.py)
# with a subclass that throttles registration only — must come before the
# djoser.urls include below, same reasoning as the jwt/create override.
_throttled_users_router = DefaultRouter()
_throttled_users_router.register(
    'users', core_views.ThrottledUserViewSet, basename='user')

admin.site.site_header = 'Storefront Admin'
admin.site.index_title = 'Admin'


@api_view(['GET'])
def store_api_root(request, format=None):
    return Response({
        'products': reverse('products-list', request=request, format=format),
        'collections': reverse('collections-list', request=request, format=format),
        'cart': reverse('cart-detail', request=request, format=format),
        'customers': reverse('customers-me', request=request, format=format),
        'orders': reverse('orders-list', request=request, format=format),
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('store-front/', store_api_root, name='api-root'),
    path('store-front/', include('catalog.urls_front')),
    path('store-front/', include('cart.urls')),
    path('store-front/', include('customers.urls_front')),
    path('store-front/', include('orders.urls_front')),
    path('store-front/', include('payment.urls')),
    path('store-front/', include('shipping.urls')),
    path('store-front/', include('returns.urls_front')),
    path('store-admin/', include('catalog.urls_admin')),
    path('store-admin/', include('customers.urls_admin')),
    path('store-admin/', include('orders.urls_admin')),
    path('store-admin/', include('returns.urls_admin')),
    path('store-admin/', include('shipping.urls_admin')),
    path('store-admin/', include('reports.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('auth/', include(_throttled_users_router.urls)),
    path('auth/', include('djoser.urls')),
    # Overrides djoser.urls.jwt's auth/jwt/create/ with a version that also
    # merges the guest session's cart on login (core/views.py) — must come
    # before the djoser.urls.jwt include below, which is only reached for
    # jwt/refresh/, jwt/verify/, etc.
    path('auth/jwt/create/', core_views.CartMergingTokenObtainPairView.as_view(),
         name='jwt-create-with-cart-merge'),
    path('auth/', include('djoser.urls.jwt')),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
