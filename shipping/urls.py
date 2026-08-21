from django.urls import path
from . import views

urlpatterns = [
    path('shipping/rates/', views.RateQuoteView.as_view(), name='shipping-rates'),
    path('shipping/shipments/<int:order_id>/', views.ShipmentDetailView.as_view(),
         name='shipping-shipment-detail'),
    path('shipping/webhook/', views.ShippingWebhookView.as_view(), name='shipping-webhook'),
]
