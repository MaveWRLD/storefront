from django.urls import path
from . import views

urlpatterns = [
    path('shipments/<int:order_id>/pickup/', views.CreatePickupView.as_view(),
         name='shipping-create-pickup'),
]
