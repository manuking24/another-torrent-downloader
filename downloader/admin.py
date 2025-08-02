from django.contrib import admin
from .models import TorrentDownload

@admin.register(TorrentDownload)
class TorrentDownloadAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'progress_percentage', 'size_human', 'created_at']
    list_filter = ['status', 'is_multi_file', 'created_at']
    search_fields = ['name', 'magnet_link']
    readonly_fields = ['id', 'created_at', 'completed_at', 'progress_percentage', 'size_human', 'downloaded_human']
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'magnet_link', 'status')
        }),
        ('Download Progress', {
            'fields': ('progress', 'progress_percentage', 'download_speed', 'upload_speed')
        }),
        ('File Info', {
            'fields': ('size', 'size_human', 'downloaded', 'downloaded_human', 'is_multi_file', 'file_path')
        }),
        ('Network Info', {
            'fields': ('peers', 'seeds', 'eta')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at')
        }),
    )