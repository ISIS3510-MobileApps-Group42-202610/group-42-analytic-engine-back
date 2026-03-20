from django.urls import path

from marketplace_analytics.views import (
    post_performance_event,
    bq2_dashboard,
    q9_dashboard,
    performance_summary_api,
    BusinessEventIngestionAPIView,
    Q9MessagingImpactAPIView,
    BQ3SearchDiscoveryEventIngestionAPIView,
    BQ3SearchToInteractionAPIView,
    bq3_dashboard,
)

urlpatterns = [
    # ====== Performance BQ2 ==========
    path('api/performance', post_performance_event, name='performance-event'),
    path('api/performance-summary/', performance_summary_api, name='performance-summary'),
    path('api/dashboard/bq2', bq2_dashboard, name='bq2-dashboard'),
    path('api/dashboard/bq9', q9_dashboard, name='bq9-dashboard'),
    # ====== Business Events / Q9 ==========
    path('api/business-events/', BusinessEventIngestionAPIView.as_view(), name='business-event-ingestion'),
    path('api/reports/q9-messaging-impact/', Q9MessagingImpactAPIView.as_view(), name='q9-messaging-impact'),
    # ====== BQ3 Search / Filter to Interaction ==========
    path('api/bq3/events/', BQ3SearchDiscoveryEventIngestionAPIView.as_view(), name='bq3-event-ingestion'),
    path('api/reports/bq3-search-to-interaction/', BQ3SearchToInteractionAPIView.as_view(), name='bq3-search-to-interaction'),
    path('api/dashboard/bq3', bq3_dashboard, name='bq3-dashboard'),
]
