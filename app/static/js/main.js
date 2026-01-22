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
                refreshDownloads();
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
                refreshDownloads();
            } else {
                showToast('Error', data.message, 'error');
            }
        })
        .catch(() => showToast('Error', 'Network error during deletion', 'error'));
}

function clearSession() {
    if (!confirm('Clear all history and files? This cannot be undone.')) return;

    fetch('/api/session/clear', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Session Cleared', 'All history removed', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showToast('Error', 'Failed to clear session', 'error');
            }
        });
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
                    <div class="d-flex justify-content-between align-items-center p-3 border-bottom bg-body-secondary">
                        <span class="text-muted small">${data.files.length} files found</span>
                        <a href="/api/download-zip/${downloadId}" class="btn btn-primary btn-sm">
                            <i class="bi bi-file-earmark-zip me-1"></i> Download All (Zip)
                        </a>
                    </div>
                `;

                const filesHtml = data.files.map(file => `
                    <div class="list-group-item d-flex justify-content-between align-items-center file-item-action">
                        <div class="text-truncate me-3">
                            <i class="bi bi-file-earmark me-2 text-secondary"></i>
                            <span class="fw-medium">${file.name}</span>
                            <div class="small text-muted">${file.size || 'Unknown size'}</div>
                        </div>
                        <a href="/api/download-file/${downloadId}/${file.name}" class="btn btn-sm btn-outline-primary" download>
                            <i class="bi bi-download"></i>
                        </a>
                    </div>
                `).join('');
                
                listContainer.innerHTML = headerHtml + filesHtml;
            } else {
                listContainer.innerHTML = '<div class="alert alert-warning m-3">Could not load files.</div>';
            }
        })
        .catch(() => {
            listContainer.innerHTML = '<div class="alert alert-danger m-3">Network error loading files.</div>';
        });
}

// --- Rendering & Logic ---

function renderDownloads(downloads) {
    const list = document.getElementById('downloadsList');
    
    // Sort: Newest first
    const sorted = downloads.sort((a, b) => new Date(b.start_time || 0) - new Date(a.start_time || 0));

    if (sorted.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>No downloads yet.</p>
            </div>`;
        return;
    }

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
        list.innerHTML = `
            <div class="text-center py-5 text-muted">
                <p>No downloads match the current filter.</p>
            </div>`;
        return;
    }

    list.innerHTML = filtered.map(d => createCardHtml(d)).join('');
}

function normalizeStatus(status) {
    status = (status || 'pending').toLowerCase();
    if (['completed', 'finished'].includes(status)) return 'completed';
    if (['error', 'failed'].includes(status)) return 'error';
    if (['cancelled', 'canceled'].includes(status)) return 'cancelled';
    if (['starting', 'downloading', 'processing', 'in_progress', 'retrying'].includes(status)) return 'downloading';
    return 'pending';
}

function createCardHtml(d) {
    const status = normalizeStatus(d.status);
    const progress = Math.round(d.progress || 0);
    const id = d.id;
    
    let statusBadge, borderClass, actionBtns;
    
    switch(status) {
        case 'completed':
            statusBadge = '<span class="badge bg-success-subtle text-success border border-success-subtle">Completed</span>';
            borderClass = 'status-completed';
            actionBtns = `
                <button onclick="showFiles('${id}')" class="btn btn-sm btn-outline-primary">
                    <i class="bi bi-folder2-open me-1"></i> Files
                </button>
                <button onclick="deleteDownload('${id}')" class="btn btn-sm btn-outline-danger">
                    <i class="bi bi-trash"></i>
                </button>
            `;
            break;
        case 'error':
            statusBadge = '<span class="badge bg-danger-subtle text-danger border border-danger-subtle">Failed</span>';
            borderClass = 'status-error';
            actionBtns = `
                <button onclick="deleteDownload('${id}')" class="btn btn-sm btn-outline-danger">
                    <i class="bi bi-trash"></i> Delete
                </button>
            `;
            break;
        case 'downloading':
            statusBadge = '<span class="badge bg-primary-subtle text-primary border border-primary-subtle"><span class="spinner-grow spinner-grow-sm me-1" style="width: 0.5rem; height: 0.5rem;"></span> In Progress</span>';
            borderClass = 'status-in-progress';
            actionBtns = `
                <button disabled class="btn btn-sm btn-light text-muted">
                    <i class="bi bi-hourglass-split"></i> Processing...
                </button>
            `;
            break;
        default: // cancelled or pending
            statusBadge = '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">Cancelled</span>';
            borderClass = 'status-cancelled';
            actionBtns = `
                <button onclick="deleteDownload('${id}')" class="btn btn-sm btn-outline-danger">
                    <i class="bi bi-trash"></i>
                </button>
            `;
    }

    const message = d.message || d.error || '';
    const fileCount = d.total_files ? `${d.files_downloaded}/${d.total_files} files` : '';

    return `
        <div class="card shadow-sm download-item ${borderClass}">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="card-subtitle text-truncate text-body-secondary" style="max-width: 70%;" title="${d.url}">
                        <i class="bi bi-link-45deg me-1"></i>${d.url}
                    </h6>
                    ${statusBadge}
                </div>
                
                <div class="d-flex justify-content-between align-items-center mb-1 small">
                    <span class="fw-bold fs-5 text-dark">${progress}%</span>
                    <span class="text-muted">${fileCount}</span>
                </div>
                
                <div class="progress mb-3" style="height: 6px;">
                    <div class="progress-bar ${status === 'completed' ? 'bg-success' : (status === 'error' ? 'bg-danger' : '')}" 
                         role="progressbar" 
                         style="width: ${progress}%" 
                         aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100">
                    </div>
                </div>
                
                ${message ? `<div class="alert alert-light border py-1 px-2 small mb-3 text-muted text-truncate"><i class="bi bi-terminal me-1"></i>${message}</div>` : ''}

                <div class="d-flex justify-content-end gap-2">
                    ${actionBtns}
                </div>
            </div>
        </div>
    `;
}

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    // Theme Logic
    const themeToggle = document.getElementById('themeToggle');
    const html = document.documentElement;
    const icon = themeToggle.querySelector('i');

    const setTheme = (theme) => {
        html.setAttribute('data-bs-theme', theme);
        localStorage.setItem('theme', theme);
        
        // Update Icon
        if (theme === 'dark') {
            icon.classList.replace('bi-moon-stars', 'bi-sun');
            icon.classList.add('text-warning');
        } else {
            icon.classList.replace('bi-sun', 'bi-moon-stars');
            icon.classList.remove('text-warning');
        }
    };

    // Load saved theme
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);

    // Toggle event
    themeToggle.addEventListener('click', (e) => {
        e.preventDefault();
        const current = html.getAttribute('data-bs-theme');
        setTheme(current === 'dark' ? 'light' : 'dark');
    });

    // Attach listeners
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('change', (e) => {
            if (e.target.checked) {
                statusFilter = e.target.dataset.filter;
                refreshDownloads();
            }
        });
    });

    document.getElementById('clearSessionBtn').addEventListener('click', clearSession);

    // Initial load
    startRefreshing();
});

function startRefreshing() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(refreshDownloads, 2000); // 2s polling
    refreshDownloads();
}
