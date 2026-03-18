import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from marketplace_analytics.models import PerformanceEvent

DEVICE_MODELS = {
    'android': [
        'Samsung Galaxy S23',
        'Samsung Galaxy A54',
        'Google Pixel 8',
        'Xiaomi 13',
        'OnePlus 11',
    ],
    'ios': [
        'iPhone 15',
        'iPhone 14',
        'iPhone 13',
        'iPad Air 5',
    ],
}

APP_VERSIONS = ['1.0.0', '1.1.0', '1.2.0', '1.2.1']

OS_VERSIONS = {
    'android': ['12', '13', '14', '15'],
    'ios': ['16.6', '17.0', '17.2', '17.4', '18.0'],
}

# Startup time ranges per device tier (ms)
STARTUP_RANGES = {
    'iPhone 15': (180, 600),
    'iPhone 14': (200, 700),
    'iPhone 13': (220, 800),
    'iPad Air 5': (170, 550),
    'Google Pixel 8': (200, 700),
    'Samsung Galaxy S23': (250, 800),
    'Samsung Galaxy A54': (400, 1400),
    'Xiaomi 13': (300, 1000),
    'OnePlus 11': (250, 850),
}

NAV_RANGES = {
    'iPhone 15': (40, 250),
    'iPhone 14': (50, 300),
    'iPhone 13': (55, 350),
    'iPad Air 5': (35, 220),
    'Google Pixel 8': (50, 300),
    'Samsung Galaxy S23': (60, 350),
    'Samsung Galaxy A54': (100, 550),
    'Xiaomi 13': (80, 450),
    'OnePlus 11': (60, 370),
}


class Command(BaseCommand):
    help = 'Seed the analytics database with realistic performance event data for the last 10 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=5000,
            help='Number of events to generate (default: 5000)',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = PerformanceEvent.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing events.")

        count = options['count']
        now = timezone.now()
        start = now - timedelta(days=10)
        events = []

        for _ in range(count):
            platform = random.choice(['android', 'ios'])
            device = random.choice(DEVICE_MODELS[platform])
            event_type = random.choice(['app_startup', 'screen_navigation'])

            # Generate timestamp with bias toward peak hours (weekdays 8-17)
            ts = start + timedelta(seconds=random.uniform(0, 10 * 24 * 3600))
            # 60% chance to land in peak hours
            if random.random() < 0.6:
                # Force weekday
                while ts.weekday() >= 5:
                    ts += timedelta(days=1)
                    if ts > now:
                        ts = start + timedelta(days=random.randint(0, 9))
                        while ts.weekday() >= 5:
                            ts += timedelta(days=1)
                # Force peak hour (8-17)
                ts = ts.replace(hour=random.randint(8, 16),
                                minute=random.randint(0, 59),
                                second=random.randint(0, 59))

            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))

            if event_type == 'app_startup':
                low, high = STARTUP_RANGES[device]
            else:
                low, high = NAV_RANGES[device]

            # Use triangular distribution for more realistic data
            duration = random.triangular(low, high, low + (high - low) * 0.3)

            events.append(PerformanceEvent(
                event_type=event_type,
                device_model=device,
                platform=platform,
                duration_ms=round(duration, 2),
                timestamp=ts,
                os_version=random.choice(OS_VERSIONS[platform]),
                app_version=random.choice(APP_VERSIONS),
            ))

        PerformanceEvent.objects.bulk_create(events)
        self.stdout.write(self.style.SUCCESS(f"Created {count} performance events."))
