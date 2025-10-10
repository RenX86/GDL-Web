# Gallery-DL Web App - Complete In-Depth Flow Diagram

## 🚀 Application Entry Point & Initialization

### 1. Application Startup (`run.py`)
```
main() function execution:
├── check_dependencies() → Validates gallery-dl installation
├── get_config(config_name) → Loads configuration class
├── setup_logging(config_class.LOG_LEVEL, config_class.LOG_FILE) → Initializes logging
├── create_app(config_name) → Creates Flask application instance
└── app.run(host, port, debug, threaded=True) → Starts Flask server
```

**Function Calls:**
- `run.py::main()`
- `run.py::check_dependencies()`
- `app/config.py::get_config()`
- `app/logging_config.py::setup_logging()`
- `app/__init__.py::create_app()`

### 2. Flask App Creation (`app/__init__.py`)
```
create_app(config_name) execution:
├── Flask(__name__) → Creates Flask instance
├── get_config(config_name) → Gets configuration class
├── config_class.init_app(app) → Initializes app configuration
├── os.makedirs(app.config['DOWNLOADS_DIR'], exist_ok=True) → Creates download directory
├── create_download_service(config) → Creates download service instance
├── registry.register('download_service_raw', download_service) → Registers raw service
├── DownloadServiceAdapter(download_service) → Creates service adapter
├── registry.register('download_service', download_adapter) → Registers adapted service
├── app.service_registry = registry → Attaches registry to app
├── app.register_blueprint(main_bp) → Registers web routes
└── app.register_blueprint(api_bp, url_prefix='/api') → Registers API routes
```

**Function Calls:**
- `app/__init__.py::create_app()`
- `app/config.py::get_config()`
- `app/services/__init__.py::create_download_service()`
- `app/services/service_registry.py::ServiceRegistry.register()`
- `app/services/download_service_adapter.py::DownloadServiceAdapter.__init__()`
- `app/routes/__init__.py::main_bp, api_bp`

## 🌐 Frontend User Interface Flow

### 3. HTML Template Loading (`app/templates/index.html`)
```
Page Load Sequence:
├── HTML DOM Construction
├── CSS Loading: app/static/css/styles.css
├── JavaScript Loading: app/static/js/main.js (defer)
└── DOMContentLoaded Event → Triggers JavaScript initialization
```

### 4. JavaScript Initialization (`app/static/js/main.js`)
```
DOMContentLoaded Event Handler:
├── document.getElementById('mediaUrl').addEventListener('keypress', function(e))
├── setupFilterButtons() → Attaches filter button event listeners
├── allFilterBtn.classList.add('active') → Sets default filter
└── refreshDownloads() → Initial download list load
```

**Function Calls:**
- `app/static/js/main.js::DOMContentLoaded event handler`
- `app/static/js/main.js::setupFilterButtons()`
- `app/static/js/main.js::refreshDownloads()`

### 5. User Download Initiation (`app/static/js/main.js`)
```
startDownload() function execution:
├── document.getElementById('mediaUrl').value.trim() → Gets URL input
├── document.getElementById('cookieFile').files[0] → Gets cookie file
├── new URL(url) → Validates URL format
├── downloadBtn.disabled = true → Disables download button
├── spinner.style.display = 'inline-block' → Shows loading spinner
├── FileReader.readAsText(cookieFile) → Reads cookie file (if provided)
└── sendRequest(cookiesContent) → Sends download request
```

**Function Calls:**
- `app/static/js/main.js::startDownload()`
- `app/static/js/main.js::sendRequest()`

### 6. AJAX Request to API (`app/static/js/main.js`)
```
sendRequest(cookiesContent) execution:
├── fetch('/api/download', {method: 'POST', ...}) → POST request to API
├── response.json() → Parses JSON response
├── data.success check → Validates response
├── document.getElementById('mediaUrl').value = '' → Clears URL input
├── document.getElementById('cookieFile').value = '' → Clears file input
├── startRefreshing() → Begins status polling
└── showNotification('Download started successfully!', 'success') → Shows success message
```

**Function Calls:**
- `app/static/js/main.js::sendRequest()`
- `app/static/js/main.js::startRefreshing()`
- `app/static/js/main.js::showNotification()`

## 🔌 API Layer Processing

### 7. API Route Handler (`app/routes/api.py`)
```
start_download() route execution:
├── @handle_api_errors decorator → Error handling wrapper
├── @validate_required_fields(['url']) decorator → URL validation
├── request.get_json() → Extracts JSON data
├── data.get('url'), data.get('cookies') → Gets URL and cookies
├── current_app.service_registry.get('download_service') → Gets service instance
├── download_service.is_valid_url(url) → Validates URL format
├── download_service.start_download(url, output_dir, cookies_content) → Starts download
└── jsonify({'success': True, 'download_id': download_id, ...}) → Returns response
```

**Function Calls:**
- `app/routes/api.py::start_download()`
- `app/utils.py::handle_api_errors()`
- `app/utils.py::validate_required_fields()`
- `app/services/download_service_adapter.py::is_valid_url()`
- `app/services/download_service_adapter.py::start_download()`

## ⚙️ Service Layer Processing

### 8. Download Service Adapter (`app/services/download_service_adapter.py`)
```
start_download() adapter execution:
├── self._service.start_download(url, output_dir, cookies_content) → Delegates to raw service
└── Returns download_id
```

**Function Calls:**
- `app/services/download_service_adapter.py::start_download()`
- `app/services/download_service.py::start_download()`

### 9. Core Download Service (`app/services/download_service.py`)
```
start_download() service execution:
├── download_id = str(int(time.time() * 1000)) → Generates unique ID
├── self.download_status[download_id] = {...} → Initializes status tracking
├── threading.Thread(target=self._download_worker, args=(...)) → Creates worker thread
├── thread.daemon = True → Sets thread as daemon
├── thread.start() → Starts background thread
├── encrypt_cookies(cookies_content, self.encryption_key) → Encrypts cookies (if provided)
├── os.path.join(self.cookies_dir, f"{download_id}.txt") → Creates cookie file path
└── Returns download_id
```

**Function Calls:**
- `app/services/download_service.py::start_download()`
- `app/services/download_service.py::_download_worker()` (threaded)
- `app/services/cookie_manager.py::encrypt_cookies()`

## 🔄 Background Download Processing

### 10. Download Worker Thread (`app/services/download_service.py`)
```
_download_worker() execution:
├── check_network_connectivity() → Validates internet connection
├── check_url_accessibility(url) → Tests URL accessibility
├── Retry Loop (max_retries = 3):
│   ├── self.download_status[download_id].update({...}) → Updates status
│   ├── cmd = ['gallery-dl'] → Builds gallery-dl command
│   ├── gallery_dl_config processing → Applies configuration
│   ├── cmd.extend(['-D', output_dir]) → Sets output directory
│   ├── Cookie handling:
│   │   ├── decrypt_cookies(encrypted_content, self.encryption_key) → Decrypts cookies
│   │   ├── temp_cookie_path creation → Creates temporary cookie file
│   │   └── cmd.extend(['--cookies', temp_cookie_path]) → Adds cookies to command
│   ├── subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, ...) → Executes gallery-dl
│   ├── self.active_processes[download_id] = process → Stores process reference
│   ├── Real-time output processing:
│   │   ├── process.stdout.readline() → Reads output line by line
│   │   ├── parse_progress(self.download_status, download_id, line) → Parses progress
│   │   └── self.logger.debug(f"[gallery-dl] {line.strip()}") → Logs output
│   ├── process.communicate() → Gets remaining output
│   ├── self.active_processes.pop(download_id, None) → Removes process reference
│   ├── Success handling (returncode == 0):
│   │   ├── count_downloaded_files(stdout_lines) → Counts downloaded files
│   │   └── self.download_status[download_id].update({...}) → Updates final status
│   └── Error handling:
│       ├── self._is_retriable_error(error_message) → Checks if error is retriable
│       └── Retry logic or final failure status update
└── Cleanup:
    ├── os.remove(cookie_file_path) → Removes encrypted cookie file
    └── os.remove(temp_cookie_path) → Removes temporary cookie file
```

**Function Calls:**
- `app/services/download_service.py::_download_worker()`
- `app/services/network_utils.py::check_network_connectivity()`
- `app/services/network_utils.py::check_url_accessibility()`
- `app/services/cookie_manager.py::decrypt_cookies()`
- `app/services/progress_parser.py::parse_progress()`
- `app/services/progress_parser.py::count_downloaded_files()`
- `app/services/download_service.py::_is_retriable_error()`

### 11. Progress Parsing (`app/services/progress_parser.py`)
```
parse_progress() execution:
├── Line analysis for progress indicators
├── 'downloading' detection → Updates message to 'Downloading files...'
├── 'extracting' detection → Updates message and progress to 25%
└── 'processing' detection → Updates message and progress to 50%

count_downloaded_files() execution:
├── Iterates through stdout_lines
├── Searches for 'Downloading' and ' -> ' patterns
└── Returns count of downloaded files
```

**Function Calls:**
- `app/services/progress_parser.py::parse_progress()`
- `app/services/progress_parser.py::count_downloaded_files()`

### 12. Cookie Management (`app/services/cookie_manager.py`)
```
encrypt_cookies() execution:
├── Fernet(encryption_key.encode()) → Creates cipher
├── cipher.encrypt(cookies_content.encode()) → Encrypts content
└── Returns encrypted content as string

decrypt_cookies() execution:
├── Fernet(encryption_key.encode()) → Creates cipher
├── cipher.decrypt(encrypted_content.encode()) → Decrypts content
└── Returns decrypted content as string
```

**Function Calls:**
- `app/services/cookie_manager.py::encrypt_cookies()`
- `app/services/cookie_manager.py::decrypt_cookies()`

## 📊 Real-time Status Updates

### 13. Frontend Status Polling (`app/static/js/main.js`)
```
startRefreshing() execution:
├── clearInterval(refreshInterval) → Clears existing interval
├── setInterval(refreshDownloads, 2000) → Sets 2-second polling
└── refreshDownloads() → Immediate refresh

refreshDownloads() execution:
├── fetch('/api/downloads') → GET request to downloads API
├── response.json() → Parses JSON response
├── updateDownloadsList(data.data) → Updates UI with download data
└── Error handling for failed requests
```

**Function Calls:**
- `app/static/js/main.js::startRefreshing()`
- `app/static/js/main.js::refreshDownloads()`
- `app/static/js/main.js::updateDownloadsList()`

### 14. Downloads List API (`app/routes/api.py`)
```
list_all_downloads() route execution:
├── @handle_api_errors decorator → Error handling
├── current_app.service_registry.get('download_service') → Gets service
├── download_service.list_all_downloads() → Gets all downloads
├── Data normalization loop:
│   ├── normalized_download = {...} → Standardizes download structure
│   └── normalized_downloads.append(normalized_download) → Adds to list
└── jsonify({'success': True, 'data': normalized_downloads, ...}) → Returns response
```

**Function Calls:**
- `app/routes/api.py::list_all_downloads()`
- `app/services/download_service_adapter.py::list_all_downloads()`
- `app/services/download_service.py::get_all_downloads()`

### 15. UI Update Processing (`app/static/js/main.js`)
```
updateDownloadsList() execution:
├── Array.isArray(downloads) check → Validates data
├── Empty state handling → Shows "No downloads" message
├── validItems.filter() → Filters valid download objects
├── .sort((a, b) => new Date(b.start_time) - new Date(a.start_time)) → Sorts by time
├── .map((download) => createDownloadCard(download)) → Creates HTML cards
├── downloadsList.innerHTML = html → Updates DOM
└── setupFilterButtons() → Reattaches event listeners

createDownloadCard() execution:
├── Download data validation → Checks required fields
├── Status normalization → Maps backend status to frontend status
├── Progress calculation → Ensures 0-100% range
├── Date formatting → Converts ISO dates to locale strings
├── HTML template generation → Creates card HTML with data
└── Returns HTML string with download information
```

**Function Calls:**
- `app/static/js/main.js::updateDownloadsList()`
- `app/static/js/main.js::createDownloadCard()`
- `app/static/js/main.js::setupFilterButtons()`

## 🗑️ Download Management Operations

### 16. Delete Download Flow (`app/static/js/main.js` → `app/routes/api.py`)
```
deleteDownload() frontend execution:
├── confirm('Are you sure...') → User confirmation
├── fetch(`/api/downloads/${downloadId}`, {method: 'DELETE'}) → DELETE request
├── response.json() → Parses response
├── data.success check → Validates deletion
└── refreshDownloads() → Refreshes download list

delete_download() API execution:
├── @handle_api_errors decorator → Error handling
├── download_service.download_exists(download_id) → Checks existence
├── download_service.delete_download(download_id) → Deletes download
└── jsonify({'success': True, 'message': ...}) → Returns success response

delete_download() service execution:
├── self.active_processes.get(download_id) → Gets active process
├── process.terminate() → Terminates running process
├── self.active_processes.pop(download_id, None) → Removes process reference
├── self.download_status.pop(download_id, None) → Removes status entry
├── os.path.join(self.cookies_dir, f"{download_id}.txt") → Gets cookie file path
└── os.remove(enc_cookie_path) → Removes encrypted cookie file
```

**Function Calls:**
- `app/static/js/main.js::deleteDownload()`
- `app/routes/api.py::delete_download()`
- `app/services/download_service_adapter.py::delete_download()`
- `app/services/download_service.py::delete_download()`

### 17. Clear History Flow (`app/static/js/main.js` → `app/routes/api.py`)
```
clearHistory() frontend execution:
├── confirm('Are you sure...') → User confirmation
├── fetch('/api/downloads/clear', {method: 'POST'}) → POST request
├── response.json() → Parses response
└── refreshDownloads() → Refreshes download list

clear_download_history() API execution:
├── @handle_api_errors decorator → Error handling
├── download_service.clear_history() → Clears all history
└── jsonify({'success': True, 'message': ...}) → Returns success response

clear_history() service execution:
├── Active processes termination loop:
│   ├── process.terminate() → Terminates each active process
│   └── self.active_processes.clear() → Clears process registry
├── Cookie files cleanup loop:
│   ├── os.path.join(self.cookies_dir, f"{did}.txt") → Gets cookie file path
│   └── os.remove(enc_cookie_path) → Removes encrypted cookie file
├── os.remove(temp_cookie_path) → Removes temporary cookie file
└── self.download_status.clear() → Clears status registry
```

**Function Calls:**
- `app/static/js/main.js::clearHistory()`
- `app/routes/api.py::clear_download_history()`
- `app/services/download_service_adapter.py::clear_history()`
- `app/services/download_service.py::clear_history()`

## 🔍 Filter and Search Operations

### 18. Download Filtering (`app/static/js/main.js`)
```
setupFilterButtons() execution:
├── document.querySelectorAll('.filter-btn') → Gets filter buttons
├── Event listener attachment loop:
│   ├── button.addEventListener('click', function()) → Attaches click handler
│   ├── filterButtons.forEach(btn => btn.classList.remove('active')) → Removes active class
│   ├── this.classList.add('active') → Adds active class to clicked button
│   ├── this.getAttribute('data-filter') → Gets filter value
│   └── filterDownloads(filter) → Applies filter
└── button.dataset.listenerAttached = 'true' → Prevents duplicate listeners

filterDownloads() execution:
├── document.querySelectorAll('.download-card') → Gets all download cards
├── Download cards iteration loop:
│   ├── card.getAttribute('data-status') → Gets card status
│   ├── filter === 'all' || filter === cardStatus → Checks filter match
│   ├── card.style.display = 'block' → Shows matching cards
│   └── card.style.display = 'none' → Hides non-matching cards
```

**Function Calls:**
- `app/static/js/main.js::setupFilterButtons()`
- `app/static/js/main.js::filterDownloads()`

## 📈 Statistics and Monitoring

### 19. Statistics API (`app/routes/api.py`)
```
get_statistics() route execution:
├── @handle_api_errors decorator → Error handling
├── download_service.get_statistics() → Gets statistics from service
└── jsonify({'success': True, 'data': stats}) → Returns statistics

get_statistics() service execution:
├── total = len(self.download_status) → Counts total downloads
├── Status counting loop:
│   ├── status.get('status', 'unknown').lower() → Gets normalized status
│   ├── Status classification:
│   │   ├── ['completed', 'finished'] → Increments completed counter
│   │   ├── ['failed', 'error'] → Increments failed counter
│   │   └── ['downloading', 'starting', 'processing', 'in_progress'] → Increments in_progress counter
└── Returns statistics dictionary
```

**Function Calls:**
- `app/routes/api.py::get_statistics()`
- `app/services/download_service_adapter.py::get_statistics()`
- `app/services/download_service.py::get_statistics()`

## 🔧 Configuration and Utilities

### 20. Configuration Management (`app/config.py`)
```
get_config() execution:
├── config_name parameter processing → Determines environment
├── Configuration class selection:
│   ├── 'development' → DevelopmentConfig
│   ├── 'production' → ProductionConfig
│   └── 'testing' → TestingConfig
└── Returns configuration class instance
```

### 21. Error Handling (`app/utils.py`)
```
handle_api_errors() decorator execution:
├── try-except wrapper around route function
├── Exception type handling:
│   ├── ValidationError → Returns 400 with error message
│   ├── ResourceNotFoundError → Returns 404 with error message
│   ├── ValueError → Returns 400 with error message
│   └── Exception → Returns 500 with generic error message
└── jsonify({'success': False, 'error': message}) → Returns error response

validate_required_fields() decorator execution:
├── request.get_json() → Gets request data
├── Required fields validation loop:
│   ├── field not in data check → Validates field presence
│   └── not data[field] check → Validates field value
├── ValidationError(f'Missing required field: {field}') → Raises validation error
└── Calls wrapped function if validation passes
```

**Function Calls:**
- `app/utils.py::handle_api_errors()`
- `app/utils.py::validate_required_fields()`

## 🌐 Network Utilities (`app/services/network_utils.py`)

### 22. Network Connectivity Checks
```
check_network_connectivity() execution:
├── socket.create_connection(('8.8.8.8', 53), timeout=3) → Tests DNS connectivity
├── connection.close() → Closes test connection
└── Returns True if successful, False on exception

check_url_accessibility() execution:
├── requests.head(url, timeout=10, allow_redirects=True) → HEAD request to URL
├── response.status_code < 400 → Checks for successful response
└── Returns True if accessible, False on exception

is_network_error() execution:
├── Network error patterns list → Defines error patterns to match
├── any(pattern in error_message.lower() for pattern in patterns) → Pattern matching
└── Returns True if network error detected, False otherwise
```

**Function Calls:**
- `app/services/network_utils.py::check_network_connectivity()`
- `app/services/network_utils.py::check_url_accessibility()`
- `app/services/network_utils.py::is_network_error()`

## 📝 Complete Function Call Chain Summary

### Download Initiation Chain:
1. `app/static/js/main.js::startDownload()`
2. `app/static/js/main.js::sendRequest()`
3. `app/routes/api.py::start_download()`
4. `app/services/download_service_adapter.py::start_download()`
5. `app/services/download_service.py::start_download()`
6. `app/services/download_service.py::_download_worker()` (threaded)
7. `app/services/cookie_manager.py::encrypt_cookies()`/`decrypt_cookies()`
8. `app/services/progress_parser.py::parse_progress()`
9. `app/services/network_utils.py::check_network_connectivity()`
10. `subprocess.Popen()` → gallery-dl execution

### Status Update Chain:
1. `app/static/js/main.js::refreshDownloads()` (every 2 seconds)
2. `app/routes/api.py::list_all_downloads()`
3. `app/services/download_service_adapter.py::list_all_downloads()`
4. `app/services/download_service.py::get_all_downloads()`
5. `app/static/js/main.js::updateDownloadsList()`
6. `app/static/js/main.js::createDownloadCard()`

### File Structure Impact:
- **Entry Point**: `run.py::main()`
- **App Factory**: `app/__init__.py::create_app()`
- **Web Routes**: `app/routes/web.py::index()`
- **API Routes**: `app/routes/api.py::*`
- **Service Layer**: `app/services/download_service.py::*`
- **Service Adapter**: `app/services/download_service_adapter.py::*`
- **Utilities**: `app/services/{cookie_manager,progress_parser,network_utils}.py::*`
- **Frontend**: `app/templates/index.html` + `app/static/js/main.js::*`
- **Configuration**: `app/config.py::*`

This comprehensive flow diagram traces every function call, file interaction, and data flow from the moment a user enters a URL until the file is downloaded and status is updated in real-time.