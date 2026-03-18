from django.urls import path

from marketplace_analytics.views import post_performance_event, bq1_dashboard, performance_summary_api

urlpatterns = [
    # ====== Performance BQ1 ==========
    path('api/performance', post_performance_event, name='performance-event'),
    path('api/performance-summary/', performance_summary_api, name='performance-summary'),
    path('api/dashboard/bq1', bq1_dashboard, name='bq1-dashboard'),
]
