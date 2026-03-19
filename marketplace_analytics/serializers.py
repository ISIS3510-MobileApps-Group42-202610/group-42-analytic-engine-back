from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from marketplace_analytics.models import AnalyticsEvent


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
