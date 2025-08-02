from django.urls import path
from . import views

urlpatterns = [
    # Main pages
    path('', views.torrent_list, name='torrent_list'),
    path('torrent/<uuid:torrent_id>/', views.torrent_detail, name='torrent_detail'),
    
    # Torrent management
    path('add/', views.add_torrent, name='add_torrent'),
    path('pause/<uuid:torrent_id>/', views.pause_torrent, name='pause_torrent'),
    path('resume/<uuid:torrent_id>/', views.resume_torrent, name='resume_torrent'),
    path('restart/<uuid:torrent_id>/', views.restart_torrent, name='restart_torrent'),
    path('delete/<uuid:torrent_id>/', views.delete_torrent, name='delete_torrent'),
    
    # File operations
    path('download/<uuid:torrent_id>/', views.download_file, name='download_file'),
    
    # API endpoints
    path('status/<uuid:torrent_id>/', views.get_torrent_status, name='torrent_status'),
    
    # Bulk operations
    path('cleanup/completed/', views.cleanup_completed, name='cleanup_completed'),
    path('cleanup/failed/', views.cleanup_failed, name='cleanup_failed'),
]