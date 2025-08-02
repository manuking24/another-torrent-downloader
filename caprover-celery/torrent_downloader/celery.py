import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'torrent_downloader.settings')

app = Celery('torrent_downloader')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# torrent_downloader/__init__.py
from .celery import app as celery_app
__all__ = ('celery_app',)
