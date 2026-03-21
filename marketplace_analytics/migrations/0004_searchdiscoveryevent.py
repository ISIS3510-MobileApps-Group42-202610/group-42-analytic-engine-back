from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace_analytics', '0003_analyticsevent_listinganalyticsstate'),
    ]

    operations = [
        migrations.CreateModel(
            name='SearchDiscoveryEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_id', models.CharField(db_index=True, max_length=64)),
                ('user_id', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('event_name', models.CharField(
                    choices=[
                        ('search_started', 'Search Started'),
                        ('filter_applied', 'Filter Applied'),
                        ('listing_opened', 'Listing Opened'),
                        ('message_sent', 'Message Sent'),
                        ('reservation_created', 'Reservation Created'),
                    ],
                    db_index=True,
                    max_length=32,
                )),
                ('listing_id', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('selected_course_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('selected_course_name', models.CharField(blank=True, max_length=255, null=True)),
                ('selected_category_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('selected_category_name', models.CharField(blank=True, max_length=255, null=True)),
                ('selected_filter_type', models.CharField(
                    choices=[
                        ('course', 'Course'),
                        ('category', 'Category'),
                        ('both', 'Both'),
                        ('none', 'None'),
                    ],
                    db_index=True,
                    default='none',
                    max_length=20,
                )),
                ('search_query', models.CharField(blank=True, max_length=255, null=True)),
                ('platform', models.CharField(blank=True, default='ios', max_length=20)),
                ('app_version', models.CharField(blank=True, default='', max_length=40)),
                ('occurred_at', models.DateTimeField(db_index=True)),
                ('ingested_at', models.DateTimeField(auto_now_add=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('client_event_id', models.CharField(blank=True, max_length=64, null=True, unique=True)),
            ],
            options={
                'ordering': ['-occurred_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='searchdiscoveryevent',
            index=models.Index(fields=['session_id', 'occurred_at'], name='bq3_session_occ_idx'),
        ),
        migrations.AddIndex(
            model_name='searchdiscoveryevent',
            index=models.Index(fields=['event_name', 'occurred_at'], name='bq3_event_occ_idx'),
        ),
        migrations.AddIndex(
            model_name='searchdiscoveryevent',
            index=models.Index(fields=['selected_filter_type', 'occurred_at'], name='bq3_filter_occ_idx'),
        ),
        migrations.AddIndex(
            model_name='searchdiscoveryevent',
            index=models.Index(fields=['selected_course_id'], name='bq3_course_idx'),
        ),
        migrations.AddIndex(
            model_name='searchdiscoveryevent',
            index=models.Index(fields=['selected_category_id'], name='bq3_category_idx'),
        ),
    ]