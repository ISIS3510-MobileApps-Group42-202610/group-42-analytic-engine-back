import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace_analytics.models import AnalyticsEvent

CATEGORIES = ['Textbooks', 'Electronics', 'Accessories', 'Clothing', 'Sports', 'Stationery', 'Other']

PRODUCTS_BY_CATEGORY = {
    'Textbooks': ['Calculus 8th Ed', 'Physics Fundamentals', 'Introduction to Algorithms', 'Organic Chemistry', 'Linear Algebra'],
    'Electronics': ['TI-84 Calculator', 'Laptop Lenovo', 'iPad Pro', 'Arduino Kit', 'USB Hub'],
    'Accessories': ['Backpack', 'Laptop Sleeve', 'Notebook Set', 'Pen Collection', 'USB Cable'],
    'Clothing': ['University Hoodie', 'Lab Coat', 'Sports Jacket', 'Cap', 'T-Shirt'],
    'Sports': ['Tennis Racket', 'Soccer Ball', 'Yoga Mat', 'Resistance Bands', 'Water Bottle'],
    'Stationery': ['Markers Set', 'Ruler', 'Sticky Notes', 'Binder', 'Highlighters'],
    'Other': ['Desk Lamp', 'Mini Fridge', 'Coffee Maker', 'Plant', 'Picture Frame'],
}

PRICE_RANGE_BY_CATEGORY = {
    'Textbooks':   (15.0, 80.0),
    'Electronics': (30.0, 300.0),
    'Accessories': (5.0, 50.0),
    'Clothing':    (8.0, 60.0),
    'Sports':      (10.0, 120.0),
    'Stationery':  (2.0, 25.0),
    'Other':       (5.0, 100.0),
}


class Command(BaseCommand):
    help = (
        'Seed business analytics data for BQ11: which brands and product categories '
        'have the highest transaction volume per academic semester.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--transactions',
            type=int,
            default=400,
            help='Number of completed transactions to generate (default: 400).',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='How many days back to spread events (default: 365).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing TRANSACTION_COMPLETED AnalyticsEvent rows before seeding.',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=11,
            help='Random seed for reproducible data generation (default: 11).',
        )

    def handle(self, *args, **options):
        transactions_count = max(1, options['transactions'])
        days = max(1, options['days'])

        if options['clear']:
            deleted, _ = AnalyticsEvent.objects.filter(
                event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
                metadata__seeded_bq11=True
            ).delete()
            self.stdout.write(self.style.WARNING(f'Cleared {deleted} BQ11 seeded events.'))

        rng = random.Random(options['seed'])
        now = timezone.now()
        start = now - timedelta(days=days)

        listing_id_base = int(now.timestamp() * 1000) + 11_000_000
        buyer_id_base  = 500_000
        seller_id_base = 600_000

        events = []
        summary = {cat: {'A': 0, 'B': 0} for cat in CATEGORIES}

        for idx in range(transactions_count):
            listing_id    = listing_id_base + idx
            buyer_user_id = buyer_id_base + idx
            seller_user_id = seller_id_base + (idx % max(1, transactions_count // 5))

            occurred_at = self._rand_datetime(rng, start, now)
            semester    = 'A' if occurred_at.month <= 6 else 'B'
            year        = occurred_at.year
            semester_label = f'{year}-{semester}'

            category = rng.choice(CATEGORIES)
            product  = rng.choice(PRODUCTS_BY_CATEGORY[category])
            price_min, price_max = PRICE_RANGE_BY_CATEGORY[category]
            selling_price = round(rng.uniform(price_min, price_max), 2)

            events.append(
                AnalyticsEvent(
                    event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
                    listing_id=listing_id,
                    buyer_user_id=buyer_user_id,
                    seller_user_id=seller_user_id,
                    occurred_at=occurred_at,
                    metadata={
                        'seeded': True,
                        'seeded_bq11': True,
                        'category': category,
                        'product': product,
                        'selling_price': selling_price,
                        'semester': semester_label,
                    },
                    client_event_id=f'seed-bq11-txn-{listing_id}-{idx}',
                )
            )
            summary[category][semester] += 1

        with transaction.atomic():
            AnalyticsEvent.objects.bulk_create(events, batch_size=1000, ignore_conflicts=True)

        self._print_summary(transactions_count, summary)

    @staticmethod
    def _rand_datetime(rng, start_dt, end_dt):
        span = max(1, int((end_dt - start_dt).total_seconds()))
        return start_dt + timedelta(seconds=rng.randint(0, span))

    def _print_summary(self, total, summary):
        self.stdout.write(self.style.SUCCESS('BQ11 seed completed successfully.'))
        self.stdout.write(f'Total transactions generated: {total}')
        self.stdout.write('')
        self.stdout.write(f'{"Category":<15} {"Semester A":>12} {"Semester B":>12} {"Total":>8}')
        self.stdout.write('-' * 50)
        for cat, counts in sorted(summary.items(), key=lambda x: -(x[1]['A'] + x[1]['B'])):
            total_cat = counts['A'] + counts['B']
            self.stdout.write(f'{cat:<15} {counts["A"]:>12} {counts["B"]:>12} {total_cat:>8}')
