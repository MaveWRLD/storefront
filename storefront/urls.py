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
import debug_toolbar

admin.site.site_header = 'Storefront Admin'
admin.site.index_title = 'Admin'


@api_view(['GET'])
def store_api_root(request, format=None):
    return Response({
        'products': reverse('products-list', request=request, format=format),
        'collections': reverse('collection-list', request=request, format=format),
        'carts': reverse('cart-list', request=request, format=format),
        'customers': reverse('customer-list', request=request, format=format),
        'orders': reverse('orders-list', request=request, format=format),
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('store/', store_api_root, name='api-root'),
    path('store/', include('catalog.urls')),
    path('store/', include('cart.urls')),
    path('store/', include('customers.urls')),
    path('store/', include('orders.urls')),
    path('store/', include('payment.urls')),
    path('store/', include('returns.urls')),
    path('store/', include('reports.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
    path('__debug__/', include(debug_toolbar.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
