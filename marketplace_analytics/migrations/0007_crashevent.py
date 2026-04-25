from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace_analytics', '0006_messagingresponseevent'),
    ]

    operations = [
        migrations.CreateModel(
            name='CrashEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_name', models.CharField(choices=[('crash_occurred', 'Crash Occurred')], db_index=True, max_length=30)),
                ('feature_name', models.CharField(blank=True, db_index=True, default='', max_length=120)),
                ('code_location', models.CharField(blank=True, db_index=True, default='', max_length=255)),
                ('crash_signature', models.CharField(db_index=True, max_length=255)),
                ('stack_trace', models.TextField(blank=True, default='')),
                ('device_model', models.CharField(blank=True, db_index=True, default='', max_length=100)),
                ('platform', models.CharField(choices=[('android', 'Android'), ('ios', 'iOS')], default='android', max_length=10)),
                ('os_version', models.CharField(blank=True, default='', max_length=20)),
                ('app_version', models.CharField(blank=True, default='', max_length=20)),
                ('occurred_at', models.DateTimeField(db_index=True)),
                ('ingested_at', models.DateTimeField(auto_now_add=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('client_event_id', models.CharField(blank=True, max_length=64, null=True, unique=True)),
            ],
            options={
                'ordering': ['-occurred_at', '-id'],
                'indexes': [
                    models.Index(fields=['event_name', 'occurred_at'], name='bq1_event_time_idx'),
                    models.Index(fields=['crash_signature', 'occurred_at'], name='bq1_signature_idx'),
                    models.Index(fields=['code_location', 'occurred_at'], name='bq1_location_idx'),
                    models.Index(fields=['feature_name', 'occurred_at'], name='bq1_feature_idx'),
                    models.Index(fields=['device_model', 'platform'], name='bq1_device_platform_idx'),
                ],
            },
        ),
    ]

