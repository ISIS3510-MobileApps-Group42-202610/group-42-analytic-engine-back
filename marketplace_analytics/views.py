import json
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from marketplace_analytics.models import PerformanceEvent
from marketplace_analytics.serializers import AnalyticsEventIngestSerializer
from marketplace_analytics.services import (
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
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

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
    :param days:
    :return:
    """
    since = timezone.now() - timedelta(days=days)
    return (
        PerformanceEvent.objects
        .filter(timestamp__gte=since)
        .exclude(timestamp__week_day__in=[1, 7])  # No incluye sabados y domingos por obvias razones xd
        .filter(timestamp__hour__gte=8, timestamp__hour__lt=17)
    )


def bq1_dashboard(request):
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
        .values('device_model')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    # Lo mismo pero de navegacion
    nav_by_device = list(
        peak_events
        .filter(event_type='screen_navigation')
        .values('device_model')
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

    # resumen
    all_events = PerformanceEvent.objects.filter(timestamp__gte=since)
    total_events = all_events.count()
    peak_count = peak_events.count()
    device_count = peak_events.values('device_model').distinct().count()

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
        'startup_labels': json.dumps([d['device_model'] for d in startup_by_device]),
        'startup_values': json.dumps([round(d['avg_ms'], 1) for d in startup_by_device]),
        'startup_counts': json.dumps([d['count'] for d in startup_by_device]),
        'nav_labels': json.dumps([d['device_model'] for d in nav_by_device]),
        'nav_values': json.dumps([round(d['avg_ms'], 1) for d in nav_by_device]),
        'nav_counts': json.dumps([d['count'] for d in nav_by_device]),
        'daily_startup_labels': json.dumps([d['date'].strftime('%b %d') for d in daily_startup]),
        'daily_startup_values': json.dumps([round(d['avg_ms'], 1) for d in daily_startup]),
        'daily_nav_labels': json.dumps([d['date'].strftime('%b %d') for d in daily_nav]),
        'daily_nav_values': json.dumps([round(d['avg_ms'], 1) for d in daily_nav]),
        'total_events': total_events,
        'peak_count': peak_count,
        'device_count': device_count,
        'overall_startup': round(overall_startup, 1),
        'overall_nav': round(overall_nav, 1),
    }

    # se renderiza con las graficas y eso bonito para el analytics persona
    return render(request, 'bq1_dashboard.html', context)


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
        .values('device_model')
        .annotate(avg_ms=Avg('duration_ms'), count=Count('id'))
        .order_by('avg_ms')
    )

    nav_by_device = list(
        peak_events
        .filter(event_type='screen_navigation')
        .values('device_model')
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
        'peak_hours': 'Weekdays 8AM-5PM', # Esto puede cambiar, depende de lo que digan las estadisticas xd
        'period': 'Last 10 days',
        'overall_avg_startup_ms': round(overall_startup, 1),
        'overall_avg_navigation_ms': round(overall_nav, 1),
        'startup_by_device': [
            {'device_model': d['device_model'], 'avg_ms': round(d['avg_ms'], 1), 'count': d['count']}
            for d in startup_by_device
        ],
        'navigation_by_device': [
            {'device_model': d['device_model'], 'avg_ms': round(d['avg_ms'], 1), 'count': d['count']}
            for d in nav_by_device
        ],
    }
    return JsonResponse(data)


def q9_dashboard(request):
    """
    Dashboard view for Q9 messaging impact metric with date filters.
    """
    period, start, end = _extract_period_params(request)
    since, until, resolved_period = resolve_reporting_window(period=period, start=start, end=end)

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


class BusinessEventIngestionAPIView(APIView):
    """
    Ingest business-relevant analytics events from Android/iOS clients.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = AnalyticsEventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event = ingest_business_event(serializer.validated_data)

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

        since, until, resolved_period = resolve_reporting_window(period=period, start=start, end=end)

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
        raise ValidationError('period must be one of: all_time, last_30_days, semester_to_date, custom')

    start = None
    end = None
    if period == 'custom':
        start_raw = params.get('start')
        end_raw = params.get('end')

        if not start_raw or not end_raw:
            raise ValidationError('custom period requires start and end query params in ISO-8601 format.')

        start = parse_datetime(start_raw)
        end = parse_datetime(end_raw)

        if not start or not end:
            raise ValidationError('Invalid start/end datetime format. Use ISO-8601.')

        if timezone.is_naive(start):
            start = timezone.make_aware(start, timezone=dt_timezone.utc)
        if timezone.is_naive(end):
            end = timezone.make_aware(end, timezone=dt_timezone.utc)

        if start > end:
            raise ValidationError('start must be earlier than or equal to end.')

    return period, start, end
