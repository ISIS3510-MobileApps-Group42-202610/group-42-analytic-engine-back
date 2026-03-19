from datetime import datetime

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from marketplace_analytics.models import AnalyticsEvent, ListingAnalyticsState


MESSAGING_EVENTS = {
    AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
}


@transaction.atomic
def ingest_business_event(validated_event_data):
    """
    Persist a validated analytics event and update listing-level aggregate state.
    """
    event = AnalyticsEvent.objects.create(**validated_event_data)
    _upsert_listing_state_from_event(event)
    return event


def _upsert_listing_state_from_event(event):
    state, _ = ListingAnalyticsState.objects.get_or_create(listing_id=event.listing_id)

    fields_to_update = []

    if event.buyer_user_id and not state.buyer_user_id:
        state.buyer_user_id = event.buyer_user_id
        fields_to_update.append('buyer_user_id')

    if event.seller_user_id and not state.seller_user_id:
        state.seller_user_id = event.seller_user_id
        fields_to_update.append('seller_user_id')

    if event.event_name in MESSAGING_EVENTS and event.buyer_user_id and event.seller_user_id:
        if not state.has_messaging_interaction:
            state.has_messaging_interaction = True
            fields_to_update.append('has_messaging_interaction')

        if state.first_messaging_at is None or event.occurred_at < state.first_messaging_at:
            state.first_messaging_at = event.occurred_at
            fields_to_update.append('first_messaging_at')

    if event.event_name == AnalyticsEvent.EventName.TRANSACTION_COMPLETED:
        if not state.is_transaction_completed:
            state.is_transaction_completed = True
            fields_to_update.append('is_transaction_completed')

        if state.transaction_completed_at is None or event.occurred_at < state.transaction_completed_at:
            state.transaction_completed_at = event.occurred_at
            fields_to_update.append('transaction_completed_at')

    if state.last_event_at is None or event.occurred_at > state.last_event_at:
        state.last_event_at = event.occurred_at
        fields_to_update.append('last_event_at')

    if fields_to_update:
        fields_to_update.append('updated_at')
        state.save(update_fields=fields_to_update)


def calculate_q9_messaging_impact_metric():
    """
    Q9: Compare listing completion rate by messaging interaction.

    Defensible definitions used:
    - Listing with messaging: at least one meaningful buyer-seller interaction event.
            (chat_started or first_message_sent with both buyer and seller ids present)
    - Completed listing: listing-level final state has transaction completion flagged.
    """
    return calculate_q9_messaging_impact_metric_with_filters()


def calculate_q9_messaging_impact_metric_with_filters(
    since: datetime | None = None,
    until: datetime | None = None,
    period_label: str = 'all_time',
):
    """
    Calculate Q9 metric with optional date filtering over the analytics event stream.

    Date window controls the analysis population: listings with any event in the range.
    Completion still uses listing final backend state (ListingAnalyticsState).
    """
    population_listing_ids = _population_listing_ids_for_window(since=since, until=until)

    listing_states = ListingAnalyticsState.objects.filter(listing_id__in=population_listing_ids)

    messaging_listing_ids = _messaging_listing_ids_for_window(since=since, until=until)

    with_messaging = listing_states.filter(listing_id__in=messaging_listing_ids)
    without_messaging = listing_states.exclude(listing_id__in=messaging_listing_ids)

    with_total = with_messaging.count()
    with_completed = with_messaging.filter(is_transaction_completed=True).count()

    without_total = without_messaging.count()
    without_completed = without_messaging.filter(is_transaction_completed=True).count()

    with_rate = (with_completed / with_total) if with_total else None
    without_rate = (without_completed / without_total) if without_total else None

    absolute_difference = None
    relative_lift_percentage = None

    if with_rate is not None and without_rate is not None:
        absolute_difference = with_rate - without_rate
        if without_rate > 0:
            relative_lift_percentage = ((with_rate - without_rate) / without_rate) * 100

    return {
        'period': {
            'label': period_label,
            'since': since,
            'until': until,
        },
        'group_with_messaging': {
            'listings': with_total,
            'completed': with_completed,
            'completion_rate': with_rate,
        },
        'group_without_messaging': {
            'listings': without_total,
            'completed': without_completed,
            'completion_rate': without_rate,
        },
        'absolute_difference': absolute_difference,
        'relative_lift_percentage': relative_lift_percentage,
        'definitions': {
            'listing_with_messaging': (
                'At least one first_message_sent event with '
                'buyer_user_id and seller_user_id present.'
            ),
            'chat_started_usage': (
                'chat_started is treated as informational and does not define '
                'messaging interaction for Q9 grouping.'
            ),
            'completed_transaction': (
                'ListingAnalyticsState.is_transaction_completed = true '
                '(updated by transaction_completed business events).'
            ),
        },
    }


def _population_listing_ids_for_window(since=None, until=None):
    events = AnalyticsEvent.objects.all()
    if since is not None:
        events = events.filter(occurred_at__gte=since)
    if until is not None:
        events = events.filter(occurred_at__lte=until)
    return events.values_list('listing_id', flat=True).distinct()


def _messaging_listing_ids_for_window(since=None, until=None):
    messaging_events = AnalyticsEvent.objects.filter(
        event_name=AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
        buyer_user_id__isnull=False,
        seller_user_id__isnull=False,
    )
    if since is not None:
        messaging_events = messaging_events.filter(occurred_at__gte=since)
    if until is not None:
        messaging_events = messaging_events.filter(occurred_at__lte=until)
    return messaging_events.values_list('listing_id', flat=True).distinct()


def resolve_reporting_window(period: str, start=None, end=None):
    now = timezone.now()

    if period == 'last_30_days':
        return now - timezone.timedelta(days=30), now, period

    if period == 'semester_to_date':
        semester_start = _semester_start_for(now)
        return semester_start, now, period

    if period == 'custom':
        return start, end, period

    return None, None, 'all_time'


def _semester_start_for(reference_dt):
    # Academic semester simplification: Jan-Jun or Jul-Dec.
    month = reference_dt.month
    if month <= 6:
        return reference_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return reference_dt.replace(month=7, day=1, hour=0, minute=0, second=0, microsecond=0)
