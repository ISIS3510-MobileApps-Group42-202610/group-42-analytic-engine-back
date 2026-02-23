# example/urls.py
from django.urls import path

from marketplace_analytics.views import index


urlpatterns = [
    path('', index),
]