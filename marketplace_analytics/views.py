import json
from datetime import timedelta

from django.db.models import Avg, Count
from django.db.models.functions import TruncDate, ExtractHour, ExtractWeekDay
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from marketplace_analytics.models import PerformanceEvent


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
