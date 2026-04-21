from datetime import timedelta
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from marketplace_analytics.models import MessagingResponseEvent


class Command(BaseCommand):
    help = "Seed fake data for BQ6 seller response time dashboard"

    def handle(self, *args, **options):
        MessagingResponseEvent.objects.all().delete()

        now = timezone.now()
        seller_ids = [2001, 2002, 2003, 2004, 2005, 2006]

        counter = 1

        for day_offset in range(30):
            day_base = now - timedelta(days=day_offset)

            for seller_id in seller_ids:
                measurements_today = random.randint(1, 4)

                for measurement in range(measurements_today):
                    event_time = day_base - timedelta(
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                    )

                    response_minutes = round(random.uniform(1.5, 180.0), 2)

                    MessagingResponseEvent.objects.create(
                        event_name=MessagingResponseEvent.EventName.SELLER_AVG_RESPONSE_TIME,
                        user_id=1000 + seller_id,
                        seller_id=seller_id,
                        avg_response_minutes=response_minutes,
                        unread_conversations=random.randint(0, 12),
                        timestamp=event_time,
                        properties={
                            'source': 'seed_bq6_data',
                            'sample_id': counter,
                        },
                    )
                    counter += 1

                MessagingResponseEvent.objects.create(
                    event_name=MessagingResponseEvent.EventName.MESSAGES_SCREEN_OPENED,
                    user_id=5000 + seller_id,
                    seller_id=seller_id,
                    unread_conversations=random.randint(0, 8),
                    timestamp=day_base - timedelta(minutes=random.randint(0, 120)),
                    properties={
                        'source': 'seed_bq6_data',
                        'sample_id': counter,
                    },
                )
                counter += 1

                MessagingResponseEvent.objects.create(
                    event_name=random.choice([
                        MessagingResponseEvent.EventName.MESSAGE_SENT,
                        MessagingResponseEvent.EventName.FIRST_MESSAGE_SENT,
                    ]),
                    user_id=6000 + seller_id,
                    seller_id=seller_id,
                    timestamp=day_base - timedelta(minutes=random.randint(0, 120)),
                    properties={
                        'source': 'seed_bq6_data',
                        'sample_id': counter,
                    },
                )
                counter += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'BQ6 fake data created successfully. Events created: {MessagingResponseEvent.objects.count()}'
            )
        )