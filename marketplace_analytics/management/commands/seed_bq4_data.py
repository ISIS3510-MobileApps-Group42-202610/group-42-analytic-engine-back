import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from marketplace_analytics.models import MessagingResponseEvent


class Command(BaseCommand):
    help = 'Seed the analytics database with realistic BQ4 messaging data for the last 30 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=200,
            help='Number of response time events to generate (default: 200)',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing BQ4 data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = MessagingResponseEvent.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing BQ4 events.")

        count = options['count']
        now = timezone.now()
        start = now - timedelta(days=30)
        
        # Simulate 10 different sellers with varying response times
        sellers = list(range(1, 11))
        # Simulate 20 different buyers
        buyers = list(range(101, 121))
        
        events = []
        
        # Generate seller_avg_response_time events
        for _ in range(count):
            seller_id = random.choice(sellers)
            buyer_id = random.choice(buyers)
            
            # Generate timestamp
            ts = start + timedelta(seconds=random.uniform(0, 30 * 24 * 3600))
            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))
            
            # Different sellers have different response time patterns
            if seller_id <= 3:
                # Fast responders (1-10 minutes)
                avg_minutes = random.triangular(0.5, 10, 3)
            elif seller_id <= 7:
                # Medium responders (5-30 minutes)
                avg_minutes = random.triangular(5, 30, 15)
            else:
                # Slow responders (20-120 minutes)
                avg_minutes = random.triangular(20, 120, 45)
            
            events.append(MessagingResponseEvent(
                event_name='seller_avg_response_time',
                user_id=buyer_id,
                seller_id=seller_id,
                avg_response_minutes=round(avg_minutes, 2),
                timestamp=ts,
                properties={
                    'seller_id': str(seller_id),
                    'avg_minutes': str(round(avg_minutes, 2)),
                    'timestamp': str(int(ts.timestamp() * 1000))
                }
            ))
        
        # Generate messages_screen_opened events (about 30% of response events)
        messages_opened_count = int(count * 0.3)
        for _ in range(messages_opened_count):
            buyer_id = random.choice(buyers)
            ts = start + timedelta(seconds=random.uniform(0, 30 * 24 * 3600))
            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))
            
            unread_count = random.randint(0, 5)
            
            events.append(MessagingResponseEvent(
                event_name='messages_screen_opened',
                user_id=buyer_id,
                unread_conversations=unread_count,
                timestamp=ts,
                properties={
                    'unread_conversations': str(unread_count),
                    'timestamp': str(int(ts.timestamp() * 1000))
                }
            ))
        
        # Generate message_sent events (about 50% of response events)
        messages_sent_count = int(count * 0.5)
        for _ in range(messages_sent_count):
            buyer_id = random.choice(buyers)
            seller_id = random.choice(sellers)
            ts = start + timedelta(seconds=random.uniform(0, 30 * 24 * 3600))
            if ts > now:
                ts = now - timedelta(minutes=random.randint(1, 60))
            
            events.append(MessagingResponseEvent(
                event_name='message_sent',
                user_id=buyer_id,
                seller_id=seller_id,
                timestamp=ts,
                properties={
                    'seller_id': str(seller_id),
                    'timestamp': str(int(ts.timestamp() * 1000))
                }
            ))
        
        MessagingResponseEvent.objects.bulk_create(events)
        
        total_events = len(events)
        self.stdout.write(self.style.SUCCESS(
            f"Created {total_events} BQ4 events:\n"
            f"  - {count} seller response time measurements\n"
            f"  - {messages_opened_count} messages screen opened events\n"
            f"  - {messages_sent_count} message sent events"
        ))
