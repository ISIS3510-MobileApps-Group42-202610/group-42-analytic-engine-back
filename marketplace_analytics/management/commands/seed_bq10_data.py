import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from marketplace_analytics.models import CampusLocationEvent


class Command(BaseCommand):
    help = 'Seed the analytics database with realistic BQ10 campus location data for the last 30 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=300,
            help='Number of campus events to generate (default: 300)',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing BQ10 data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = CampusLocationEvent.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing BQ10 events.")

        count = options['count']
        now = timezone.now()
        start = now - timedelta(days=30)
        
        # Buildings on campus
        buildings = [
            {'name': 'Mario Laserna (ML)', 'lat': 4.6013, 'lng': -74.0657},
            {'name': 'Edificio SD', 'lat': 4.6025, 'lng': -74.0650},
            {'name': 'Edificio W', 'lat': 4.6010, 'lng': -74.0665},
            {'name': 'Edificio Cívico', 'lat': 4.6008, 'lng': -74.0668},
            {'name': 'Edificio Au', 'lat': 4.6020, 'lng': -74.0645},
            {'name': 'Biblioteca General', 'lat': 4.6005, 'lng': -74.0660},
        ]
        
        # Simulate 50 different users
        users = list(range(101, 151))
        
        # Simulate 20 different sellers
        sellers = list(range(1, 21))
        
        # Simulate 100 different listings
        listings = list(range(1, 101))
        
        events = []
        
        # Generate campus_banner_shown events (40% of total)
        banner_count = int(count * 0.4)
        for _ in range(banner_count):
            user_id = random.choice(users)
            building = random.choice(buildings)
            seller_id = random.choice(sellers)
            listing_id = random.choice(listings)
            
            # Generate timestamp (more events during weekdays 8am-5pm)
            ts = start + timedelta(seconds=random.uniform(0, 30 * 24 * 3600))
            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))
            
            # Adjust for weekday peak hours
            if ts.weekday() < 5 and 8 <= ts.hour < 17:
                # Peak hours - more likely to generate events
                pass
            else:
                # Off-peak - skip some events
                if random.random() < 0.5:
                    continue
            
            events.append(CampusLocationEvent(
                event_name='campus_banner_shown',
                user_id=user_id,
                listing_id=listing_id,
                seller_id=seller_id,
                building_name=building['name'],
                latitude=building['lat'] + random.uniform(-0.001, 0.001),
                longitude=building['lng'] + random.uniform(-0.001, 0.001),
                timestamp=ts,
                metadata={
                    'building': building['name'],
                    'timestamp': str(int(ts.timestamp() * 1000))
                }
            ))
        
        # Generate meeting_point_suggested events (30% of total)
        meeting_count = int(count * 0.3)
        for _ in range(meeting_count):
            user_id = random.choice(users)
            building = random.choice(buildings)
            seller_id = random.choice(sellers)
            listing_id = random.choice(listings)
            
            ts = start + timedelta(seconds=random.uniform(0, 30 * 24 * 3600))
            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))
            
            meeting_points = [
                f"{building['name']} lobby",
                f"{building['name']} entrance",
                f"{building['name']} cafeteria",
                f"Near {building['name']}",
            ]
            
            events.append(CampusLocationEvent(
                event_name='meeting_point_suggested',
                user_id=user_id,
                listing_id=listing_id,
                seller_id=seller_id,
                building_name=building['name'],
                latitude=building['lat'],
                longitude=building['lng'],
                timestamp=ts,
                metadata={
                    'building': building['name'],
                    'meeting_point': random.choice(meeting_points),
                    'timestamp': str(int(ts.timestamp() * 1000))
                }
            ))
        
        # Generate location_detected events (30% of total)
        location_count = int(count * 0.3)
        for _ in range(location_count):
            user_id = random.choice(users)
            building = random.choice(buildings)
            
            ts = start + timedelta(seconds=random.uniform(0, 30 * 24 * 3600))
            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))
            
            events.append(CampusLocationEvent(
                event_name='location_detected',
                user_id=user_id,
                building_name=building['name'],
                latitude=building['lat'] + random.uniform(-0.0005, 0.0005),
                longitude=building['lng'] + random.uniform(-0.0005, 0.0005),
                timestamp=ts,
                metadata={
                    'building': building['name'],
                    'timestamp': str(int(ts.timestamp() * 1000))
                }
            ))
        
        CampusLocationEvent.objects.bulk_create(events)
        
        total_events = len(events)
        self.stdout.write(self.style.SUCCESS(
            f"Created {total_events} BQ10 campus location events:\n"
            f"  - {banner_count} campus banner shown events\n"
            f"  - {meeting_count} meeting point suggested events\n"
            f"  - {location_count} location detected events"
        ))
