from django.urls import path
from . import views

urlpatterns = [
    path('reports/sales/', views.SalesReportView.as_view(), name='sales-report'),
]
