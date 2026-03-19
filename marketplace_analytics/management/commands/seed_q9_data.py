import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace_analytics.models import AnalyticsEvent, ListingAnalyticsState


class Command(BaseCommand):
    help = (
        'Seed business analytics data for Q9: messaging interaction impact on '
        'transaction completion at listing level.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--listings',
            type=int,
            default=300,
            help='Number of listings to generate (default: 300).',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=120,
            help='How many days back to spread events (default: 120).',
        )
        parser.add_argument(
            '--messaging-rate',
            type=float,
            default=0.55,
            help='Share of listings with first_message_sent (default: 0.55).',
        )
        parser.add_argument(
            '--completion-with-messaging',
            type=float,
            default=0.62,
            help='Completion probability for messaging listings (default: 0.62).',
        )
        parser.add_argument(
            '--completion-without-messaging',
            type=float,
            default=0.34,
            help='Completion probability for non-messaging listings (default: 0.34).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing AnalyticsEvent and ListingAnalyticsState rows before seeding.',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=42,
            help='Random seed for reproducible data generation (default: 42).',
        )

    def handle(self, *args, **options):
        listings = max(1, options['listings'])
        days = max(1, options['days'])
        messaging_rate = self._clamp(options['messaging_rate'])
        completion_with_messaging = self._clamp(options['completion_with_messaging'])
        completion_without_messaging = self._clamp(options['completion_without_messaging'])

        if options['clear']:
            deleted_events, _ = AnalyticsEvent.objects.all().delete()
            deleted_states, _ = ListingAnalyticsState.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    f'Cleared {deleted_events} events and {deleted_states} listing states.'
                )
            )

        rng = random.Random(options['seed'])
        now = timezone.now()
        start = now - timedelta(days=days)

        listing_id_base = int(now.timestamp() * 1000)
        buyer_id_base = 200_000
        seller_id_base = 300_000

        generated = {
            'listings_total': listings,
            'listings_with_messaging': 0,
            'listings_without_messaging': 0,
            'completed_with_messaging': 0,
            'completed_without_messaging': 0,
            'events_total': 0,
        }

        events = []
        states = []

        for idx in range(listings):
            listing_id = listing_id_base + idx
            buyer_user_id = buyer_id_base + idx
            seller_user_id = seller_id_base + (idx % max(1, listings // 3))

            has_messaging = rng.random() < messaging_rate
            completed = rng.random() < (
                completion_with_messaging if has_messaging else completion_without_messaging
            )

            listing_created_at = self._rand_datetime(rng, start, now)

            # Baseline event: listing viewed.
            events.append(
                AnalyticsEvent(
                    event_name=AnalyticsEvent.EventName.LISTING_VIEWED,
                    listing_id=listing_id,
                    buyer_user_id=buyer_user_id,
                    seller_user_id=seller_user_id,
                    occurred_at=listing_created_at,
                    metadata={
                        'seeded': True,
                        'channel': 'search',
                        'semester': self._semester_label(listing_created_at),
                    },
                    client_event_id=f'seed-view-{listing_id}',
                )
            )
            generated['events_total'] += 1

            first_messaging_at = None
            transaction_completed_at = None
            last_event_at = listing_created_at

            if has_messaging:
                generated['listings_with_messaging'] += 1

                # Informational event; not used to define treatment group.
                if rng.random() < 0.85:
                    chat_started_at = listing_created_at + timedelta(minutes=rng.randint(2, 180))
                    events.append(
                        AnalyticsEvent(
                            event_name=AnalyticsEvent.EventName.CHAT_STARTED,
                            listing_id=listing_id,
                            buyer_user_id=buyer_user_id,
                            seller_user_id=seller_user_id,
                            occurred_at=chat_started_at,
                            metadata={'seeded': True, 'note': 'informational_only'},
                            client_event_id=f'seed-chat-{listing_id}',
                        )
                    )
                    generated['events_total'] += 1
                    if chat_started_at > last_event_at:
                        last_event_at = chat_started_at

                first_message_at = listing_created_at + timedelta(minutes=rng.randint(3, 240))
                first_messaging_at = first_message_at
                events.append(
                    AnalyticsEvent(
                        event_name=AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
                        listing_id=listing_id,
                        buyer_user_id=buyer_user_id,
                        seller_user_id=seller_user_id,
                        occurred_at=first_message_at,
                        metadata={'seeded': True, 'message_length': rng.randint(12, 120)},
                        client_event_id=f'seed-msg-{listing_id}',
                    )
                )
                generated['events_total'] += 1
                if first_message_at > last_event_at:
                    last_event_at = first_message_at

                if completed:
                    generated['completed_with_messaging'] += 1
            else:
                generated['listings_without_messaging'] += 1

                # Some listings can have chat_started but no meaningful messaging.
                if rng.random() < 0.12:
                    chat_started_at = listing_created_at + timedelta(minutes=rng.randint(5, 300))
                    events.append(
                        AnalyticsEvent(
                            event_name=AnalyticsEvent.EventName.CHAT_STARTED,
                            listing_id=listing_id,
                            buyer_user_id=buyer_user_id,
                            seller_user_id=seller_user_id,
                            occurred_at=chat_started_at,
                            metadata={'seeded': True, 'note': 'no_first_message'},
                            client_event_id=f'seed-chat-only-{listing_id}',
                        )
                    )
                    generated['events_total'] += 1
                    if chat_started_at > last_event_at:
                        last_event_at = chat_started_at

                if completed:
                    generated['completed_without_messaging'] += 1

            if completed:
                completion_at = listing_created_at + timedelta(hours=rng.randint(2, 240))
                if completion_at > now:
                    completion_at = now - timedelta(minutes=rng.randint(1, 30))
                transaction_completed_at = completion_at

                events.append(
                    AnalyticsEvent(
                        event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
                        listing_id=listing_id,
                        buyer_user_id=buyer_user_id,
                        seller_user_id=seller_user_id,
                        occurred_at=completion_at,
                        metadata={'seeded': True, 'payment_method': rng.choice(['cash', 'transfer'])},
                        client_event_id=f'seed-done-{listing_id}',
                    )
                )
                generated['events_total'] += 1
                if completion_at > last_event_at:
                    last_event_at = completion_at

            states.append(
                ListingAnalyticsState(
                    listing_id=listing_id,
                    buyer_user_id=buyer_user_id,
                    seller_user_id=seller_user_id,
                    has_messaging_interaction=has_messaging,
                    first_messaging_at=first_messaging_at,
                    is_transaction_completed=completed,
                    transaction_completed_at=transaction_completed_at,
                    last_event_at=last_event_at,
                )
            )

        with transaction.atomic():
            AnalyticsEvent.objects.bulk_create(events, batch_size=1000, ignore_conflicts=True)
            ListingAnalyticsState.objects.bulk_create(states, batch_size=1000, ignore_conflicts=True)

        self._print_summary(generated)

    @staticmethod
    def _rand_datetime(rng, start_dt, end_dt):
        span_seconds = max(1, int((end_dt - start_dt).total_seconds()))
        return start_dt + timedelta(seconds=rng.randint(0, span_seconds))

    @staticmethod
    def _clamp(value):
        return max(0.0, min(1.0, value))

    @staticmethod
    def _semester_label(dt):
        return 'A' if dt.month <= 6 else 'B'

    def _print_summary(self, generated):
        with_total = generated['listings_with_messaging']
        without_total = generated['listings_without_messaging']

        with_rate = (
            generated['completed_with_messaging'] / with_total if with_total else 0
        )
        without_rate = (
            generated['completed_without_messaging'] / without_total if without_total else 0
        )

        self.stdout.write(self.style.SUCCESS('Q9 seed completed successfully.'))
        self.stdout.write(f"Listings total: {generated['listings_total']}")
        self.stdout.write(f"Events total: {generated['events_total']}")
        self.stdout.write(
            f"With messaging: {with_total} listings, {generated['completed_with_messaging']} completed "
            f"({with_rate:.2%})"
        )
        self.stdout.write(
            f"Without messaging: {without_total} listings, {generated['completed_without_messaging']} completed "
            f"({without_rate:.2%})"
        )
