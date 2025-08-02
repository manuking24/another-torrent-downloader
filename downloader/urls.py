from django.urls import path
from . import views

urlpatterns = [
    path('', views.TorrentListView.as_view(), name='torrent_list'),
    path('add/', views.add_torrent, name='add_torrent'),
    path('pause/<uuid:torrent_id>/', views.pause_torrent, name='pause_torrent'),
    path('resume/<uuid:torrent_id>/', views.resume_torrent, name='resume_torrent'),
    path('delete/<uuid:torrent_id>/', views.delete_torrent, name='delete_torrent'),
    path('download/<uuid:torrent_id>/', views.download_file, name='download_file'),
    path('status/<uuid:torrent_id>/', views.get_torrent_status, name='torrent_status'),
]