from unittest.mock import patch

from django.db import ProgrammingError
from django.test import TestCase as DjangoTestCase
from django.utils import timezone

from marketplace_analytics.models import CrashEvent
from marketplace_analytics.services import calculate_bq1_crash_hotspot_metric


class BQ1CrashHotspotMetricTests(DjangoTestCase):
	def test_hotspot_uses_code_location_and_groups_by_device_and_os(self):
		now = timezone.now()

		CrashEvent.objects.create(
			event_name=CrashEvent.EventName.CRASH_OCCURRED,
			feature_name='Checkout',
			code_location='CheckoutFragment.kt:88',
			crash_signature='NullPointerException@Checkout',
			stack_trace='trace-a',
			device_model='Pixel 8',
			platform='android',
			os_version='14',
			app_version='1.0.0',
			occurred_at=now,
		)
		CrashEvent.objects.create(
			event_name=CrashEvent.EventName.CRASH_OCCURRED,
			feature_name='Checkout',
			code_location='CheckoutFragment.kt:88',
			crash_signature='NullPointerException@Checkout',
			stack_trace='trace-b',
			device_model='Pixel 8',
			platform='android',
			os_version='14',
			app_version='1.0.0',
			occurred_at=now,
		)
		CrashEvent.objects.create(
			event_name=CrashEvent.EventName.CRASH_OCCURRED,
			feature_name='Search',
			code_location='',
			crash_signature='IllegalStateException@Search',
			stack_trace='trace-c',
			device_model='Galaxy A54',
			platform='android',
			os_version='13',
			app_version='1.0.0',
			occurred_at=now,
		)

		report = calculate_bq1_crash_hotspot_metric()

		self.assertEqual(report['total_crashes'], 3)
		self.assertEqual(report['top_hotspot']['label'], 'CheckoutFragment.kt:88')
		self.assertEqual(report['top_hotspot']['count'], 2)
		self.assertEqual(report['top_hotspot']['device_breakdown'][0]['label'], 'Pixel 8')
		self.assertEqual(report['top_hotspot']['os_breakdown'][0]['label'], '14')

	def test_hotspot_falls_back_to_feature_name_when_location_missing(self):
		CrashEvent.objects.create(
			event_name=CrashEvent.EventName.CRASH_OCCURRED,
			feature_name='Messages',
			code_location='',
			crash_signature='RuntimeException@Messages',
			stack_trace='trace-d',
			device_model='Pixel 7',
			platform='android',
			os_version='15',
			app_version='1.0.0',
			occurred_at=timezone.now(),
		)

		report = calculate_bq1_crash_hotspot_metric()

		self.assertEqual(report['top_hotspot']['label'], 'Messages')

	def test_missing_crash_table_returns_empty_report(self):
		with patch('marketplace_analytics.services.CrashEvent.objects.all', side_effect=ProgrammingError('missing table')):
			report = calculate_bq1_crash_hotspot_metric()

		self.assertEqual(report['total_crashes'], 0)
		self.assertEqual(report['unique_hotspots'], 0)
		self.assertEqual(report['device_breakdown'], [])
		self.assertIsNone(report['top_hotspot'])

