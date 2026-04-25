from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from marketplace_analytics.models import CrashEvent
from marketplace_analytics.models import AnalyticsEvent
from marketplace_analytics.models import SearchDiscoveryEvent
from marketplace_analytics.models import MessagingResponseEvent


class AnalyticsEventIngestSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField(source='occurred_at', required=False)

    EVENT_ALIASES = {
        'listing_opened': AnalyticsEvent.EventName.LISTING_VIEWED,
        'view_listing': AnalyticsEvent.EventName.LISTING_VIEWED,
        'product_viewed': AnalyticsEvent.EventName.LISTING_VIEWED,
        'chat_opened': AnalyticsEvent.EventName.CHAT_STARTED,
        'conversation_started': AnalyticsEvent.EventName.CHAT_STARTED,
        'message_sent': AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
        'comment_sent': AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
        'comment_created': AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
        'buyer_seller_message_sent': AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
        'sale_completed': AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
        'purchase_completed': AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
        'listing_sold': AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
        'product_sold': AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
        'reservation_completed': AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
    }

    def to_internal_value(self, data):
        mutable_data = data.copy()
        event_name = mutable_data.get('event_name')
        if isinstance(event_name, str):
            normalized_event_name = event_name.strip().lower()
            mutable_data['event_name'] = self.EVENT_ALIASES.get(
                normalized_event_name,
                normalized_event_name,
            )
        return super().to_internal_value(mutable_data)

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


class CrashEventIngestSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField(source='occurred_at', required=False)

    class Meta:
        model = CrashEvent
        fields = [
            'event_name',
            'feature_name',
            'code_location',
            'crash_signature',
            'stack_trace',
            'device_model',
            'platform',
            'os_version',
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
        if 'metadata' not in attrs or attrs['metadata'] is None:
            attrs['metadata'] = {}

        if 'occurred_at' not in attrs:
            attrs['occurred_at'] = timezone.now()

        if attrs['occurred_at'] > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError('timestamp cannot be far in the future.')

        feature_name = (attrs.get('feature_name') or '').strip()
        code_location = (attrs.get('code_location') or '').strip()
        crash_signature = (attrs.get('crash_signature') or '').strip()

        if not crash_signature:
            raise serializers.ValidationError('crash_signature is required.')

        if not feature_name and not code_location:
            raise serializers.ValidationError(
                'Either feature_name or code_location must be provided.'
            )

        attrs['feature_name'] = feature_name
        attrs['code_location'] = code_location
        attrs['crash_signature'] = crash_signature

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


class MessagingResponseEventIngestSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessagingResponseEvent
        fields = [
            'event_name',
            'user_id',
            'seller_id',
            'avg_response_minutes',
            'unread_conversations',
            'timestamp',
            'properties',
        ]

    def validate_properties(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('properties must be a JSON object.')
        return value

    def validate(self, attrs):
        event_name = attrs.get('event_name')
        seller_id = attrs.get('seller_id')
        avg_response_minutes = attrs.get('avg_response_minutes')
        unread_conversations = attrs.get('unread_conversations')
        timestamp = attrs.get('timestamp')

        if 'properties' not in attrs or attrs['properties'] is None:
            attrs['properties'] = {}

        if timestamp is None:
            attrs['timestamp'] = timezone.now()

        if attrs['timestamp'] > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError('timestamp cannot be far in the future.')

        response_metric_events = {
            MessagingResponseEvent.EventName.SELLER_AVG_RESPONSE_TIME,
        }

        contact_events = {
            MessagingResponseEvent.EventName.MESSAGE_SENT,
            MessagingResponseEvent.EventName.FIRST_MESSAGE_SENT,
        }

        if event_name in response_metric_events:
            if seller_id is None:
                raise serializers.ValidationError(
                    'seller_avg_response_time requires seller_id.'
                )
            if avg_response_minutes is None:
                raise serializers.ValidationError(
                    'seller_avg_response_time requires avg_response_minutes.'
                )
            if avg_response_minutes < 0:
                raise serializers.ValidationError(
                    'avg_response_minutes must be greater than or equal to 0.'
                )

        if event_name in contact_events and seller_id is None:
            raise serializers.ValidationError(
                f'{event_name} requires seller_id.'
            )

        if unread_conversations is not None and unread_conversations < 0:
            raise serializers.ValidationError(
                'unread_conversations must be greater than or equal to 0.'
            )

        return attrs
