from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404, FileResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.core.paginator import Paginator
import os
import shutil
import zipfile
from .models import TorrentDownload
from .forms import TorrentForm
from .tasks import download_torrent, create_zip_file

class TorrentListView(ListView):
    model = TorrentDownload
    template_name = 'downloader/index.html'
    context_object_name = 'torrents'
    paginate_by = 10
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = TorrentForm()
        context['stats'] = {
            'total': TorrentDownload.objects.count(),
            'downloading': TorrentDownload.objects.filter(status='downloading').count(),
            'completed': TorrentDownload.objects.filter(status='completed').count(),
            'failed': TorrentDownload.objects.filter(status='failed').count(),
        }
        return context

def add_torrent(request):
    if request.method == 'POST':
        form = TorrentForm(request.POST)
        if form.is_valid():
            torrent = form.save(commit=False)
            torrent.name = form.cleaned_data.get('name', 'Unknown Torrent')
            torrent.save()
            
            # Start download task
            download_torrent.delay(str(torrent.id))
            
            messages.success(request, f'Torrent "{torrent.name}" added successfully!')
            return redirect('torrent_list')
        else:
            messages.error(request, 'Please enter a valid magnet link.')
    
    return redirect('torrent_list')

@require_POST
def pause_torrent(request, torrent_id):
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    if torrent.status == 'downloading':
        torrent.status = 'paused'
        torrent.save()
        messages.success(request, f'Torrent "{torrent.name}" paused.')
    return redirect('torrent_list')

@require_POST
def resume_torrent(request, torrent_id):
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    if torrent.status == 'paused':
        torrent.status = 'pending'
        torrent.save()
        download_torrent.delay(str(torrent.id))
        messages.success(request, f'Torrent "{torrent.name}" resumed.')
    return redirect('torrent_list')

@require_POST
def delete_torrent(request, torrent_id):
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    # Delete files if they exist
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
            messages.error(request, f'Error deleting files: {str(e)}')
    
    torrent_name = torrent.name
    torrent.delete()
    messages.success(request, f'Torrent "{torrent_name}" deleted successfully.')
    return redirect('torrent_list')

def download_file(request, torrent_id):
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    
    if torrent.status != 'completed' or not torrent.file_path:
        messages.error(request, 'File not ready for download.')
        return redirect('torrent_list')
    
    file_path = torrent.file_path
    
    if not os.path.exists(file_path):
        messages.error(request, 'File not found.')
        return redirect('torrent_list')
    
    # For multi-file torrents, create and serve zip
    if torrent.is_multi_file and os.path.isdir(file_path):
        zip_path = f"{file_path}.zip"
        
        if not os.path.exists(zip_path):
            # Create zip file
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(file_path):
                        for file in files:
                            file_full_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_full_path, file_path)
                            zipf.write(file_full_path, arcname)
            except Exception as e:
                messages.error(request, f'Error creating zip file: {str(e)}')
                return redirect('torrent_list')
        
        try:
            response = FileResponse(
                open(zip_path, 'rb'),
                as_attachment=True,
                filename=f"{torrent.name}.zip"
            )
            return response
        except Exception as e:
            messages.error(request, f'Error serving file: {str(e)}')
            return redirect('torrent_list')
    
    # For single files
    else:
        try:
            response = FileResponse(
                open(file_path, 'rb'),
                as_attachment=True,
                filename=os.path.basename(file_path)
            )
            return response
        except Exception as e:
            messages.error(request, f'Error serving file: {str(e)}')
            return redirect('torrent_list')

def get_torrent_status(request, torrent_id):
    torrent = get_object_or_404(TorrentDownload, id=torrent_id)
    data = {
        'status': torrent.status,
        'progress': torrent.progress_percentage,
        'download_speed': torrent.download_speed_human,
        'upload_speed': f"{torrent.format_bytes(torrent.upload_speed * 1024)}/s",
        'downloaded': torrent.downloaded_human,
        'size': torrent.size_human,
        'peers': torrent.peers,
        'seeds': torrent.seeds,
        'eta': torrent.eta,
    }
    return JsonResponse(data)