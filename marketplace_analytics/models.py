from django.db import models


class PerformanceEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('app_startup', 'App Startup'),
        ('screen_navigation', 'Screen Navigation'),
    ]

    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    device_model = models.CharField(max_length=100)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    duration_ms = models.FloatField(help_text='Duration in milliseconds')
    timestamp = models.DateTimeField()
    os_version = models.CharField(max_length=20, blank=True, default='')
    app_version = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['device_model']),
        ]

    def __str__(self):
        """
        para simplificar el print y guardado de la info de performance en la db
        :return: la string en formato "tipo_de_evento - modelo_dispositivo - duración_en_ms"
        """
        return f"{self.event_type} - {self.device_model} - {self.duration_ms}ms"
