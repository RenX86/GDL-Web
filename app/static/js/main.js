let refreshInterval;

// Start a download
function startDownload() {
    const url = document.getElementById('mediaUrl').value.trim();
    const cookieFile = document.getElementById('cookieFile').files[0];
    
    if (!url) {
        alert('Please enter a valid URL');
        return;
    }

    const downloadBtn = document.querySelector('.download-btn');
    const spinner = document.getElementById('loadingSpinner');
    
    // Disable button and show spinner
    downloadBtn.disabled = true;
    spinner.style.display = 'inline-block';

    const sendRequest = (cookiesContent) => {
        fetch('/api/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url, cookies: cookiesContent })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('mediaUrl').value = '';
                document.getElementById('cookieFile').value = '';
                startRefreshing();
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Network error occurred');
        })
        .finally(() => {
            downloadBtn.disabled = false;
            spinner.style.display = 'none';
        });
    };

    if (cookieFile) {
        const reader = new FileReader();
        reader.onload = (e) => {
            sendRequest(e.target.result);
        };
        reader.readAsText(cookieFile);
    } else {
        sendRequest(null);
    }
}

// Refresh download status
function refreshDownloads() {
    fetch('/api/downloads')
        .then(response => response.json())
        .then(data => {
            updateDownloadsList(data);
        })
        .catch(error => {
            console.error('Error fetching downloads:', error);
        });
}

// Update the downloads list
function updateDownloadsList(downloads) {
    const downloadsList = document.getElementById('downloadsList');
    
    if (!downloads || !downloads.data || Object.keys(downloads.data).length === 0) {
        downloadsList.innerHTML = '<div class="empty-state">No downloads yet. Enter a URL above to get started!</div>';
        return;
    }
    
    const html = Object.entries(downloads.data)
        .sort(([,a], [,b]) => new Date(b.start_time) - new Date(a.start_time))
        .map(([id, download]) => createDownloadCard(id, download))
        .join('');
    
    downloadsList.innerHTML = html;
}

// Create a download card
function createDownloadCard(id, download) {
    const progress = download.progress || 0;
    const status = download.status || 'unknown';
    const statusClass = `status-${status}`;
    const message = download.message || 'No message available';
    const url = download.url || 'No URL available';
    const startTime = download.start_time ? new Date(download.start_time).toLocaleString() : 'Unknown';
    
    return `
        <div class="status-card">
            <div class="status-header">
                <span class="status-id">ID: ${id}</span>
                <span class="status-badge ${statusClass}">${status}</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${progress}%"></div>
            </div>
            <div><strong>Message:</strong> ${message}</div>
            <div class="url-display"><strong>URL:</strong> ${url}</div>
            <div><strong>Started:</strong> ${startTime}</div>
        </div>
    `;
}

// Start refreshing downloads
function startRefreshing() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    
    refreshInterval = setInterval(refreshDownloads, 2000);
    refreshDownloads(); // Refresh immediately
}

// Clear download history
function clearHistory() {
    if (!confirm('Are you sure you want to clear the download history?')) {
        return;
    }
    
    fetch('/api/clear-history', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            refreshDownloads();
        } else {
            alert('Error clearing history');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Network error occurred');
    });
}

// Allow Enter key to start download
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('mediaUrl').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startDownload();
        }
    });
    
    // Initial load
    refreshDownloads();
});