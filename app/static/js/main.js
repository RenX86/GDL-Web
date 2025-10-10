let refreshInterval;

// Show notification to user
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// Start a download
function startDownload() {
    const url = document.getElementById('mediaUrl').value.trim();
    const cookieFile = document.getElementById('cookieFile').files[0];
    
    if (!url) {
        alert('Please enter a valid URL');
        return;
    }

    // Basic URL validation
    try {
        new URL(url);
    } catch (error) {
        alert('Please enter a valid URL format');
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
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                document.getElementById('mediaUrl').value = '';
                document.getElementById('cookieFile').value = '';
                startRefreshing();
                // Show success message
                showNotification('Download started successfully!', 'success');
            } else {
                const errorMessage = data.error || data.message || 'Unknown error occurred';
                alert('Download failed: ' + errorMessage);
            }
        })
        .catch(error => {
            console.error('Request failed:', error);
            if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
                alert('Network connection failed. Please check your connection and try again.');
            } else {
                alert('Download failed: ' + error.message);
            }
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
        reader.onerror = (error) => {
            console.error('File reading error:', error);
            alert('Failed to read cookie file');
            downloadBtn.disabled = false;
            spinner.style.display = 'none';
        };
        reader.readAsText(cookieFile);
    } else {
        sendRequest(null);
    }
}

// Refresh download status
function refreshDownloads() {
    // Check if this is a new session
    if (!sessionStorage.getItem('downloadSessionActive')) {
        // Set session flag
        sessionStorage.setItem('downloadSessionActive', 'true');
        // Clear any existing downloads on the server
        fetch('/api/clear-history', { method: 'POST' })
            .then(response => response.json())
            .catch(error => console.error('Error clearing downloads:', error));
    }
    
    fetch('/api/downloads')
        .then(response => response.json())
        .then(data => {
            if (data.success && Array.isArray(data.data)) {
                updateDownloadsList(data.data);
            } else {
                console.warn('Invalid response format:', data);
                updateDownloadsList([]);
            }
        })
        .catch(error => {
            console.error('Error fetching downloads:', error);
            const downloadsContainer = document.getElementById('downloads-container');
            if (downloadsContainer) {
                downloadsContainer.innerHTML = '<div class="error-message">Failed to load downloads. Please refresh the page.</div>';
            }
        });
}

// Update the downloads list
function updateDownloadsList(downloads) {
    const downloadsList = document.getElementById('downloadsList');
    
    // The API returns {success: true, data: [...]} where data is the array of downloads
    const items = Array.isArray(downloads) ? downloads : [];

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
    
    const validItems = items.filter(download => download && typeof download === 'object' && download.id);
    
    const html = validItems
        .sort((a, b) => new Date(b.start_time) - new Date(a.start_time))
        // Use the real download.id from backend instead of array index
        .map((download) => createDownloadCard(download))
        .join('');
    
    downloadsList.innerHTML = html;
    
    // Add event listeners to filter buttons
    setupFilterButtons();
}

// Delete a download
function deleteDownload(downloadId) {
    if (!downloadId) {
        console.error('Invalid download ID');
        return;
    }
    
    if (confirm('Are you sure you want to delete this download?')) {
        fetch(`/api/downloads/${downloadId}`, { method: 'DELETE' })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    refreshDownloads();
                } else {
                    alert('Failed to delete download: ' + (data.message || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error deleting download:', error);
                alert('Network error occurred while deleting download');
            });
    }
}

// Create a download card
function createDownloadCard(download) {
    // Validate required fields
    if (!download || !download.id) {
        console.error('Invalid download data:', download);
        return '<div></div>'; // Return empty HTML string
    }
    
    // Normalize status to expected values
    const status = download.status || 'pending';
    const statusClass = status === 'completed' ? 'status-completed' : 
                       status === 'error' || status === 'failed' ? 'status-error' : 'status-in-progress';
    
    // Safely get values with defaults
    const progress = Math.max(0, Math.min(100, parseInt(download.progress) || 0));
    const message = download.message || download.error || '';
    const url = download.url || 'Unknown URL';
    const filesDownloaded = download.files_downloaded || 0;
    const totalFiles = download.total_files || 0;
    
    // Format dates safely
    let startTime = 'N/A';
    let endTime = null;
    
    try {
        if (download.start_time) {
            startTime = new Date(download.start_time).toLocaleString();
        }
        if (download.end_time) {
            endTime = new Date(download.end_time).toLocaleString();
        }
    } catch (dateError) {
        console.warn('Invalid date format in download:', download);
    }
    
    // Return HTML string instead of DOM element
    return `
        <div class="download-card" data-download-id="${download.id}" data-status="${status}">
            <div class="download-header">
                <h3 title="${url}">${url.length > 50 ? url.substring(0, 50) + '...' : url}</h3>
                <span class="status-badge ${statusClass}">${status}</span>
            </div>
            <div class="download-info">
                <p><strong>Started:</strong> ${startTime}</p>
                ${endTime ? `<p><strong>Completed:</strong> ${endTime}</p>` : ''}
                <p><strong>Progress:</strong> ${progress}%</p>
                ${totalFiles > 0 ? `<p><strong>Files:</strong> ${filesDownloaded}/${totalFiles}</p>` : ''}
                ${message ? `<p><strong>Message:</strong> ${message}</p>` : ''}
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${progress}%"></div>
            </div>
            <div class="download-actions">
                ${status === 'completed' ? `<button class="btn download-btn" onclick="showDownloadFiles('${download.id}')">View Files</button>` : ''}
                <button class="btn download-btn" onclick="deleteDownload('${download.id}')" 
                        ${status === 'downloading' ? 'disabled title="Cannot delete while downloading"' : ''}>
                    Delete
                </button>
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
    if (!confirm('Are you sure you want to clear all completed downloads?')) {
        return;
    }
    
    fetch('/api/downloads/clear', {
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
            alert('Failed to clear history: ' + (data.message || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error clearing history:', error);
        alert('Network error occurred while clearing history');
    });
}

// Add filter functionality
function setupFilterButtons() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    
    filterButtons.forEach(button => {
        // Prevent adding duplicate listeners across refreshes
        if (button.dataset.listenerAttached === 'true') return;
        
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            filterButtons.forEach(btn => btn.classList.remove('active'));
            // Add active class to clicked button
            this.classList.add('active');
            
            const filter = this.getAttribute('data-filter');
            filterDownloads(filter);
        });
        
        button.dataset.listenerAttached = 'true';
    });
}

// Filter downloads based on status
function filterDownloads(filter) {
    const downloadCards = document.querySelectorAll('.download-card');
    
    downloadCards.forEach(card => {
        const cardStatus = card.getAttribute('data-status');
        
        if (filter === 'all' || filter === cardStatus) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

// Show files for a completed download
function showDownloadFiles(downloadId) {
    if (!downloadId) {
        console.error('Invalid download ID');
        return;
    }

    fetch(`/api/files/${downloadId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.files) {
                displayDownloadFiles(downloadId, data.files);
            } else {
                alert('Failed to load files: ' + (data.message || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error fetching files:', error);
            alert('Failed to load files: ' + error.message);
        });
}

// Display download files in a modal or popup
function displayDownloadFiles(downloadId, files) {
    // Create modal overlay
    const modal = document.createElement('div');
    modal.className = 'file-modal-overlay';
    modal.innerHTML = `
        <div class="file-modal">
            <div class="file-modal-header">
                <h3>Downloaded Files</h3>
                <button class="close-btn" onclick="this.closest('.file-modal-overlay').remove()">&times;</button>
            </div>
            <div class="file-modal-content">
                ${files.length === 0 ? 
                    '<p class="no-files">No files found for this download.</p>' :
                    `<div class="file-list">
                        ${files.map(file => `
                            <div class="file-item">
                                <div class="file-info">
                                    <span class="file-name">${file.name}</span>
                                    <span class="file-size">${file.size}</span>
                                </div>
                                <button class="btn download-btn" 
                                        onclick="downloadFile('${downloadId}', '${file.name}')">
                                    Download
                                </button>
                            </div>
                        `).join('')}
                    </div>`
                }
            </div>
        </div>
    `;
    
    // Add modal styles if not already present
    if (!document.getElementById('modal-styles')) {
        const style = document.createElement('style');
        style.id = 'modal-styles';
        style.textContent = `
            .file-modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 1000;
            }
            .file-modal {
                background: white;
                border-radius: 8px;
                width: 90%;
                max-width: 600px;
                max-height: 80vh;
                overflow: hidden;
            }
            .file-modal-header {
                padding: 20px;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .file-modal-header h3 {
                margin: 0;
            }
            .close-btn {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
            }
            .file-modal-content {
                padding: 20px;
                max-height: calc(80vh - 100px);
                overflow-y: auto;
            }
            .file-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .file-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px;
                border: 1px solid #eee;
                border-radius: 4px;
            }
            .file-info {
                display: flex;
                flex-direction: column;
            }
            .file-name {
                font-weight: 500;
                margin-bottom: 2px;
            }
            .file-size {
                font-size: 12px;
                color: #666;
            }
            .no-files {
                text-align: center;
                color: #666;
                margin: 20px 0;
            }
            .file-modal .download-btn {
                padding: 5px 10px;
                font-size: 12px;
                width: auto;
                height: auto;
                min-width: 80px;
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(modal);
}

// Download a specific file
function downloadFile(downloadId, filename) {
    if (!downloadId || !filename) {
        console.error('Invalid download ID or filename');
        return;
    }

    // Create a download link and trigger it
    const downloadUrl = `/api/download-file/${downloadId}/${filename}`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename; // This will suggest the filename to the browser
    link.style.display = 'none';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showNotification(`Downloading ${filename}...`, 'info');
}

// Allow Enter key to start download
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('mediaUrl').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startDownload();
        }
    });
    
    // Setup filter buttons on initial load
    setupFilterButtons();
    
    // Set "All" filter as active by default
    const allFilterBtn = document.querySelector('.filter-btn[data-filter="all"]');
    if (allFilterBtn) {
        allFilterBtn.classList.add('active');
    }
    
    // Initial load
    refreshDownloads();
});
