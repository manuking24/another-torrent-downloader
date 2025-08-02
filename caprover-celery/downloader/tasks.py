import libtorrent as lt
import time
import os
import zipfile
import shutil
from celery import shared_task
from django.conf import settings
from .models import TorrentDownload
from django.utils import timezone

@shared_task
def download_torrent(torrent_id):
    try:
        torrent = TorrentDownload.objects.get(id=torrent_id)
        torrent.status = 'downloading'
        torrent.save()
        
        # Create session
        ses = lt.session()
        ses.listen_on(6881, 6891)
        
        # Add torrent
        params = {
            'url': torrent.magnet_link,
            'save_path': str(settings.TORRENT_DOWNLOAD_DIR)
        }
        
        handle = ses.add_torrent(params)
        
        # Wait for metadata
        while not handle.has_metadata():
            time.sleep(1)
            if TorrentDownload.objects.get(id=torrent_id).status == 'paused':
                ses.remove_torrent(handle)
                return
        
        # Update torrent info
        info = handle.get_torrent_info()
        torrent.name = info.name()
        torrent.size = info.total_size()
        torrent.is_multi_file = info.num_files() > 1
        torrent.save()
        
        # Download loop
        while handle.status().progress < 1:
            time.sleep(1)
            
            # Check if paused or cancelled
            current_torrent = TorrentDownload.objects.get(id=torrent_id)
            if current_torrent.status == 'paused':
                ses.remove_torrent(handle)
                return
            
            # Update progress
            status = handle.status()
            torrent.progress = status.progress
            torrent.download_speed = status.download_rate / 1024  # Convert to KB/s
            torrent.upload_speed = status.upload_rate / 1024
            torrent.downloaded = status.total_done
            torrent.peers = status.num_peers
            torrent.seeds = status.num_seeds
            
            # Calculate ETA
            if status.download_rate > 0:
                remaining = torrent.size - torrent.downloaded
                eta_seconds = remaining / status.download_rate
                if eta_seconds < 60:
                    torrent.eta = f"{int(eta_seconds)}s"
                elif eta_seconds < 3600:
                    torrent.eta = f"{int(eta_seconds/60)}m"
                else:
                    torrent.eta = f"{int(eta_seconds/3600)}h {int((eta_seconds%3600)/60)}m"
            else:
                torrent.eta = "∞"
            
            torrent.save()
        
        # Download completed
        torrent.status = 'completed'
        torrent.progress = 1.0
        torrent.completed_at = timezone.now()
        torrent.file_path = os.path.join(settings.TORRENT_DOWNLOAD_DIR, info.name())
        torrent.save()
        
        ses.remove_torrent(handle)
        
    except Exception as e:
        torrent.status = 'failed'
        torrent.save()
        raise e

@shared_task
def create_zip_file(torrent_id):
    try:
        torrent = TorrentDownload.objects.get(id=torrent_id)
        if not torrent.is_multi_file or torrent.status != 'completed':
            return
        
        source_dir = torrent.file_path
        zip_path = f"{source_dir}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
        
        return zip_path
    except Exception as e:
        print(f"Error creating zip: {e}")
        return None