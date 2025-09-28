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
    
    // Normalize API response: backend returns an array of download objects
    const rawData = (downloads && downloads.data) ? downloads.data : [];
    const items = Array.isArray(rawData) ? rawData : Object.values(rawData);

    if (!items || items.length === 0) {
        downloadsList.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                <p>No downloads yet. Enter a URL above to get started!</p>
            </div>`;
        return;
    }
    
    const html = items
        .sort((a, b) => new Date(b.start_time) - new Date(a.start_time))
        // Use the real download.id from backend instead of array index
        .map((download) => createDownloadCard(download.id || 'unknown', download))
        .join('');
    
    downloadsList.innerHTML = html;
    
    // Add event listeners to filter buttons
    setupFilterButtons();
}

// Create a download card
function createDownloadCard(id, download) {
    const rawProgress = typeof download.progress === 'number' ? download.progress : parseFloat(download.progress) || 0;
    const progress = Math.max(0, Math.min(100, rawProgress));
    const status = download.status || 'pending';
    let statusClass = '';
    let badgeText = '';
    
    // Map status to appropriate class and user-friendly badge text
    switch(status) {
        case 'completed':
            statusClass = 'completed';
            badgeText = 'COMPLETED';
            break;
        case 'in_progress':
        case 'downloading':
        case 'starting':
        case 'processing':
        case 'retrying':
            statusClass = 'in-progress';
            badgeText = 'IN PROGRESS';
            break;
        case 'error':
        case 'failed':
        case 'cancelled':
            statusClass = 'error';
            badgeText = 'FAILED';
            break;
        default:
            statusClass = 'pending';
            badgeText = 'PENDING';
    }
    
    const message = download.message || 'No message available';
    const url = download.url || 'No URL available';
    const startTime = download.start_time ? new Date(download.start_time).toLocaleString() : 'Unknown';
    
    return `
        <div class="status-card" data-status="${statusClass}">
            <div class="status-header">
                <div class="status-title">${url}</div>
                <span class="status-badge ${statusClass}">${badgeText}</span>
            </div>
            <div class="progress-container">
                <div class="progress-bar" style="width: ${progress}%">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
            </div>
            <div class="status-details">
                <div><strong>ID:</strong> ${id}</div>
                <div><strong>Message:</strong> ${message}</div>
                <div><strong>Started:</strong> ${startTime}</div>
            </div>
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

// Add filter functionality
function setupFilterButtons() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const statusCards = document.querySelectorAll('.status-card');
    
    filterButtons.forEach(button => {
        // Prevent adding duplicate listeners across refreshes
        if (button.dataset.listenerAttached === 'true') return;
        button.addEventListener('click', () => {
            // Remove active class from all buttons
            filterButtons.forEach(btn => btn.classList.remove('active'));
            
            // Add active class to clicked button
            button.classList.add('active');
            
            const filter = button.getAttribute('data-filter');
            
            // Show/hide cards based on filter
            statusCards.forEach(card => {
                if (filter === 'all' || card.getAttribute('data-status') === filter) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
        button.dataset.listenerAttached = 'true';
    });
}

// Allow Enter key to start download
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('mediaUrl').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startDownload();
        }
    });
    
    // Setup filter buttons on initial load (avoid duplicate listeners)
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(button => {
        if (button.dataset.listenerAttached === 'true') return;
        button.addEventListener('click', function() {
            filterButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
        });
        button.dataset.listenerAttached = 'true';
    });
    
    // Set "All" filter as active by default
    const allFilterBtn = document.querySelector('.filter-btn[data-filter="all"]');
    if (allFilterBtn) {
        allFilterBtn.classList.add('active');
    }
    
    // Initial load
    refreshDownloads();
});