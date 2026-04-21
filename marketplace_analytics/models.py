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
            models.Index(fields=['event_type', 'timestamp'], name='bq2_event_time_idx'),
            models.Index(fields=['device_model'], name='bq2_device_idx'),
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
            models.Index(
                fields=['listing_id', 'event_name', 'occurred_at'],
                name='bq9_listing_event_occ_idx',
            ),
            models.Index(
                fields=['event_name', 'occurred_at'],
                name='bq9_event_occ_idx',
            ),
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
            models.Index(
                fields=['has_messaging_interaction', 'is_transaction_completed'],
                name='bq9_msg_txn_idx',
            ),
            models.Index(
                fields=['updated_at'],
                name='bq9_updated_idx',
            ),
        ]


class SearchDiscoveryEvent(models.Model):
    class EventName(models.TextChoices):
        SEARCH_STARTED = 'search_started', 'Search Started'
        FILTER_APPLIED = 'filter_applied', 'Filter Applied'
        LISTING_OPENED = 'listing_opened', 'Listing Opened'
        MESSAGE_SENT = 'message_sent', 'Message Sent'
        RESERVATION_CREATED = 'reservation_created', 'Reservation Created'

    class FilterType(models.TextChoices):
        COURSE = 'course', 'Course'
        CATEGORY = 'category', 'Category'
        BOTH = 'both', 'Both'
        NONE = 'none', 'None'

    session_id = models.CharField(max_length=64, db_index=True)
    user_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    event_name = models.CharField(
        max_length=32,
        choices=EventName.choices,
        db_index=True,
    )

    listing_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    selected_course_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    selected_course_name = models.CharField(max_length=255, null=True, blank=True)

    selected_category_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    selected_category_name = models.CharField(max_length=255, null=True, blank=True)

    selected_filter_type = models.CharField(
        max_length=20,
        choices=FilterType.choices,
        default=FilterType.NONE,
        db_index=True,
    )

    search_query = models.CharField(max_length=255, null=True, blank=True)
    platform = models.CharField(max_length=20, blank=True, default='ios')
    app_version = models.CharField(max_length=40, blank=True, default='')

    occurred_at = models.DateTimeField(db_index=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    metadata = models.JSONField(default=dict, blank=True)
    client_event_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['session_id', 'occurred_at'], name='bq3_session_occ_idx'),
            models.Index(fields=['event_name', 'occurred_at'], name='bq3_event_occ_idx'),
            models.Index(fields=['selected_filter_type', 'occurred_at'], name='bq3_filter_occ_idx'),
            models.Index(fields=['selected_course_id'], name='bq3_course_idx'),
            models.Index(fields=['selected_category_id'], name='bq3_category_idx'),
        ]

    def __str__(self):
        return f'{self.session_id} - {self.event_name} - {self.occurred_at.isoformat()}'


class MessagingResponseEvent(models.Model):
    """
    BQ4: Tracks seller response times and messaging activity.
    Stores events related to messaging interactions between buyers and sellers.
    """
    
    class EventName(models.TextChoices):
        MESSAGES_SCREEN_OPENED = 'messages_screen_opened', 'Messages Screen Opened'
        MESSAGE_SENT = 'message_sent', 'Message Sent'
        SELLER_AVG_RESPONSE_TIME = 'seller_avg_response_time', 'Seller Avg Response Time'
        FIRST_MESSAGE_SENT = 'first_message_sent', 'First Message Sent'
    
    event_name = models.CharField(max_length=50, choices=EventName.choices, db_index=True)
    user_id = models.BigIntegerField(db_index=True)
    seller_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    avg_response_minutes = models.FloatField(null=True, blank=True, help_text='Average response time in minutes')
    unread_conversations = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    properties = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['event_name', 'timestamp'], name='bq4_event_time_idx'),
            models.Index(fields=['seller_id', 'timestamp'], name='bq4_seller_time_idx'),
            models.Index(fields=['user_id'], name='bq4_user_idx'),
        ]
    
    def __str__(self):
        return f'{self.event_name} - User {self.user_id} - {self.timestamp.isoformat()}'