import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace_analytics.models import AnalyticsEvent

CATEGORIES = ['Textbooks', 'Electronics', 'Accessories',
              'Clothing', 'Sports', 'Stationery', 'Other']


class Command(BaseCommand):
    help = (
        'Seed business analytics data for BQ5: most reliable sellers from buyer perspective. '
        'Generates transaction_completed events enriched with seller_id, rating, '
        'response_time_minutes, and category.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--transactions', type=int, default=300,
                            help='Number of completed transactions to generate (default: 300).')
        parser.add_argument('--sellers', type=int, default=20,
                            help='Number of distinct sellers to simulate (default: 20).')
        parser.add_argument('--days', type=int, default=180,
                            help='How many days back to spread events (default: 180).')
        parser.add_argument('--clear', action='store_true',
                            help='Delete existing BQ5 seeded events before seeding.')
        parser.add_argument('--seed', type=int, default=5,
                            help='Random seed for reproducible data (default: 5).')

    def handle(self, *args, **options):
        n_transactions = max(1, options['transactions'])
        n_sellers = max(1, options['sellers'])
        days = max(1, options['days'])

        if options['clear']:
            deleted, _ = AnalyticsEvent.objects.filter(
                event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
                metadata__seeded_bq5=True
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared {deleted} BQ5 seeded events.'))

        rng = random.Random(options['seed'])
        now = timezone.now()
        start = now - timedelta(days=days)

        listing_id_base = int(now.timestamp() * 1000) + 5_000_000
        buyer_id_base = 700_000
        seller_id_base = 800_000

        seller_profiles = {}
        for i in range(n_sellers):
            seller_id = seller_id_base + i
            tier = rng.choice(['high', 'high', 'mid', 'mid', 'low'])
            if tier == 'high':
                seller_profiles[seller_id] = {
                    'rating_range':        (4, 5),
                    'response_range':      (2, 30),
                    'completion_rate':     0.92,
                }
            elif tier == 'mid':
                seller_profiles[seller_id] = {
                    'rating_range':        (3, 4),
                    'response_range':      (30, 120),
                    'completion_rate':     0.70,
                }
            else:
                seller_profiles[seller_id] = {
                    'rating_range':        (1, 3),
                    'response_range':      (120, 480),
                    'completion_rate':     0.45,
                }

        seller_ids = list(seller_profiles.keys())
        events = []

        for idx in range(n_transactions):
            listing_id = listing_id_base + idx
            buyer_user_id = buyer_id_base + idx
            seller_id = rng.choice(seller_ids)
            profile = seller_profiles[seller_id]

            occurred_at = self._rand_datetime(rng, start, now)
            semester = 'A' if occurred_at.month <= 6 else 'B'
            semester_label = f'{occurred_at.year}-{semester}'

            rating = rng.randint(*profile['rating_range'])
            response_minutes = rng.randint(*profile['response_range'])
            category = rng.choice(CATEGORIES)
            selling_price = round(rng.uniform(5.0, 300.0), 2)
            completed = rng.random() < profile['completion_rate']

            if not completed:
                continue

            events.append(
                AnalyticsEvent(
                    event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
                    listing_id=listing_id,
                    buyer_user_id=buyer_user_id,
                    seller_user_id=seller_id,
                    occurred_at=occurred_at,
                    metadata={
                        'seeded':               True,
                        'seeded_bq5':           True,
                        'seller_id':            seller_id,
                        'rating':               rating,
                        'response_time_minutes': response_minutes,
                        'category':             category,
                        'selling_price':        selling_price,
                        'semester':             semester_label,
                    },
                    client_event_id=f'seed-bq5-txn-{listing_id}-{idx}',
                )
            )

        with transaction.atomic():
            AnalyticsEvent.objects.bulk_create(
                events, batch_size=1000, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(
            'BQ5 seed completed successfully.'))
        self.stdout.write(
            f'Events generated: {len(events)} out of {n_transactions} attempted.')

    @staticmethod
    def _rand_datetime(rng, start_dt, end_dt):
        span = max(1, int((end_dt - start_dt).total_seconds()))
        return start_dt + timedelta(seconds=rng.randint(0, span))
