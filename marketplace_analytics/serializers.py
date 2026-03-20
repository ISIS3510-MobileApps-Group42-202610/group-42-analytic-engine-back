from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from marketplace_analytics.models import AnalyticsEvent
from marketplace_analytics.models import SearchDiscoveryEvent


class AnalyticsEventIngestSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField(source='occurred_at', required=False)

    class Meta:
        model = AnalyticsEvent
        fields = [
            'event_name',
            'listing_id',
            'buyer_user_id',
            'seller_user_id',
            'timestamp',
            'metadata',
            'client_event_id',
        ]

    def validate_metadata(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('metadata must be a JSON object.')
        return value

    def validate(self, attrs):
        event_name = attrs.get('event_name')
        buyer_user_id = attrs.get('buyer_user_id')
        seller_user_id = attrs.get('seller_user_id')

        if event_name == AnalyticsEvent.EventName.FIRST_MESSAGE_SENT:
            if not buyer_user_id or not seller_user_id:
                raise serializers.ValidationError(
                    'first_message_sent requires both buyer_user_id and seller_user_id.'
                )

        if buyer_user_id and seller_user_id and buyer_user_id == seller_user_id:
            raise serializers.ValidationError('buyer_user_id and seller_user_id cannot be the same.')

        if 'occurred_at' not in attrs:
            attrs['occurred_at'] = timezone.now()

        if attrs['occurred_at'] > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError('timestamp cannot be far in the future.')

        return attrs


class SearchDiscoveryEventIngestSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField(source='occurred_at', required=False)

    class Meta:
        model = SearchDiscoveryEvent
        fields = [
            'session_id',
            'user_id',
            'event_name',
            'listing_id',
            'selected_course_id',
            'selected_course_name',
            'selected_category_id',
            'selected_category_name',
            'selected_filter_type',
            'search_query',
            'platform',
            'app_version',
            'timestamp',
            'metadata',
            'client_event_id',
        ]

    def validate_metadata(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('metadata must be a JSON object.')
        return value

    def validate(self, attrs):
        event_name = attrs.get('event_name')
        listing_id = attrs.get('listing_id')
        filter_type = attrs.get('selected_filter_type', SearchDiscoveryEvent.FilterType.NONE)
        selected_course_id = attrs.get('selected_course_id')
        selected_category_id = attrs.get('selected_category_id')

        interaction_events = {
            SearchDiscoveryEvent.EventName.LISTING_OPENED,
            SearchDiscoveryEvent.EventName.MESSAGE_SENT,
            SearchDiscoveryEvent.EventName.RESERVATION_CREATED,
        }

        if event_name in interaction_events and not listing_id:
            raise serializers.ValidationError(
                f'{event_name} requires listing_id.'
            )

        if filter_type == SearchDiscoveryEvent.FilterType.COURSE and not selected_course_id:
            raise serializers.ValidationError(
                'selected_filter_type="course" requires selected_course_id.'
            )

        if filter_type == SearchDiscoveryEvent.FilterType.CATEGORY and not selected_category_id:
            raise serializers.ValidationError(
                'selected_filter_type="category" requires selected_category_id.'
            )

        if filter_type == SearchDiscoveryEvent.FilterType.BOTH:
            if not selected_course_id or not selected_category_id:
                raise serializers.ValidationError(
                    'selected_filter_type="both" requires both selected_course_id and selected_category_id.'
                )

        if 'occurred_at' not in attrs:
            attrs['occurred_at'] = timezone.now()

        if attrs['occurred_at'] > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError('timestamp cannot be far in the future.')

        return attrs