import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from datetime import timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import OperationalError, InterfaceError
from django.db.models import Avg, Count, Case, When, Value, CharField, F
from django.db.models.functions import TruncDate, ExtractHour, ExtractWeekDay
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from marketplace_analytics.authentication import (
    JWTIngestionAuthentication,
    ApiKeyAuthentication,
    StaticTokenAuthentication,
)
from marketplace_analytics.models import PerformanceEvent
from marketplace_analytics.serializers import (
    AnalyticsEventIngestSerializer,
    SearchDiscoveryEventIngestSerializer,
)
from marketplace_analytics.services import (
    ingest_search_discovery_event,
    calculate_bq3_search_to_interaction_metric,
    ingest_business_event,
    calculate_q9_messaging_impact_metric_with_filters,
    resolve_reporting_window,
)


@csrf_exempt
def post_performance_event(request):
    """
    Post un evento de performance para el analytics engine
    :param request: Debe ser un POST con JSON body que contenga:
    {
    "event_type": "app_startup" o "screen_navigation",
    "device_model": "iPhone 15",
    "platform": "ios" o "android",
    "duration_ms": 123.45,
    "os_version": "17.3" o "14" (opcional),
    "app_version": "1.2.3" (opcional)
    }
    :return: JSON con status del resultado
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'Invalid JSON'}, status=400)

    PerformanceEvent.objects.create(
        event_type=data['event_type'],  # "app_startup" or "screen_navigation"
        device_model=data['device_model'],
        platform=data['platform'],  # "ios" or "android"
        duration_ms=data['duration_ms'],  # tiempo en ms
        timestamp=timezone.now(),
        os_version=data.get('os_version', ''),
        app_version=data.get('app_version', ''),
    )
    return JsonResponse({'status': 'ok'}, status=201)


def get_peak_events(days=10):
    """
    Lógica para sacar los eventos en los últimos X días durante las horas pico (8am-5pm, lunes a viernes)
    Usa la zona horaria de Bogotá (UTC-5)
    :param days:
    :return:
    """
    since = timezone.now() - timedelta(days=days)
    bogota_tz = ZoneInfo('America/Bogota')
    
    return (
        PerformanceEvent.objects
        .filter(timestamp__gte=since)
        .annotate(
            hour_bogota=ExtractHour('timestamp', tzinfo=bogota_tz),
            weekday_bogota=ExtractWeekDay('timestamp', tzinfo=bogota_tz),
            device_model_display=Case(
                When(device_model__isnull=True, then=Value("Other (Chrome, Desktop)")),
                When(device_model__exact='', then=Value("Other (Chrome, Desktop)")),
                default=F('device_model'),
                output_field=CharField()
            )
        )
        # No incluye sabados y domingos por obvias razones xd (1=Sunday, 7=Saturday en Django)
        .exclude(weekday_bogota__in=[1, 7])
        # 8am-5pm Bogotá time
        .filter(hour_bogota__gte=8, hour_bogota__lt=17)
    )


def bq2_dashboard(request):
    """
    El view principal del dashboard para la BQ1
    :param request: un request HTTP
    :return: renderiza
    """
    since = timezone.now() - timedelta(days=10)
    peak_events = get_peak_events(days=10)

    # Tiempo promedio de startup en ms, durante las peak hours
    startup_by_device = list(
        peak_events
        .filter(event_type='app_startup')
        .values('device_model_display')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    # Lo mismo pero de navegacion
    nav_by_device = list(
        peak_events
        .filter(event_type='screen_navigation')
        .values('device_model_display')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    # El trend diario de startup
    daily_startup = list(
        peak_events
        .filter(event_type='app_startup')
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(avg_ms=Avg('duration_ms'))
        .order_by('date')
    )

    # El trend diario de navegacion
    daily_nav = list(
        peak_events
        .filter(event_type='screen_navigation')
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(avg_ms=Avg('duration_ms'))
        .order_by('date')
    )

    # ====== Queries para TODOS los eventos (sin filtro de peak hours) ======
    all_events = PerformanceEvent.objects.filter(timestamp__gte=since).annotate(
        device_model_display=Case(
            When(device_model__isnull=True, then=Value("Other (Chrome, Desktop)")),
            When(device_model__exact='', then=Value("Other (Chrome, Desktop)")),
            default=F('device_model'),
            output_field=CharField()
        )
    )

    all_startup_by_device = list(
        all_events
        .filter(event_type='app_startup')
        .values('device_model_display')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    all_nav_by_device = list(
        all_events
        .filter(event_type='screen_navigation')
        .values('device_model_display')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    all_daily_startup = list(
        all_events
        .filter(event_type='app_startup')
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(avg_ms=Avg('duration_ms'))
        .order_by('date')
    )

    all_daily_nav = list(
        all_events
        .filter(event_type='screen_navigation')
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(avg_ms=Avg('duration_ms'))
        .order_by('date')
    )

    all_overall_startup = (
        all_events.filter(event_type='app_startup')
        .aggregate(avg=Avg('duration_ms'))['avg'] or 0
    )
    all_overall_nav = (
        all_events.filter(event_type='screen_navigation')
        .aggregate(avg=Avg('duration_ms'))['avg'] or 0
    )

    # resumen
    total_events = all_events.count()
    peak_count = peak_events.count()
    device_count = peak_events.values('device_model_display').distinct().count()
    all_device_count = all_events.values('device_model_display').distinct().count()

    overall_startup = (
        peak_events.filter(event_type='app_startup')
        .aggregate(avg=Avg('duration_ms'))['avg'] or 0
    )
    overall_nav = (
        peak_events.filter(event_type='screen_navigation')
        .aggregate(avg=Avg('duration_ms'))['avg'] or 0
    )

    # todas las "variables" del contexto pueden ser directamente accedidas por el HTML c:
    context = {
        # Peak hours
        'startup_labels': json.dumps([d['device_model_display'] for d in startup_by_device]),
        'startup_values': json.dumps([round(d['avg_ms'], 1) for d in startup_by_device]),
        'startup_counts': json.dumps([d['count'] for d in startup_by_device]),
        'nav_labels': json.dumps([d['device_model_display'] for d in nav_by_device]),
        'nav_values': json.dumps([round(d['avg_ms'], 1) for d in nav_by_device]),
        'nav_counts': json.dumps([d['count'] for d in nav_by_device]),
        'daily_startup_labels': json.dumps([d['date'].strftime('%b %d') for d in daily_startup]),
        'daily_startup_values': json.dumps([round(d['avg_ms'], 1) for d in daily_startup]),
        'daily_nav_labels': json.dumps([d['date'].strftime('%b %d') for d in daily_nav]),
        'daily_nav_values': json.dumps([round(d['avg_ms'], 1) for d in daily_nav]),
        # All hours
        'all_startup_labels': json.dumps([d['device_model_display'] for d in all_startup_by_device]),
        'all_startup_values': json.dumps([round(d['avg_ms'], 1) for d in all_startup_by_device]),
        'all_nav_labels': json.dumps([d['device_model_display'] for d in all_nav_by_device]),
        'all_nav_values': json.dumps([round(d['avg_ms'], 1) for d in all_nav_by_device]),
        'all_daily_startup_labels': json.dumps([d['date'].strftime('%b %d') for d in all_daily_startup]),
        'all_daily_startup_values': json.dumps([round(d['avg_ms'], 1) for d in all_daily_startup]),
        'all_daily_nav_labels': json.dumps([d['date'].strftime('%b %d') for d in all_daily_nav]),
        'all_daily_nav_values': json.dumps([round(d['avg_ms'], 1) for d in all_daily_nav]),
        # Summary
        'total_events': total_events,
        'peak_count': peak_count,
        'device_count': device_count,
        'all_device_count': all_device_count,
        'overall_startup': round(overall_startup, 1),
        'overall_nav': round(overall_nav, 1),
        'all_overall_startup': round(all_overall_startup, 1),
        'all_overall_nav': round(all_overall_nav, 1),
    }

    # se renderiza con las graficas y eso bonito para el analytics persona
    return render(request, 'bq2_dashboard.html', context)


def performance_summary_api(request):
    """
    Esto genera un resumen de la info de la BQ1
    :param request: un request HTTP
    :return: El resumen de la BQ1 en formato JSON
    """
    peak_events = get_peak_events(days=10)

    startup_by_device = list(
        peak_events
        .filter(event_type='app_startup')
        .values('device_model_display')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    nav_by_device = list(
        peak_events
        .filter(event_type='screen_navigation')
        .values('device_model_display')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    overall_startup = (
        peak_events.filter(event_type='app_startup')
        .aggregate(avg=Avg('duration_ms'))['avg'] or 0
    )
    overall_nav = (
        peak_events.filter(event_type='screen_navigation')
        .aggregate(avg=Avg('duration_ms'))['avg'] or 0
    )

    data = {
        # Esto puede cambiar, depende de lo que digan las estadisticas xd
        'peak_hours': 'Weekdays 8AM-5PM',
        'period': 'Last 10 days',
        'overall_avg_startup_ms': round(overall_startup, 1),
        'overall_avg_navigation_ms': round(overall_nav, 1),
        'startup_by_device': [
            {'device_model': d['device_model_display'], 'avg_ms': round(
                d['avg_ms'], 1), 'count': d['count']}
            for d in startup_by_device
        ],
        'navigation_by_device': [
            {'device_model': d['device_model_display'], 'avg_ms': round(
                d['avg_ms'], 1), 'count': d['count']}
            for d in nav_by_device
        ],
    }
    return JsonResponse(data)


def q9_dashboard(request):
    """
    Dashboard view for Q9 messaging impact metric with date filters.
    """
    period, start, end = _extract_period_params(request)
    since, until, resolved_period = resolve_reporting_window(
        period=period, start=start, end=end)

    report = calculate_q9_messaging_impact_metric_with_filters(
        since=since,
        until=until,
        period_label=resolved_period,
    )

    with_group = report['group_with_messaging']
    without_group = report['group_without_messaging']

    with_rate = with_group['completion_rate'] if with_group['completion_rate'] is not None else 0
    without_rate = without_group['completion_rate'] if without_group['completion_rate'] is not None else 0
    absolute_difference = report['absolute_difference'] if report['absolute_difference'] is not None else 0
    relative_lift = report['relative_lift_percentage'] if report['relative_lift_percentage'] is not None else 0

    period_label_map = {
        'all_time': 'All Time',
        'last_30_days': 'Last 30 Days',
        'semester_to_date': 'Semester to Date',
        'custom': 'Custom Range',
    }

    context = {
        'selected_period': resolved_period,
        'period_display': period_label_map.get(resolved_period, resolved_period),
        'custom_start': start.isoformat().replace('+00:00', 'Z') if start else '',
        'custom_end': end.isoformat().replace('+00:00', 'Z') if end else '',
        'with_listings': with_group['listings'],
        'without_listings': without_group['listings'],
        'with_completed': with_group['completed'],
        'without_completed': without_group['completed'],
        'with_rate_pct': round(with_rate * 100, 2),
        'without_rate_pct': round(without_rate * 100, 2),
        'absolute_difference_pct': round(absolute_difference * 100, 2),
        'relative_lift_pct': round(relative_lift, 2),
        'completion_labels': ['With Messaging', 'Without Messaging'],
        'completion_rates': [round(with_rate * 100, 2), round(without_rate * 100, 2)],
    }
    return render(request, 'bq9_dashboard.html', context)


def bq11_dashboard(request):
    """
    Dashboard for BQ11: which product categories and brands have the highest
    transaction volume per academic semester.
    """
    from marketplace_analytics.models import AnalyticsEvent

    events_qs = AnalyticsEvent.objects.filter(
        event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
        metadata__category__isnull=False,
    ).exclude(metadata__category='unknown')

    all_events_list = list(events_qs.values('metadata', 'occurred_at'))

    category_counts = {}
    category_revenue = {}
    semester_category = {}
    product_counts = {}

    for e in all_events_list:
        meta = e.get('metadata') or {}
        category = meta.get('category', 'unknown')
        product = meta.get('product', 'unknown')
        price = meta.get('selling_price', 0) or 0
        occurred = e.get('occurred_at')

        semester = meta.get('semester')
        if not semester and occurred:
            year = occurred.year
            half = 'A' if occurred.month <= 6 else 'B'
            semester = f'{year}-{half}'

        category_counts[category] = category_counts.get(category, 0) + 1
        category_revenue[category] = category_revenue.get(
            category, 0) + float(price)
        product_counts[product] = product_counts.get(product, 0) + 1

        if semester not in semester_category:
            semester_category[semester] = {}
        semester_category[semester][category] = semester_category[semester].get(
            category, 0) + 1

    sorted_categories = sorted(category_counts.items(), key=lambda x: -x[1])
    top_categories = sorted_categories[:10]

    sorted_products = sorted(product_counts.items(), key=lambda x: -x[1])
    top_products = sorted_products[:10]

    sorted_semesters = sorted(semester_category.keys())

    all_categories = [c for c, _ in top_categories]
    semester_datasets = {}
    for cat in all_categories:
        semester_datasets[cat] = [
            semester_category.get(sem, {}).get(cat, 0)
            for sem in sorted_semesters
        ]

    total_transactions = sum(category_counts.values())
    total_revenue = sum(category_revenue.values())

    context = {
        'total_transactions': total_transactions,
        'total_revenue': round(total_revenue, 2),
        'unique_categories': len(category_counts),
        'unique_products': len(product_counts),
        'category_labels':  [c for c, _ in top_categories],
        'category_counts':  [n for _, n in top_categories],
        'category_revenue': [round(category_revenue.get(c, 0), 2) for c, _ in top_categories],
        'product_labels':   [p for p, _ in top_products],
        'product_counts':   [n for _, n in top_products],
        'semester_labels':  sorted_semesters,
        'semester_datasets': [
            {'label': cat, 'data': semester_datasets[cat]}
            for cat in all_categories
        ],
    }

    return render(request, 'bq11_dashboard.html', context)


def bq12_dashboard(request):
    """
    Dashboard for BQ12 seasonal demand patterns.
    Consumes aggregated analytics from the general backend endpoint.
    """
    grain = (request.GET.get('grain') or 'month').strip()
    date_from = (request.GET.get('from') or '2026-01-01').strip()
    date_to = (request.GET.get('to') or '2026-12-31').strip()
    university_code = (request.GET.get('university_code') or 'UNIANDES').strip().upper()

    base_url = getattr(
        settings,
        'SEASONAL_DEMAND_API_BASE_URL',
        'https://group-42-backend.vercel.app',
    ).rstrip('/')

    query = urlencode({
        'grain': grain,
        'from': date_from,
        'to': date_to,
        'university_code': university_code,
    })
    endpoint_url = f'{base_url}/api/v1/listings/analytics/seasonal-demand?{query}'

    rows = []
    error_message = ''

    try:
        with urlopen(endpoint_url, timeout=12) as response:
            payload = json.loads(response.read().decode('utf-8'))
            rows = payload.get('data') or []
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        error_message = f'Could not load BQ12 data from backend: {exc}'

    period_set = sorted({row.get('period_start') for row in rows if row.get('period_start')})
    faculty_set = sorted({row.get('faculty') or 'Unknown' for row in rows})
    phase_totals = {}

    # Build a period x faculty matrix for listings_created.
    listings_matrix = {faculty: {period: 0 for period in period_set} for faculty in faculty_set}

    total_listings = 0
    total_transactions = 0

    for row in rows:
        period = row.get('period_start')
        faculty = row.get('faculty') or 'Unknown'
        phase = row.get('calendar_phase') or 'unknown'

        listings_created = int(row.get('listings_created') or 0)
        transactions_completed = int(row.get('transactions_completed') or 0)

        total_listings += listings_created
        total_transactions += transactions_completed

        if period in listings_matrix.get(faculty, {}):
            listings_matrix[faculty][period] += listings_created

        if phase not in phase_totals:
            phase_totals[phase] = {'listings': 0, 'transactions': 0}
        phase_totals[phase]['listings'] += listings_created
        phase_totals[phase]['transactions'] += transactions_completed

    faculty_datasets = []
    for faculty in faculty_set:
        faculty_datasets.append({
            'label': faculty,
            'data': [listings_matrix[faculty][period] for period in period_set],
        })

    phase_labels = sorted(phase_totals.keys())
    phase_conversion_rates = []
    for phase in phase_labels:
        listings_count = phase_totals[phase]['listings']
        transactions_count = phase_totals[phase]['transactions']
        rate = (transactions_count / listings_count) if listings_count else 0
        phase_conversion_rates.append(round(rate * 100, 2))

    overall_conversion_rate = (total_transactions / total_listings) if total_listings else 0

    context = {
        'selected_grain': grain,
        'selected_from': date_from,
        'selected_to': date_to,
        'selected_university_code': university_code,
        'error_message': error_message,
        'total_rows': len(rows),
        'total_listings': total_listings,
        'total_transactions': total_transactions,
        'overall_conversion_rate': round(overall_conversion_rate * 100, 2),
        'period_labels': period_set,
        'faculty_datasets': faculty_datasets,
        'phase_labels': phase_labels,
        'phase_conversion_rates': phase_conversion_rates,
        'rows': rows,
    }

    return render(request, 'bq12_dashboard.html', context)


class BusinessEventIngestionAPIView(APIView):
    """
    Ingest business-relevant analytics events from Android/iOS clients.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = AnalyticsEventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            event = ingest_business_event(serializer.validated_data)
        except (OperationalError, InterfaceError):
            return Response(
                {
                    'status': 'error',
                    'detail': 'Temporary database connectivity issue. Retry in a few seconds.',
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                'status': 'ok',
                'event_id': event.pk,
                'event_name': event.event_name,
                'listing_id': event.listing_id,
            },
            status=status.HTTP_201_CREATED,
        )


class Q9MessagingImpactAPIView(APIView):
    """
    Return the Q9 metric: messaging impact on transaction completion.
    """

    def get(self, request):
        period, start, end = _extract_period_params(request)

        since, until, resolved_period = resolve_reporting_window(
            period=period, start=start, end=end)

        data = calculate_q9_messaging_impact_metric_with_filters(
            since=since,
            until=until,
            period_label=resolved_period,
        )
        return Response(data, status=status.HTTP_200_OK)


def _extract_period_params(request):
    params = getattr(request, 'query_params', request.GET)

    period = (params.get('period') or 'all_time').strip()

    if period not in {'all_time', 'last_30_days', 'semester_to_date', 'custom'}:
        raise ValidationError(
            'period must be one of: all_time, last_30_days, semester_to_date, custom')

    start = None
    end = None
    if period == 'custom':
        start_raw = params.get('start')
        end_raw = params.get('end')

        if not start_raw or not end_raw:
            raise ValidationError(
                'custom period requires start and end query params in ISO-8601 format.')

        start = parse_datetime(start_raw)
        end = parse_datetime(end_raw)

        if not start or not end:
            raise ValidationError(
                'Invalid start/end datetime format. Use ISO-8601.')

        if timezone.is_naive(start):
            start = timezone.make_aware(start, timezone=dt_timezone.utc)
        if timezone.is_naive(end):
            end = timezone.make_aware(end, timezone=dt_timezone.utc)

        if start > end:
            raise ValidationError(
                'start must be earlier than or equal to end.')

    return period, start, end


class BQ3SearchDiscoveryEventIngestionAPIView(APIView):
    authentication_classes = (
        JWTIngestionAuthentication,
        ApiKeyAuthentication,
        StaticTokenAuthentication,
    )
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = SearchDiscoveryEventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = ingest_search_discovery_event(serializer.validated_data)

        return Response(
            {
                'status': 'ok',
                'event_id': event.pk,
                'session_id': event.session_id,
                'event_name': event.event_name,
                'occurred_at': event.occurred_at,
            },
            status=status.HTTP_201_CREATED,
        )


class BQ3SearchToInteractionAPIView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        period = request.GET.get('period', 'all_time')
        start_raw = request.GET.get('start')
        end_raw = request.GET.get('end')

        start = parse_datetime(start_raw) if start_raw else None
        end = parse_datetime(end_raw) if end_raw else None

        if start_raw and start is None:
            raise ValidationError({'start': 'Invalid ISO datetime.'})
        if end_raw and end is None:
            raise ValidationError({'end': 'Invalid ISO datetime.'})

        if start and timezone.is_naive(start):
            start = timezone.make_aware(start, dt_timezone.utc)

        if end and timezone.is_naive(end):
            end = timezone.make_aware(end, dt_timezone.utc)

        since, until, label = resolve_reporting_window(period, start, end)

        report = calculate_bq3_search_to_interaction_metric(
            since=since,
            until=until,
            period_label=label,
        )
        return Response(report, status=status.HTTP_200_OK)


def bq3_dashboard(request):
    period = request.GET.get('period', 'all_time')
    start_raw = request.GET.get('start')
    end_raw = request.GET.get('end')

    start = parse_datetime(start_raw) if start_raw else None
    end = parse_datetime(end_raw) if end_raw else None

    if start_raw and start is None:
        raise ValidationError({'start': 'Invalid ISO datetime.'})
    if end_raw and end is None:
        raise ValidationError({'end': 'Invalid ISO datetime.'})

    if start and timezone.is_naive(start):
        start = timezone.make_aware(start, dt_timezone.utc)

    if end and timezone.is_naive(end):
        end = timezone.make_aware(end, dt_timezone.utc)

    since, until, label = resolve_reporting_window(period, start, end)

    report = calculate_bq3_search_to_interaction_metric(
        since=since,
        until=until,
        period_label=label,
    )

    by_filter_type = report.get('by_filter_type', {})
    distribution = report.get('distribution_buckets', {})
    by_interaction_type = report.get('by_interaction_type', {})

    context = {
        'selected_period': period,
        'custom_start': start_raw or '',
        'custom_end': end_raw or '',
        'period_display': label,

        'search_sessions_started': report.get('search_sessions_started', 0),
        'search_sessions_with_meaningful_interaction': report.get('search_sessions_with_meaningful_interaction', 0),
        'interaction_rate': round((report.get('interaction_rate') or 0) * 100, 1),
        'avg_seconds_to_first_interaction': round(report.get('avg_seconds_to_first_interaction') or 0, 1),
        'median_seconds_to_first_interaction': round(report.get('median_seconds_to_first_interaction') or 0, 1),
        'p90_seconds_to_first_interaction': round(report.get('p90_seconds_to_first_interaction') or 0, 1),

        'filter_labels': list(by_filter_type.keys()),
        'filter_rates': [
            round((item.get('interaction_rate') or 0) * 100, 1)
            for item in by_filter_type.values()
        ],
        'filter_avg_times': [
            round(item.get('avg_seconds_to_interaction') or 0, 1)
            for item in by_filter_type.values()
        ],

        'distribution_labels': list(distribution.keys()),
        'distribution_values': list(distribution.values()),

        'interaction_type_labels': list(by_interaction_type.keys()),
        'interaction_type_values': list(by_interaction_type.values()),

        'sample_completed_sessions': report.get('sample_completed_sessions', []),
    }

    return render(request, 'bq3_dashboard.html', context)
