from django.db import models


class PerformanceEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('app_startup', 'App Startup'),
        ('screen_navigation', 'Screen Navigation'),
    ]

    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    device_model = models.CharField(max_length=100)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    duration_ms = models.FloatField(help_text='Duration in milliseconds')
    timestamp = models.DateTimeField()
    os_version = models.CharField(max_length=20, blank=True, default='')
    app_version = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['device_model']),
        ]

    def __str__(self):
        """
        para simplificar el print y guardado de la info de performance en la db
        :return: la string en formato "tipo_de_evento - modelo_dispositivo - duración_en_ms"
        """
        return f"{self.event_type} - {self.device_model} - {self.duration_ms}ms"


class AnalyticsEvent(models.Model):
    """
    Canonical business-event log ingested from client apps.

    This table is append-only and acts as the raw source for future analytics.
    """

    class EventName(models.TextChoices):
        LISTING_VIEWED = 'listing_viewed', 'Listing Viewed'
        CHAT_STARTED = 'chat_started', 'Chat Started'
        FIRST_MESSAGE_SENT = 'first_message_sent', 'First Message Sent'
        TRANSACTION_COMPLETED = 'transaction_completed', 'Transaction Completed'

    event_name = models.CharField(max_length=50, choices=EventName.choices, db_index=True)
    listing_id = models.BigIntegerField(db_index=True)
    buyer_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    seller_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)
    client_event_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['listing_id', 'event_name', 'occurred_at']),
            models.Index(fields=['event_name', 'occurred_at']),
        ]
        constraints = [
            models.CheckConstraint(
                name='analytics_event_buyer_seller_not_equal_when_both_present',
                condition=(
                    models.Q(buyer_user_id__isnull=True)
                    | models.Q(seller_user_id__isnull=True)
                    | ~models.Q(buyer_user_id=models.F('seller_user_id'))
                ),
            ),
        ]


class ListingAnalyticsState(models.Model):
    """
    Listing-level aggregate state used for defensible, fast KPI reporting.

    One row per listing acts as the current backend truth for key outcomes.
    """

    listing_id = models.BigIntegerField(unique=True, db_index=True)
    buyer_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    seller_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    has_messaging_interaction = models.BooleanField(default=False, db_index=True)
    first_messaging_at = models.DateTimeField(null=True, blank=True)
    is_transaction_completed = models.BooleanField(default=False, db_index=True)
    transaction_completed_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['listing_id']
        indexes = [
            models.Index(fields=['has_messaging_interaction', 'is_transaction_completed']),
            models.Index(fields=['updated_at']),
        ]
