import json
from datetime import timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

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
                'event_id': event.id,
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
                'event_id': event.id,
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


@csrf_exempt
def legacy_events_endpoint(request):
    """
    Legacy endpoint for simple analytics events from Android AnalyticsLogger.
    Accepts: { "event_name": "...", "user_id": 123, "properties": {...} }
    Stores BQ4 events in MessagingResponseEvent model.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        event_name = data.get('event_name', 'unknown')
        user_id = data.get('user_id', 0)
        properties = data.get('properties', {})
        
        # Parse timestamp
        timestamp_str = properties.get('timestamp')
        if timestamp_str:
            try:
                timestamp = timezone.datetime.fromtimestamp(int(timestamp_str) / 1000, tz=timezone.utc)
            except:
                timestamp = timezone.now()
        else:
            timestamp = timezone.now()
        
        # Import the model here to avoid circular imports
        from marketplace_analytics.models import MessagingResponseEvent
        
        # Extract BQ4-specific fields
        seller_id = properties.get('seller_id')
        if seller_id:
            try:
                seller_id = int(seller_id)
            except:
                seller_id = None
        
        avg_minutes = properties.get('avg_minutes')
        if avg_minutes:
            try:
                avg_minutes = float(avg_minutes)
            except:
                avg_minutes = None
        
        unread_count = properties.get('unread_conversations')
        if unread_count:
            try:
                unread_count = int(unread_count)
            except:
                unread_count = None
        
        # Save to database
        MessagingResponseEvent.objects.create(
            event_name=event_name,
            user_id=user_id,
            seller_id=seller_id,
            avg_response_minutes=avg_minutes,
            unread_conversations=unread_count,
            timestamp=timestamp,
            properties=properties
        )
        
        return JsonResponse({
            'status': 'ok',
            'event_name': event_name,
            'user_id': user_id,
            'saved': True
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({'status': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'detail': str(e)}, status=500)


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


def bq4_dashboard(request):
    """
    Dashboard for BQ4: Average seller response time after buyer initiates contact.
    Shows messaging activity and seller responsiveness metrics.
    """
    from marketplace_analytics.models import MessagingResponseEvent
    from django.db.models import Avg, Count, Min, Max
    
    # Get time range (last 30 days by default)
    since = timezone.now() - timedelta(days=30)
    
    # Get all response time events
    response_events = MessagingResponseEvent.objects.filter(
        event_name='seller_avg_response_time',
        timestamp__gte=since,
        avg_response_minutes__isnull=False
    )
    
    # Overall statistics
    overall_stats = response_events.aggregate(
        avg_response=Avg('avg_response_minutes'),
        min_response=Min('avg_response_minutes'),
        max_response=Max('avg_response_minutes'),
        total_measurements=Count('id')
    )
    
    # Response time by seller
    by_seller = list(
        response_events.values('seller_id')
        .annotate(
            avg_response=Avg('avg_response_minutes'),
            measurements=Count('id')
        )
        .order_by('avg_response')[:10]  # Top 10 fastest sellers
    )
    
    # Messages screen activity
    messages_opened = MessagingResponseEvent.objects.filter(
        event_name='messages_screen_opened',
        timestamp__gte=since
    )
    
    total_opens = messages_opened.count()
    avg_unread = messages_opened.aggregate(avg=Avg('unread_conversations'))['avg'] or 0
    
    # Message sent activity
    messages_sent = MessagingResponseEvent.objects.filter(
        event_name='message_sent',
        timestamp__gte=since
    ).count()
    
    # Daily trend
    daily_response_times = list(
        response_events.annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(avg_response=Avg('avg_response_minutes'))
        .order_by('date')
    )
    
    # Response time distribution (buckets)
    fast_responses = response_events.filter(avg_response_minutes__lt=5).count()
    medium_responses = response_events.filter(avg_response_minutes__gte=5, avg_response_minutes__lt=30).count()
    slow_responses = response_events.filter(avg_response_minutes__gte=30).count()
    
    context = {
        'period_display': 'Last 30 Days',
        'total_measurements': overall_stats['total_measurements'] or 0,
        'avg_response_minutes': round(overall_stats['avg_response'] or 0, 1),
        'min_response_minutes': round(overall_stats['min_response'] or 0, 1),
        'max_response_minutes': round(overall_stats['max_response'] or 0, 1),
        
        'total_messages_opened': total_opens,
        'avg_unread_conversations': round(avg_unread, 1),
        'total_messages_sent': messages_sent,
        
        'seller_labels': [f"Seller {s['seller_id']}" for s in by_seller],
        'seller_response_times': [round(s['avg_response'], 1) for s in by_seller],
        'seller_measurements': [s['measurements'] for s in by_seller],
        
        'daily_labels': [d['date'].strftime('%b %d') for d in daily_response_times],
        'daily_values': [round(d['avg_response'], 1) for d in daily_response_times],
        
        'distribution_labels': ['< 5 min', '5-30 min', '> 30 min'],
        'distribution_values': [fast_responses, medium_responses, slow_responses],
    }
    
    return render(request, 'bq4_dashboard.html', context)
