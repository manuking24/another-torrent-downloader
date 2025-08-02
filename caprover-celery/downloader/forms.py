from django import forms
from .models import TorrentDownload
import re

class TorrentForm(forms.ModelForm):
    class Meta:
        model = TorrentDownload
        fields = ['magnet_link']
        widgets = {
            'magnet_link': forms.Textarea(attrs={
                'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
                'rows': 4,
                'placeholder': 'Paste your magnet link here...'
            })
        }
    
    def clean_magnet_link(self):
        magnet_link = self.cleaned_data['magnet_link'].strip()
        if not magnet_link.startswith('magnet:'):
            raise forms.ValidationError('Please enter a valid magnet link.')
        
        # Extract torrent name from magnet link
        name_match = re.search(r'dn=([^&]+)', magnet_link)
        if name_match:
            import urllib.parse
            self.cleaned_data['name'] = urllib.parse.unquote(name_match.group(1))
        else:
            self.cleaned_data['name'] = 'Unknown Torrent'
        
        return magnet_link
