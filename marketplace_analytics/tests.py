from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from marketplace_analytics.models import AnalyticsEvent, ListingAnalyticsState
from marketplace_analytics.services import calculate_q9_messaging_impact_metric_with_filters
from marketplace_analytics.views import _build_bq12_period_axis, _normalize_bq12_period


class BusinessEventIngestionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_transaction_completed_updates_listing_state(self):
        response = self.client.post(
            reverse('business-event-ingestion'),
            {
                'event_name': 'transaction_completed',
                'listing_id': 1001,
                'buyer_user_id': 10,
                'seller_user_id': 20,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        state = ListingAnalyticsState.objects.get(listing_id=1001)
        self.assertTrue(state.is_transaction_completed)
        self.assertIsNotNone(state.transaction_completed_at)

    def test_android_legacy_transaction_alias_updates_listing_state(self):
        response = self.client.post(
            reverse('legacy-events'),
            {
                'event_name': 'sale_completed',
                'user_id': 10,
                'properties': {
                    'listingId': 1002,
                    'sellerId': 20,
                    'timestamp': str(int(timezone.now().timestamp() * 1000)),
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['target'], 'business_events')
        state = ListingAnalyticsState.objects.get(listing_id=1002)
        self.assertTrue(state.is_transaction_completed)


class Q9MetricTests(TestCase):
    def test_grouping_uses_listing_state_not_messages_inside_period_only(self):
        now = timezone.now()
        old_message_time = now - timedelta(days=40)
        completion_time = now - timedelta(days=5)

        AnalyticsEvent.objects.create(
            event_name=AnalyticsEvent.EventName.LISTING_VIEWED,
            listing_id=2001,
            occurred_at=old_message_time - timedelta(hours=1),
        )
        AnalyticsEvent.objects.create(
            event_name=AnalyticsEvent.EventName.FIRST_MESSAGE_SENT,
            listing_id=2001,
            buyer_user_id=10,
            seller_user_id=20,
            occurred_at=old_message_time,
        )
        AnalyticsEvent.objects.create(
            event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
            listing_id=2001,
            buyer_user_id=10,
            seller_user_id=20,
            occurred_at=completion_time,
        )
        ListingAnalyticsState.objects.create(
            listing_id=2001,
            buyer_user_id=10,
            seller_user_id=20,
            has_messaging_interaction=True,
            first_messaging_at=old_message_time,
            is_transaction_completed=True,
            transaction_completed_at=completion_time,
            last_event_at=completion_time,
        )

        report = calculate_q9_messaging_impact_metric_with_filters()

        self.assertEqual(report['group_with_messaging']['listings'], 1)
        self.assertEqual(report['group_without_messaging']['listings'], 0)
        self.assertEqual(report['group_with_messaging']['completed'], 1)

    def test_bounded_period_counts_completion_inside_same_window(self):
        now = timezone.now()
        listing_time = now - timedelta(days=5)
        completion_time = now + timedelta(days=1)

        AnalyticsEvent.objects.create(
            event_name=AnalyticsEvent.EventName.LISTING_VIEWED,
            listing_id=2002,
            occurred_at=listing_time,
        )
        AnalyticsEvent.objects.create(
            event_name=AnalyticsEvent.EventName.TRANSACTION_COMPLETED,
            listing_id=2002,
            occurred_at=completion_time,
        )
        ListingAnalyticsState.objects.create(
            listing_id=2002,
            is_transaction_completed=True,
            transaction_completed_at=completion_time,
            last_event_at=completion_time,
        )

        report = calculate_q9_messaging_impact_metric_with_filters(
            since=now - timedelta(days=10),
            until=now,
            period_label='custom',
        )

        self.assertEqual(report['group_without_messaging']['listings'], 1)
        self.assertEqual(report['group_without_messaging']['completed'], 0)
        self.assertEqual(report['total_completed'], 0)


class BQ12PeriodAxisTests(SimpleTestCase):
    def test_daily_axis_includes_every_day_in_selected_range(self):
        rows = [
            {'period_start': '2026-04-01T00:00:00Z'},
            {'period_start': '2026-04-03T00:00:00Z'},
        ]

        periods = _build_bq12_period_axis(
            rows,
            'day',
            date(2026, 4, 1),
            date(2026, 4, 3),
        )

        self.assertEqual(periods, ['2026-04-01', '2026-04-02', '2026-04-03'])

    def test_daily_period_normalization_strips_time_part(self):
        self.assertEqual(
            _normalize_bq12_period('2026-04-25T14:30:00Z', 'day'),
            '2026-04-25',
        )
