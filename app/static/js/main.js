let refreshInterval;
let statusFilter = 'all'; // Default filter

// --- Bootstrap Components ---
// Helper to show Bootstrap Toasts
function showToast(title, message, type = 'info') {
    const toastEl = document.getElementById('liveToast');
    const toastTitle = document.getElementById('toastTitle');
    const toastMessage = document.getElementById('toastMessage');
    const toastIcon = document.getElementById('toastIcon');

    toastTitle.textContent = title;
    toastMessage.textContent = message;

    // Reset classes
    toastIcon.className = 'bi me-2';
    
    if (type === 'success') {
        toastIcon.classList.add('bi-check-circle-fill', 'text-success');
    } else if (type === 'error') {
        toastIcon.classList.add('bi-exclamation-octagon-fill', 'text-danger');
    } else if (type === 'warning') {
        toastIcon.classList.add('bi-exclamation-triangle-fill', 'text-warning');
    } else {
        toastIcon.classList.add('bi-info-circle-fill', 'text-primary');
    }

    const toast = bootstrap.Toast.getOrCreateInstance(toastEl);
    toast.show();
}

// --- API Interactions ---

function startDownload() {
    const urlInput = document.getElementById('mediaUrl');
    const cookieInput = document.getElementById('cookieFile');
    const startBtn = document.getElementById('startBtn');
    const spinner = document.getElementById('loadingSpinner');
    const btnText = startBtn.querySelector('.btn-text');

    const url = urlInput.value.trim();
    
    if (!url) {
        showToast('Input Error', 'Please enter a valid URL', 'warning');
        return;
    }

    // UI Loading State
    startBtn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.textContent = 'Starting...';

    const sendRequest = (cookiesContent) => {
        fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url, cookies: cookiesContent })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                urlInput.value = '';
                cookieInput.value = '';
                showToast('Success', 'Download started successfully', 'success');
                // SSE handles refresh
                // Ensure we are on the 'all' or 'active' filter to see it
                if (statusFilter === 'completed' || statusFilter === 'error') {
                   document.getElementById('filterAll').click();
                }
            } else {
                showToast('Error', data.message || 'Failed to start download', 'error');
            }
        })
        .catch(err => {
            console.error(err);
            showToast('Network Error', 'Could not connect to server', 'error');
        })
        .finally(() => {
            startBtn.disabled = false;
            spinner.classList.add('d-none');
            btnText.innerHTML = '<i class="bi bi-download me-2"></i>Start Download';
        });
    };

    // Handle File Reading
    if (cookieInput.files.length > 0) {
        const reader = new FileReader();
        reader.onload = (e) => sendRequest(e.target.result);
        reader.onerror = () => {
            showToast('File Error', 'Failed to read cookie file', 'error');
            startBtn.disabled = false;
            spinner.classList.add('d-none');
            btnText.innerHTML = '<i class="bi bi-download me-2"></i>Start Download';
        };
        reader.readAsText(cookieInput.files[0]);
    } else {
        sendRequest(null);
    }
}

function refreshDownloads() {
    // Ensure session is marked active
    if (!sessionStorage.getItem('downloadSessionActive')) {
        sessionStorage.setItem('downloadSessionActive', 'true');
    }

    fetch('/api/downloads')
        .then(response => response.json())
        .then(data => {
            if (data.success && Array.isArray(data.data)) {
                renderDownloads(data.data);
            }
        })
        .catch(console.error);
}

function deleteDownload(downloadId) {
    if (!confirm('Are you sure you want to delete this download?')) return;

    fetch(`/api/downloads/${downloadId}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Deleted', 'Download removed', 'success');
                // SSE handles refresh
            } else {
                showToast('Error', data.message, 'error');
            }
        })
        .catch(() => showToast('Error', 'Network error during deletion', 'error'));
}

function clearSession() {
    // Show custom modal instead of browser confirm
    const modal = new bootstrap.Modal(document.getElementById('clearSessionModal'));
    modal.show();
}

// --- File Preview Logic ---

function openPreview(url) {
    const modalEl = document.getElementById('imagePreviewModal');
    const img = document.getElementById('previewImage');
    
    // Set image source
    img.src = url;
    
    // Show modal
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
    
    // Clear src on hide to stop memory leaks / flash of old image
    modalEl.addEventListener('hidden.bs.modal', () => {
        img.src = '';
    }, { once: true });
}

function openVideo(url) {
    const modalEl = document.getElementById('videoPreviewModal');
    const video = document.getElementById('previewVideo');
    
    // Set video source
    video.src = url;
    
    // Show modal
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
    
    // Stop playback on hide
    modalEl.addEventListener('hidden.bs.modal', () => {
        video.pause();
        video.src = '';
        video.load();
    }, { once: true });
}

function showFiles(downloadId) {
    const listContainer = document.getElementById('filesListContainer');
    listContainer.innerHTML = '<div class="text-center p-4"><div class="spinner-border text-primary"></div></div>';
    
    const modal = new bootstrap.Modal(document.getElementById('filesModal'));
    modal.show();

    fetch(`/api/files/${downloadId}`)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.files) {
                if (data.files.length === 0) {
                    listContainer.innerHTML = '<div class="p-4 text-center text-muted">No files found.</div>';
                    return;
                }
                
                // Header with Zip Download Button
                const headerHtml = `
                    <div class="d-flex justify-content-between align-items-center p-3 border-bottom bg-body-secondary sticky-top" style="z-index: 10;">
                        <span class="text-muted small fw-medium">${data.files.length} files found</span>
                        <a href="/api/download-zip/${downloadId}" class="btn btn-primary btn-sm">
                            <i class="bi bi-file-earmark-zip me-1"></i> Download All (Zip)
                        </a>
                    </div>
                `;

                // Helper to check file types
                const isImage = (filename) => /\.(jpg|jpeg|png|gif|webp|bmp|svg)$/i.test(filename);
                const isVideo = (filename) => /\.(mp4|webm|ogg|mov)$/i.test(filename);

                const gridHtml = `
                    <div class="file-grid">
                        ${data.files.map(file => {
                            const isImg = isImage(file.name);
                            const isVid = isVideo(file.name);
                            const downloadUrl = `/api/download-file/${downloadId}/${file.name}`;
                            const previewUrl = `${downloadUrl}?preview=true`;
                            
                            // Determine Click Action & Class
                            let clickAction = '';
                            let cursorClass = '';
                            let thumbnailContent = '<i class="bi bi-file-earmark-text file-icon-placeholder"></i>';

                            if (isImg) {
                                clickAction = `onclick="openPreview('${previewUrl}')"`;
                                cursorClass = 'cursor-pointer';
                                thumbnailContent = `<img src="${previewUrl}" class="file-thumbnail" loading="lazy" alt="${file.name}">`;
                            } else if (isVid) {
                                clickAction = `onclick="openVideo('${previewUrl}')"`;
                                cursorClass = 'cursor-pointer';
                                thumbnailContent = `
                                    <div class="position-relative w-100 h-100 d-flex align-items-center justify-content-center bg-dark">
                                        <i class="bi bi-play-circle-fill text-white fs-1 position-absolute z-2"></i>
                                        <video src="${previewUrl}#t=0.1" class="file-thumbnail opacity-50" style="object-fit: cover;"></video>
                                    </div>
                                `;
                            }
                            
                            return `
                                <div class="file-card ${cursorClass}" title="${file.name}">
                                    <div class="file-thumbnail-container" ${clickAction}>
                                        ${thumbnailContent}
                                    </div>
                                    <div class="file-card-body border-top">
                                        <div class="text-truncate fw-medium">${file.name}</div>
                                        <div class="d-flex justify-content-between align-items-center mt-1">
                                            <span class="text-muted small" style="font-size: 0.7rem;">${file.size || ''}</span>
                                            <a href="${downloadUrl}" class="btn btn-sm btn-light py-0 px-1" download onclick="event.stopPropagation();">
                                                <i class="bi bi-download"></i>
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
                
                listContainer.innerHTML = headerHtml + gridHtml;
            } else {
                listContainer.innerHTML = '<div class="alert alert-warning m-3">Could not load files.</div>';
            }
        })
        .catch(() => {
            listContainer.innerHTML = '<div class="alert alert-danger m-3">Network error loading files.</div>';
        });
}

// --- Rendering & Logic ---

function normalizeStatus(status) {
    status = (status || 'pending').toLowerCase();
    if (['completed', 'finished'].includes(status)) return 'completed';
    if (['error', 'failed'].includes(status)) return 'error';
    if (['cancelled', 'canceled'].includes(status)) return 'cancelled';
    if (['starting', 'downloading', 'processing', 'in_progress', 'retrying'].includes(status)) return 'downloading';
    return 'pending';
}

function renderDownloads(downloads) {
    const list = document.getElementById('downloadsList');
    
    // Check for initial loading state and clear it
    const loadingState = list.querySelector('.text-center.py-5.text-muted');
    if (loadingState && loadingState.innerText.includes('Connecting')) {
        list.innerHTML = '';
    }
    
    // Sort: Newest first
    const sorted = downloads.sort((a, b) => new Date(b.start_time || 0) - new Date(a.start_time || 0));

    // Filter logic
    const filtered = sorted.filter(d => {
        const s = normalizeStatus(d.status);
        if (statusFilter === 'all') return true;
        if (statusFilter === 'in-progress') return ['starting', 'downloading', 'processing', 'retrying'].includes(s);
        if (statusFilter === 'completed') return s === 'completed';
        if (statusFilter === 'error') return ['error', 'cancelled'].includes(s);
        return true;
    });

    if (filtered.length === 0) {
        if (!document.querySelector('.empty-state')) {
            list.innerHTML = `
                <div class="empty-state animate__animated animate__fadeIn">
                    <i class="bi bi-inbox"></i>
                    <p>No downloads yet.</p>
                </div>`;
        }
        return;
    }

    // Remove empty state if it exists
    const emptyState = list.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    // 1. Create a Set of current IDs for efficient lookup
    const currentIds = new Set(filtered.map(d => d.id));

    // 2. Remove items that are no longer in the filtered list
    Array.from(list.children).forEach(child => {
        if (child.id && !currentIds.has(child.id.replace('card-', ''))) {
            child.classList.remove('animate__fadeInUp');
            child.classList.add('animate__fadeOut');
            setTimeout(() => child.remove(), 500);
        }
    });

    // 3. Update existing items or Add new ones
    filtered.forEach(d => {
        const cardId = `card-${d.id}`;
        let card = document.getElementById(cardId);
        
        if (card) {
            // --- UPDATE EXISTING CARD ---
            updateCard(card, d);
        } else {
            // --- ADD NEW CARD ---
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = createCardHtml(d);
            const newCard = tempDiv.firstElementChild;
            newCard.id = cardId; // Ensure ID is set on the element
            list.appendChild(newCard);
        }
    });
}

function updateCard(card, d) {
    const status = normalizeStatus(d.status);
    const progress = Math.round(d.progress || 0);
    
    // Update Progress Text
    const progressText = card.querySelector('.progress-text');
    if (progressText && progressText.textContent !== `${progress}%`) {
        progressText.textContent = `${progress}%`;
    }

    // Update File Count
    const fileCountText = card.querySelector('.file-count-text');
    const newFileCount = d.total_files ? `${d.files_downloaded}/${d.total_files} files` : '';
    if (fileCountText && fileCountText.textContent !== newFileCount) {
        fileCountText.textContent = newFileCount;
    }

    // Update Progress Bar
    const progressBar = card.querySelector('.progress-bar');
    if (progressBar) {
        const currentWidth = progressBar.style.width;
        if (currentWidth !== `${progress}%`) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);
        }
        
        // Update Color Class
        progressBar.className = `progress-bar ${status === 'completed' ? 'bg-success' : (status === 'error' ? 'bg-danger' : '')}`;
    }

    // Update Status Badge (Only if status changed to avoid flicker)
    const currentStatus = card.dataset.status;
    if (currentStatus !== status) {
        card.dataset.status = status; // Store status to detect changes
        
        const badgeContainer = card.querySelector('.status-badge-container');
        if (badgeContainer) {
            badgeContainer.innerHTML = getStatusBadgeHtml(status);
        }

        const actionContainer = card.querySelector('.action-btn-container');
        if (actionContainer) {
            actionContainer.innerHTML = getActionBtnsHtml(status, d.id);
        }
    }
    
    // Update Message
    const msgContainer = card.querySelector('.message-container');
    const newMessage = d.message || d.error || '';
    if (msgContainer) {
        if (newMessage && msgContainer.textContent !== newMessage) {
            msgContainer.innerHTML = `<div class="alert alert-light border py-1 px-2 small mb-3 text-muted text-truncate"><i class="bi bi-terminal me-1"></i>${newMessage}</div>`;
        } else if (!newMessage) {
            msgContainer.innerHTML = '';
        }
    }
}

function getStatusBadgeHtml(status) {
    switch(status) {
        case 'completed': return '<span class="badge bg-success-subtle">Completed</span>';
        case 'error': return '<span class="badge bg-danger-subtle text-danger">Failed</span>';
        case 'downloading': return '<span class="badge bg-primary-subtle"><span class="spinner-grow spinner-grow-sm me-1" style="width: 0.5rem; height: 0.5rem;"></span> In Progress</span>';
        default: return '<span class="badge bg-secondary-subtle text-secondary">Cancelled</span>';
    }
}

function getActionBtnsHtml(status, id) {
    switch(status) {
        case 'completed':
            return `
                <button onclick="showFiles('${id}')" class="btn btn-sm btn-outline-primary">
                    <i class="bi bi-folder2-open me-1"></i> Files
                </button>
                <button onclick="deleteDownload('${id}')" class="btn btn-sm btn-outline-danger">
                    <i class="bi bi-trash"></i>
                </button>`;
        case 'error':
            return `
                <button onclick="deleteDownload('${id}')" class="btn btn-sm btn-outline-danger">
                    <i class="bi bi-trash"></i> Delete
                </button>`;
        case 'downloading':
            return `
                <button disabled class="btn btn-sm btn-light text-muted">
                    <i class="bi bi-hourglass-split"></i> Processing...
                </button>`;
        default:
            return `
                <button onclick="deleteDownload('${id}')" class="btn btn-sm btn-outline-danger">
                    <i class="bi bi-trash"></i>
                </button>`;
    }
}

function createCardHtml(d) {
    const status = normalizeStatus(d.status);
    const progress = Math.round(d.progress || 0);
    const id = d.id;
    
    // Initial HTML generation
    const statusBadge = getStatusBadgeHtml(status);
    const actionBtns = getActionBtnsHtml(status, id);
    const message = d.message || d.error || '';
    const fileCount = d.total_files ? `${d.files_downloaded}/${d.total_files} files` : '';

    return `
        <div class="card shadow-sm download-item animate__animated animate__fadeInUp" data-status="${status}">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="card-subtitle text-truncate text-body-secondary" style="max-width: 70%;" title="${d.url}">
                        <i class="bi bi-link-45deg me-1"></i>${d.url}
                    </h6>
                    <div class="status-badge-container">${statusBadge}</div>
                </div>
                
                <div class="d-flex justify-content-between align-items-center mb-1 small">
                    <span class="fw-bold fs-5 text-body-emphasis progress-text">${progress}%</span>
                    <span class="text-muted file-count-text">${fileCount}</span>
                </div>
                
                <div class="progress mb-3">
                    <div class="progress-bar ${status === 'completed' ? 'bg-success' : (status === 'error' ? 'bg-danger' : '')}" 
                         role="progressbar" 
                         style="width: ${progress}%" 
                         aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100">
                    </div>
                </div>
                
                <div class="message-container">
                    ${message ? `<div class="alert alert-light border py-1 px-2 small mb-3 text-muted text-truncate"><i class="bi bi-terminal me-1"></i>${message}</div>` : ''}
                </div>

                <div class="d-flex justify-content-end gap-2 action-btn-container">
                    ${actionBtns}
                </div>
            </div>
        </div>
    `;
}

// --- Server-Sent Events (SSE) Logic ---

function setupEventStream() {
    const evtSource = new EventSource("/api/events");

    evtSource.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        switch (msg.type) {
            case 'initial':
                renderDownloads(msg.data);
                break;
            case 'update':
                updateOrAddCard(msg.data);
                break;
            case 'delete':
                removeCard(msg.data.id);
                break;
            case 'clear':
                document.getElementById('downloadsList').innerHTML = '';
                renderDownloads([]); // Show empty state
                break;
        }
    };

    evtSource.onerror = (err) => {
        console.error("EventSource failed:", err);
        // EventSource automatically retries, but we can log connection status
    };
}

function updateOrAddCard(d) {
    const list = document.getElementById('downloadsList');
    const cardId = `card-${d.id}`;
    let card = document.getElementById(cardId);
    
    // Remove empty state if present
    const emptyState = list.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    if (card) {
        updateCard(card, d);
    } else {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = createCardHtml(d);
        const newCard = tempDiv.firstElementChild;
        newCard.id = cardId;
        
        // Insert at top (since we sort newest first usually)
        list.insertBefore(newCard, list.firstChild);
    }
}

function removeCard(id) {
    const card = document.getElementById(`card-${id}`);
    if (card) {
        card.classList.remove('animate__fadeInUp');
        card.classList.add('animate__fadeOut');
        setTimeout(() => card.remove(), 500);
        
        // Check if list is empty after removal
        setTimeout(() => {
            const list = document.getElementById('downloadsList');
            if (list.children.length === 0) {
                renderDownloads([]); // Restore empty state
            }
        }, 550);
    }
}

// ... (rest of code)

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    // ... (theme logic) ...

    // ... (listeners) ...

    // Start SSE connection
    setupEventStream();
});

// Remove old startRefreshing/polling code
