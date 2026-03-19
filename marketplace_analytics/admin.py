from django.contrib import admin

from marketplace_analytics.models import PerformanceEvent, AnalyticsEvent, ListingAnalyticsState


@admin.register(PerformanceEvent)
class PerformanceEventAdmin(admin.ModelAdmin):
	list_display = ('event_type', 'device_model', 'platform', 'duration_ms', 'timestamp')
	list_filter = ('event_type', 'platform')
	search_fields = ('device_model',)


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
	list_display = ('event_name', 'listing_id', 'buyer_user_id', 'seller_user_id', 'occurred_at')
	list_filter = ('event_name',)
	search_fields = ('listing_id', 'buyer_user_id', 'seller_user_id', 'client_event_id')


@admin.register(ListingAnalyticsState)
class ListingAnalyticsStateAdmin(admin.ModelAdmin):
	list_display = (
		'listing_id',
		'has_messaging_interaction',
		'is_transaction_completed',
		'first_messaging_at',
		'transaction_completed_at',
		'updated_at',
	)
	list_filter = ('has_messaging_interaction', 'is_transaction_completed')
	search_fields = ('listing_id', 'buyer_user_id', 'seller_user_id')
