from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace_analytics', '0004_searchdiscoveryevent'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveIndex(
                    model_name='analyticsevent',
                    name='marketplace_listing_eb3274_idx',
                ),
                migrations.RemoveIndex(
                    model_name='analyticsevent',
                    name='marketplace_event_n_2e4955_idx',
                ),
                migrations.RemoveIndex(
                    model_name='listinganalyticsstate',
                    name='marketplace_has_mes_1c2d17_idx',
                ),
                migrations.RemoveIndex(
                    model_name='listinganalyticsstate',
                    name='marketplace_updated_d0f833_idx',
                ),
                migrations.RemoveIndex(
                    model_name='performanceevent',
                    name='marketplace_event_t_7bcba3_idx',
                ),
                migrations.RemoveIndex(
                    model_name='performanceevent',
                    name='marketplace_device__117225_idx',
                ),

                migrations.AddIndex(
                    model_name='analyticsevent',
                    index=models.Index(
                        fields=['listing_id', 'event_name', 'occurred_at'],
                        name='bq9_listing_event_occ_idx',
                    ),
                ),
                migrations.AddIndex(
                    model_name='analyticsevent',
                    index=models.Index(
                        fields=['event_name', 'occurred_at'],
                        name='bq9_event_occ_idx',
                    ),
                ),
                migrations.AddIndex(
                    model_name='listinganalyticsstate',
                    index=models.Index(
                        fields=['has_messaging_interaction', 'is_transaction_completed'],
                        name='bq9_msg_txn_idx',
                    ),
                ),
                migrations.AddIndex(
                    model_name='listinganalyticsstate',
                    index=models.Index(
                        fields=['updated_at'],
                        name='bq9_updated_idx',
                    ),
                ),
                migrations.AddIndex(
                    model_name='performanceevent',
                    index=models.Index(
                        fields=['event_type', 'timestamp'],
                        name='bq2_event_time_idx',
                    ),
                ),
                migrations.AddIndex(
                    model_name='performanceevent',
                    index=models.Index(
                        fields=['device_model'],
                        name='bq2_device_idx',
                    ),
                ),
            ],
        ),
    ]