from django.urls import path
from . import views

urlpatterns = [
    path('payments/initialize/', views.InitializePaymentView.as_view(), name='payment-initialize'),
    path('payments/verify/', views.VerifyPaymentView.as_view(), name='payment-verify'),
    path('payments/webhook/', views.PaystackWebhookView.as_view(), name='payment-webhook'),
]
