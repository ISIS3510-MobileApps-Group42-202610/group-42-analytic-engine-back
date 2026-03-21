from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random

from marketplace_analytics.models import SearchDiscoveryEvent


class Command(BaseCommand):
    help = "Seed fake data for BQ3 dashboard"

    def handle(self, *args, **options):
        SearchDiscoveryEvent.objects.all().delete()

        now = timezone.now()

        courses = [
            ('ISIS3510', 'Mobile Apps'),
            ('MATE1010', 'Calculus'),
            ('FISI2020', 'Physics II'),
            ('IMEC3100', 'Thermodynamics'),
        ]

        categories = [
            ('books', 'Books'),
            ('notes', 'Notes'),
            ('electronics', 'Electronics'),
            ('supplies', 'Supplies'),
        ]

        interaction_events = ['listing_opened', 'message_sent', 'reservation_created']
        filter_types = ['course', 'category', 'both', 'none']

        counter = 1

        for i in range(1, 101):
            session_id = f'bq3-random-{i:03d}'
            user_id = 1000 + i
            start_time = now + timedelta(minutes=i)

            filter_type = random.choice(filter_types)

            course_id = None
            course_name = None
            category_id = None
            category_name = None

            query = random.choice(['book', 'notes', 'calculator', 'lab', 'iphone case'])

            if filter_type in ['course', 'both']:
                course_id, course_name = random.choice(courses)

            if filter_type in ['category', 'both']:
                category_id, category_name = random.choice(categories)

            SearchDiscoveryEvent.objects.create(
                session_id=session_id,
                user_id=user_id,
                event_name=random.choice(['search_started', 'filter_applied']),
                selected_filter_type=filter_type,
                selected_course_id=course_id,
                selected_course_name=course_name,
                selected_category_id=category_id,
                selected_category_name=category_name,
                search_query=query,
                platform='ios',
                app_version='1.0.0',
                occurred_at=start_time,
                client_event_id=f'random-evt-{counter}',
                metadata={},
            )
            counter += 1

            if random.random() < 0.75:
                SearchDiscoveryEvent.objects.create(
                    session_id=session_id,
                    user_id=user_id,
                    event_name=random.choice(interaction_events),
                    listing_id=5000 + i,
                    selected_filter_type=filter_type,
                    selected_course_id=course_id,
                    selected_course_name=course_name,
                    selected_category_id=category_id,
                    selected_category_name=category_name,
                    platform='ios',
                    app_version='1.0.0',
                    occurred_at=start_time + timedelta(seconds=random.randint(3, 180)),
                    client_event_id=f'random-evt-{counter}',
                    metadata={},
                )
                counter += 1

        self.stdout.write(self.style.SUCCESS(
            f'BQ3 fake data created successfully. Events created: {SearchDiscoveryEvent.objects.count()}'
        ))