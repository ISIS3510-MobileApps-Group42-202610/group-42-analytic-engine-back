from django.urls import path

from marketplace_analytics.views import post_performance_event, bq2_dashboard, performance_summary_api

urlpatterns = [
    # ====== Performance BQ2 ==========
    path('api/performance', post_performance_event, name='performance-event'),
    path('api/performance-summary/', performance_summary_api, name='performance-summary'),
    path('api/dashboard/bq2', bq2_dashboard, name='bq2-dashboard'),
]
