# downloader/views.py - All Functional Views
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, FileResponse
from django.contrib import messages
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
import os
import shutil
import zipfile
import threading
import time
from .models import TorrentDownload
from .forms import TorrentForm
from django.conf import settings
from django.utils import timezone

# Global dictionary to track download threads
download_threads = {}

def torrent_list(request):
    """Main page showing all torrents with pagination and search"""
    
    # Get search query
    search_query = request.GET.get('search', '')
    
    # Filter torrents based on search
    torrents = TorrentDownload.objects.all()
    if search_query:
        torrents = torrents.filter(
            Q(name__icontains=search_query) | 
            Q(status__icontains=search_query)
        )
    
    # Order by creation date (newest first)
    torrents = torrents.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(torrents, 10)  # Show 10 torrents per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate statistics
    stats = {
        'total': TorrentDownload.objects.count(),
        'downloading': TorrentDownload.objects.filter(status='downloading').count(),
        'completed': TorrentDownload.objects.filter(status='completed').count(),
        'failed': TorrentDownload.objects.filter(status='failed').count(),
        'pending': TorrentDownload.objects.filter(status='pending').count(),
        'paused': TorrentDownload.objects.filter(status='paused').count(),
    }
    
    # Create form for adding new torrents
    form = TorrentForm()
    
    context = {
        'torrents': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'form': form,
        'stats': stats,
        'search_query': search_query,
    }
    
    return render(request, 'downloader/index.html', context)

def download_torrent_sync(torrent_id):
    """Synchronous torrent download function using threading"""
    try:
        # Try to import libtorrent
        try:
            import libtorrent as lt
        except ImportError:
            # Fallback for systems where libtorrent is not available
            print("libtorrent not available, marking torrent as failed")
            try:
                torrent = TorrentDownload.objects.get(id=torrent_id)
                torrent.status = 'failed'
                torrent.save()
            except TorrentDownload.DoesNotExist:
                pass
            return

        torrent = TorrentDownload.objects.get(id=torrent_id)
        torrent.status = 'downloading'
        torrent.save()
        
        print(f"Starting download for: {torrent.name}")
        
        # Create session with settings
        ses = lt.session()
        ses.listen_on(6881, 6891)
        
        # Configure session settings
        settings_pack = lt.session()
        settings_pack.user_agent = 'libtorrent/' + lt.version
        settings_pack.enable_upnp = True
        settings_pack.enable_natpmp = True
        ses.apply_settings(settings_pack)
        
        # Add DHT routers
        ses.add_dht_router("router.utorrent.com", 6881)
        ses.add_dht_router("router.bittorrent.com", 6881)
        ses.add_dht_router("dht.transmissionbt.com", 6881)
        
        # Add torrent
        params = {
            'url': torrent.magnet_link,
            'save_path': str(settings.TORRENT_DOWNLOAD_DIR)
        }
        
        handle = ses.add_torrent(params)
        
        # Wait for metadata with timeout
        timeout = 300  # 5 minutes timeout for metadata
        start_time = time.time()
        print(f"Waiting for metadata for torrent: {torrent.name}")
        
        while not handle.has_metadata():
            if time.time() - start_time > timeout:
                print(f"Metadata timeout for torrent {torrent_id}")
                torrent.status = 'failed'
                torrent.save()
                ses.remove_torrent(handle)
                return
                
            time.sleep(1)
            
            # Check if paused or cancelled
            try:
                torrent.refresh_from_db()
                if torrent.status == 'paused':
                    print(f"Torrent paused: {torrent.name}")
                    ses.remove_torrent(handle)
                    return
            except TorrentDownload.DoesNotExist:
                print(f"Torrent deleted: {torrent_id}")
                ses.remove_torrent(handle)
                return
        
        # Update torrent info
        info = handle.get_torrent_info()
        torrent.name = info.name()
        torrent.size = info.total_size()
        torrent.is_multi_file = info.num_files() > 1
        torrent.save()
        
        print(f"Metadata received. Starting download: {torrent.name} ({torrent.size_human})")
        
        # Download loop
        last_progress_update = 0
        while handle.status().progress < 1:
            time.sleep(2)
            
            # Check if paused or cancelled
            try:
                torrent.refresh_from_db()
                if torrent.status == 'paused':
                    print(f"Download paused: {torrent.name}")
                    ses.remove_torrent(handle)
                    return
            except TorrentDownload.DoesNotExist:
                print(f"Torrent deleted during download: {torrent_id}")
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
            
            # Log progress every 10%
            current_progress = int(torrent.progress * 10)
            if current_progress > last_progress_update:
                last_progress_update = current_progress
                print(f"Progress: {torrent.progress_percentage:.1f}% - {torrent.download_speed_human} - {torrent.name}")
        
        # Download completed
        torrent.status = 'completed'
        torrent.progress = 1.0
        torrent.completed_at = timezone.now()
        torrent.file_path = os.path.join(settings.TORRENT_DOWNLOAD_DIR, info.name())
        torrent.save()
        
        ses.remove_torrent(handle)
        print(f"Download completed: {torrent.name}")
        
        # Remove from active threads
        if torrent_id in download_threads:
            del download_threads[torrent_id]
        
    except Exception as e:
        print(f"Download error for {torrent_id}: {str(e)}")
        try:
            torrent = TorrentDownload.objects.get(id=torrent_id)
            torrent.status = 'failed'
            torrent.save()
        except TorrentDownload.DoesNotExist:
            pass
        
        # Remove from active threads
        if torrent_id in download_threads:
            del download_threads[torrent_id]

@require_http_methods(["GET", "POST"])
def add_torrent(request):
    """Add a new torrent download"""
    
    if request.method == 'POST':
        form = TorrentForm(request.POST)
        if form.is_valid():
            try:
                torrent = form.save(commit=False)
                torrent.name = form.cleaned_data.get('name', 'Unknown Torrent')
                torrent.save()
                
                # Start download in background thread
                thread = threading.Thread(target=download_torrent_sync, args=(str(torrent.id),))
                thread.daemon = True
                thread.start()
                
                # Track the thread
                download_threads[str(torrent.id)] = thread
                
                messages.success(request, f'Torrent "{torrent.name}" added successfully and download started!')
                return redirect('torrent_list')
                
            except Exception as e:
                messages.error(request, f'Error adding torrent: {str(e)}')
        else:
            # Display form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    
    return redirect('torrent_list')

@require_POST
def pause_torrent(request, torrent_id):
    """Pause a downloading torrent"""
    
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    if torrent.status in ['downloading', 'pending']:
        torrent.status = 'paused'
        torrent.save()
        messages.success(request, f'Torrent "{torrent.name}" has been paused.')
    else:
        messages.warning(request, f'Cannot pause torrent "{torrent.name}" in {torrent.get_status_display()} state.')
    
    return redirect('torrent_list')

@require_POST
def resume_torrent(request, torrent_id):
    """Resume a paused torrent"""
    
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    if torrent.status == 'paused':
        torrent.status = 'pending'
        torrent.save()
        
        # Start download in background thread
        thread = threading.Thread(target=download_torrent_sync, args=(str(torrent.id),))
        thread.daemon = True
        thread.start()
        
        # Track the thread
        download_threads[str(torrent.id)] = thread
        
        messages.success(request, f'Torrent "{torrent.name}" has been resumed.')
    else:
        messages.warning(request, f'Cannot resume torrent "{torrent.name}" in {torrent.get_status_display()} state.')
    
    return redirect('torrent_list')

@require_POST
def restart_torrent(request, torrent_id):
    """Restart a failed torrent"""
    
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    if torrent.status == 'failed':
        # Reset torrent state
        torrent.status = 'pending'
        torrent.progress = 0.0
        torrent.download_speed = 0.0
        torrent.upload_speed = 0.0
        torrent.downloaded = 0
        torrent.peers = 0
        torrent.seeds = 0
        torrent.eta = ''
        torrent.save()
        
        # Start download in background thread
        thread = threading.Thread(target=download_torrent_sync, args=(str(torrent.id),))
        thread.daemon = True
        thread.start()
        
        # Track the thread
        download_threads[str(torrent.id)] = thread
        
        messages.success(request, f'Torrent "{torrent.name}" has been restarted.')
    else:
        messages.warning(request, f'Cannot restart torrent "{torrent.name}" in {torrent.get_status_display()} state.')
    
    return redirect('torrent_list')

@require_POST
def delete_torrent(request, torrent_id):
    """Delete a torrent and its files"""
    
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    torrent_name = torrent.name
    
    # Stop any running download thread
    if str(torrent_id) in download_threads:
        del download_threads[str(torrent_id)]
    
    # Delete files if they exist
    files_deleted = False
    if torrent.file_path and os.path.exists(torrent.file_path):
        try:
            if os.path.isdir(torrent.file_path):
                shutil.rmtree(torrent.file_path)
                files_deleted = True
            else:
                os.remove(torrent.file_path)
                files_deleted = True
            
            # Also delete zip file if exists
            zip_path = f"{torrent.file_path}.zip"
            if os.path.exists(zip_path):
                os.remove(zip_path)
                
        except Exception as e:
            messages.error(request, f'Error deleting files: {str(e)}')
    
    # Delete database record
    torrent.delete()
    
    if files_deleted:
        messages.success(request, f'Torrent "{torrent_name}" and its files have been deleted successfully.')
    else:
        messages.success(request, f'Torrent "{torrent_name}" has been deleted successfully.')
    
    return redirect('torrent_list')

def download_file(request, torrent_id):
    """Download completed torrent files"""
    
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    if torrent.status != 'completed':
        messages.error(request, f'Torrent "{torrent.name}" is not completed yet. Current status: {torrent.get_status_display()}')
        return redirect('torrent_list')
    
    if not torrent.file_path:
        messages.error(request, f'File path not found for torrent "{torrent.name}".')
        return redirect('torrent_list')
    
    file_path = torrent.file_path
    
    if not os.path.exists(file_path):
        messages.error(request, f'File not found: "{torrent.name}". The file may have been moved or deleted.')
        return redirect('torrent_list')
    
    try:
        # For multi-file torrents, create and serve zip
        if torrent.is_multi_file and os.path.isdir(file_path):
            zip_path = f"{file_path}.zip"
            
            # Create zip file if it doesn't exist
            if not os.path.exists(zip_path):
                print(f"Creating zip file for: {torrent.name}")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(file_path):
                        for file in files:
                            file_full_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_full_path, file_path)
                            zipf.write(file_full_path, arcname)
                print(f"Zip file created: {zip_path}")
            
            # Serve zip file
            response = FileResponse(
                open(zip_path, 'rb'),
                as_attachment=True,
                filename=f"{torrent.name}.zip"
            )
            return response
        
        # For single files
        else:
            if os.path.isfile(file_path):
                response = FileResponse(
                    open(file_path, 'rb'),
                    as_attachment=True,
                    filename=os.path.basename(file_path)
                )
                return response
            else:
                messages.error(request, f'Invalid file type for torrent "{torrent.name}".')
                return redirect('torrent_list')
                
    except Exception as e:
        messages.error(request, f'Error serving file "{torrent.name}": {str(e)}')
        return redirect('torrent_list')

def get_torrent_status(request, torrent_id):
    """API endpoint to get real-time torrent status"""
    
    try:
        torrent = get_object_or_404(TorrentDownload, id=torrent_id)
        
        data = {
            'id': str(torrent.id),
            'name': torrent.name,
            'status': torrent.status,
            'status_display': torrent.get_status_display(),
            'progress': round(torrent.progress_percentage, 1),
            'download_speed': torrent.download_speed_human,
            'upload_speed': f"{torrent.format_bytes(torrent.upload_speed * 1024)}/s",
            'downloaded': torrent.downloaded_human,
            'size': torrent.size_human,
            'peers': torrent.peers,
            'seeds': torrent.seeds,
            'eta': torrent.eta or '∞',
            'created_at': torrent.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_multi_file': torrent.is_multi_file,
        }
        
        if torrent.completed_at:
            data['completed_at'] = torrent.completed_at.strftime('%Y-%m-%d %H:%M:%S')
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def torrent_detail(request, torrent_id):
    """Detailed view of a single torrent"""
    
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    # Get file list if torrent is completed and is multi-file
    files = []
    if torrent.status == 'completed' and torrent.is_multi_file and torrent.file_path and os.path.exists(torrent.file_path):
        try:
            for root, dirs, file_names in os.walk(torrent.file_path):
                for file_name in file_names:
                    file_path = os.path.join(root, file_name)
                    relative_path = os.path.relpath(file_path, torrent.file_path)
                    file_size = os.path.getsize(file_path)
                    files.append({
                        'name': file_name,
                        'path': relative_path,
                        'size': TorrentDownload.format_bytes(file_size),
                        'size_bytes': file_size,
                    })
        except Exception as e:
            print(f"Error reading files: {e}")
    
    context = {
        'torrent': torrent,
        'files': files,
    }
    
    return render(request, 'downloader/torrent_detail.html', context)

def cleanup_completed(request):
    """Remove all completed torrents"""
    
    if request.method == 'POST':
        completed_torrents = TorrentDownload.objects.filter(status='completed')
        count = completed_torrents.count()
        
        for torrent in completed_torrents:
            # Delete files
            if torrent.file_path and os.path.exists(torrent.file_path):
                try:
                    if os.path.isdir(torrent.file_path):
                        shutil.rmtree(torrent.file_path)
                    else:
                        os.remove(torrent.file_path)
                    
                    # Also delete zip file if exists
                    zip_path = f"{torrent.file_path}.zip"
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                except Exception as e:
                    print(f"Error deleting files for {torrent.name}: {e}")
        
        # Delete from database
        completed_torrents.delete()
        
        messages.success(request, f'Successfully removed {count} completed torrents and their files.')
    
    return redirect('torrent_list')

def cleanup_failed(request):
    """Remove all failed torrents"""
    
    if request.method == 'POST':
        failed_torrents = TorrentDownload.objects.filter(status='failed')
        count = failed_torrents.count()
        failed_torrents.delete()
        
        messages.success(request, f'Successfully removed {count} failed torrents.')
    
    return redirect('torrent_list')
