from django.db import models
from django.utils import timezone
import uuid

class TorrentDownload(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('downloading', 'Downloading'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('paused', 'Paused'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    magnet_link = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.FloatField(default=0.0)
    download_speed = models.FloatField(default=0.0)  # KB/s
    upload_speed = models.FloatField(default=0.0)    # KB/s
    size = models.BigIntegerField(default=0)         # bytes
    downloaded = models.BigIntegerField(default=0)   # bytes
    peers = models.IntegerField(default=0)
    seeds = models.IntegerField(default=0)
    eta = models.CharField(max_length=50, blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    is_multi_file = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    @property
    def progress_percentage(self):
        return min(100, max(0, self.progress * 100))
    
    @property
    def size_human(self):
        return self.format_bytes(self.size)
    
    @property
    def downloaded_human(self):
        return self.format_bytes(self.downloaded)
    
    @property
    def download_speed_human(self):
        return f"{self.format_bytes(self.download_speed * 1024)}/s"
    
    @staticmethod
    def format_bytes(bytes_val):
        if bytes_val == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"
