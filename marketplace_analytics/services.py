from datetime import datetime

from django.db import transaction
from django.db.models import QuerySet
from django.db.models import Avg
from django.db.models import Count
from django.db.models import Min
from django.db.models import Max
from django.db.models.functions import TruncDate
from django.utils import timezone
from collections import defaultdict
from statistics import median

from marketplace_analytics.models import AnalyticsEvent, ListingAnalyticsState, SearchDiscoveryEvent, MessagingResponseEvent


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

BQ3_START_EVENTS = {
    SearchDiscoveryEvent.EventName.SEARCH_STARTED,
    SearchDiscoveryEvent.EventName.FILTER_APPLIED,
}

BQ3_INTERACTION_EVENTS = {
    SearchDiscoveryEvent.EventName.LISTING_OPENED,
    SearchDiscoveryEvent.EventName.MESSAGE_SENT,
    SearchDiscoveryEvent.EventName.RESERVATION_CREATED,
}


def ingest_search_discovery_event(validated_event_data):
    return SearchDiscoveryEvent.objects.create(**validated_event_data)


def calculate_bq3_search_to_interaction_metric(
    since: datetime | None = None,
    until: datetime | None = None,
    period_label: str = 'all_time',
):
    events = SearchDiscoveryEvent.objects.all()

    if since is not None:
        events = events.filter(occurred_at__gte=since)
    if until is not None:
        events = events.filter(occurred_at__lte=until)

    events = events.order_by('session_id', 'occurred_at', 'id')

    sessions = {}

    for event in events.iterator():
        session = sessions.setdefault(
            event.session_id,
            {
                'session_id': event.session_id,
                'user_id': event.user_id,
                'first_action_at': None,
                'first_action_name': None,
                'first_interaction_at': None,
                'first_interaction_name': None,
                'selected_filter_type': SearchDiscoveryEvent.FilterType.NONE,
                'selected_course_id': None,
                'selected_course_name': None,
                'selected_category_id': None,
                'selected_category_name': None,
                'search_query': None,
            }
        )

        if event.event_name in BQ3_START_EVENTS and session['first_action_at'] is None:
            session['first_action_at'] = event.occurred_at
            session['first_action_name'] = event.event_name
            session['selected_filter_type'] = _resolve_filter_type(event)
            session['selected_course_id'] = event.selected_course_id
            session['selected_course_name'] = event.selected_course_name
            session['selected_category_id'] = event.selected_category_id
            session['selected_category_name'] = event.selected_category_name
            session['search_query'] = event.search_query

        if (
            event.event_name in BQ3_INTERACTION_EVENTS
            and session['first_action_at'] is not None
            and event.occurred_at >= session['first_action_at']
            and session['first_interaction_at'] is None
        ):
            session['first_interaction_at'] = event.occurred_at
            session['first_interaction_name'] = event.event_name

    started_sessions = [
        s for s in sessions.values()
        if s['first_action_at'] is not None
    ]

    completed_sessions = []
    elapsed_seconds = []

    breakdown = defaultdict(lambda: {
        'sessions_started': 0,
        'sessions_with_interaction': 0,
        'avg_seconds_to_interaction': None,
        'median_seconds_to_interaction': None,
    })

    interaction_breakdown = defaultdict(int)

    for session in started_sessions:
        filter_key = session['selected_filter_type'] or SearchDiscoveryEvent.FilterType.NONE
        breakdown[filter_key]['sessions_started'] += 1

        if session['first_interaction_at'] is not None:
            delta_seconds = (
                session['first_interaction_at'] - session['first_action_at']
            ).total_seconds()

            completed_sessions.append({
                **session,
                'seconds_to_first_interaction': delta_seconds,
            })
            elapsed_seconds.append(delta_seconds)

            breakdown[filter_key]['sessions_with_interaction'] += 1
            interaction_breakdown[session['first_interaction_name']] += 1

    for filter_key, data in breakdown.items():
        filter_elapsed = [
            s['seconds_to_first_interaction']
            for s in completed_sessions
            if (s['selected_filter_type'] or SearchDiscoveryEvent.FilterType.NONE) == filter_key
        ]
        data['avg_seconds_to_interaction'] = _safe_avg(filter_elapsed)
        data['median_seconds_to_interaction'] = _safe_median(filter_elapsed)
        data['interaction_rate'] = (
            data['sessions_with_interaction'] / data['sessions_started']
            if data['sessions_started'] else None
        )

    return {
        'period': {
            'label': period_label,
            'since': since,
            'until': until,
        },
        'metric_definition': (
            'Time elapsed between the first search/filter event and the first '
            'meaningful interaction in the same session.'
        ),
        'meaningful_interactions': [
            SearchDiscoveryEvent.EventName.LISTING_OPENED,
            SearchDiscoveryEvent.EventName.MESSAGE_SENT,
            SearchDiscoveryEvent.EventName.RESERVATION_CREATED,
        ],
        'search_sessions_started': len(started_sessions),
        'search_sessions_with_meaningful_interaction': len(completed_sessions),
        'interaction_rate': (
            len(completed_sessions) / len(started_sessions)
            if started_sessions else None
        ),
        'avg_seconds_to_first_interaction': _safe_avg(elapsed_seconds),
        'median_seconds_to_first_interaction': _safe_median(elapsed_seconds),
        'p90_seconds_to_first_interaction': _percentile(elapsed_seconds, 90),
        'distribution_buckets': _build_distribution_buckets(elapsed_seconds),
        'by_filter_type': breakdown,
        'by_interaction_type': dict(interaction_breakdown),
        'sample_completed_sessions': completed_sessions[:20],
    }

def ingest_messaging_response_event(validated_event_data):
    return MessagingResponseEvent.objects.create(**validated_event_data)


def calculate_bq6_seller_response_time_metric(
    since: datetime | None = None,
    until: datetime | None = None,
    period_label: str = 'all_time',
):
    base_qs = MessagingResponseEvent.objects.all()

    if since is not None:
        base_qs = base_qs.filter(timestamp__gte=since)
    if until is not None:
        base_qs = base_qs.filter(timestamp__lte=until)

    response_events = base_qs.filter(
        event_name=MessagingResponseEvent.EventName.SELLER_AVG_RESPONSE_TIME,
        avg_response_minutes__isnull=False,
        seller_id__isnull=False,
    )

    overall_stats = response_events.aggregate(
        avg_response=Avg('avg_response_minutes'),
        min_response=Min('avg_response_minutes'),
        max_response=Max('avg_response_minutes'),
        total_measurements=Count('id'),
    )

    seller_breakdown_qs = (
        response_events
        .values('seller_id')
        .annotate(
            avg_response_minutes=Avg('avg_response_minutes'),
            measurements=Count('id'),
        )
        .order_by('avg_response_minutes', '-measurements')
    )

    top_fastest_sellers = list(seller_breakdown_qs[:10])
    slowest_sellers = list(seller_breakdown_qs.order_by('-avg_response_minutes', '-measurements')[:10])

    daily_trend = list(
        response_events
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(
            avg_response_minutes=Avg('avg_response_minutes'),
            measurements=Count('id'),
        )
        .order_by('date')
    )

    screen_opened_count = base_qs.filter(
        event_name=MessagingResponseEvent.EventName.MESSAGES_SCREEN_OPENED
    ).count()

    message_sent_count = base_qs.filter(
        event_name__in=[
            MessagingResponseEvent.EventName.MESSAGE_SENT,
            MessagingResponseEvent.EventName.FIRST_MESSAGE_SENT,
        ]
    ).count()

    avg_unread_conversations = (
        base_qs.filter(
            event_name=MessagingResponseEvent.EventName.MESSAGES_SCREEN_OPENED,
            unread_conversations__isnull=False,
        ).aggregate(avg=Avg('unread_conversations'))['avg']
        or 0
    )

    values = list(
        response_events.values_list('avg_response_minutes', flat=True)
    )

    distribution_buckets = {
        'under_5_min': response_events.filter(avg_response_minutes__lt=5).count(),
        'from_5_to_30_min': response_events.filter(avg_response_minutes__gte=5, avg_response_minutes__lt=30).count(),
        'from_30_to_120_min': response_events.filter(avg_response_minutes__gte=30, avg_response_minutes__lt=120).count(),
        'over_120_min': response_events.filter(avg_response_minutes__gte=120).count(),
    }

    return {
        'period': {
            'label': period_label,
            'since': since,
            'until': until,
        },
        'metric_definition': (
            'Average seller response time, in minutes, after a buyer initiates contact.'
        ),
        'total_measurements': overall_stats['total_measurements'] or 0,
        'avg_response_minutes': overall_stats['avg_response'],
        'median_response_minutes': _safe_median(values),
        'p90_response_minutes': _percentile(values, 90),
        'min_response_minutes': overall_stats['min_response'],
        'max_response_minutes': overall_stats['max_response'],
        'messages_screen_opened': screen_opened_count,
        'messages_sent': message_sent_count,
        'avg_unread_conversations': avg_unread_conversations,
        'distribution_buckets': distribution_buckets,
        'top_fastest_sellers': top_fastest_sellers,
        'slowest_sellers': slowest_sellers,
        'daily_trend': daily_trend,
    }


def _resolve_filter_type(event: SearchDiscoveryEvent) -> str:
    if event.selected_filter_type and event.selected_filter_type != SearchDiscoveryEvent.FilterType.NONE:
        return event.selected_filter_type

    has_course = bool(event.selected_course_id)
    has_category = bool(event.selected_category_id)

    if has_course and has_category:
        return SearchDiscoveryEvent.FilterType.BOTH
    if has_course:
        return SearchDiscoveryEvent.FilterType.COURSE
    if has_category:
        return SearchDiscoveryEvent.FilterType.CATEGORY
    return SearchDiscoveryEvent.FilterType.NONE


def _safe_avg(values):
    if not values:
        return None
    return sum(values) / len(values)


def _safe_median(values):
    if not values:
        return None
    return median(values)


def _percentile(values, percentile_rank):
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    k = (len(ordered) - 1) * (percentile_rank / 100)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = k - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _build_distribution_buckets(values):
    buckets = {
        '0-10s': 0,
        '10-30s': 0,
        '30-60s': 0,
        '60-180s': 0,
        '180s+': 0,
    }

    for value in values:
        if value < 10:
            buckets['0-10s'] += 1
        elif value < 30:
            buckets['10-30s'] += 1
        elif value < 60:
            buckets['30-60s'] += 1
        elif value < 180:
            buckets['60-180s'] += 1
        else:
            buckets['180s+'] += 1

    return buckets