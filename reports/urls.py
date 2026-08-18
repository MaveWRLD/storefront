from django.urls import path
from . import views

urlpatterns = [
    path('reports/sales/', views.SalesReportView.as_view(), name='sales-report'),
    path('dashboard/summary/', views.DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('dashboard/sales-chart/', views.SalesChartView.as_view(), name='dashboard-sales-chart'),
    path('dashboard/recent-orders/', views.RecentOrdersView.as_view(), name='dashboard-recent-orders'),
]
