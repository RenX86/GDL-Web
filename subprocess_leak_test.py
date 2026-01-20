#!/usr/bin/env python3
"""
Test script to verify subprocess resource leak fixes.
This script tests various scenarios that could cause resource leaks.
"""

import threading
import time
import psutil
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.services.download_service import DownloadService
from app.models.download import DownloadStatus

def get_open_file_descriptors():
    """Get the number of open file descriptors for the current process."""
    try:
        process = psutil.Process(os.getpid())
        return len(process.open_files())
    except:
        return 0

def get_thread_count():
    """Get the number of active threads."""
    return threading.active_count()

def test_resource_leak_prevention():
    """Test that subprocess resources are properly cleaned up."""
    print("Testing subprocess resource leak prevention...")
    
    # Initial resource counts
    initial_fds = get_open_file_descriptors()
    initial_threads = get_thread_count()
    
    print(f"Initial file descriptors: {initial_fds}")
    print(f"Initial threads: {initial_threads}")
    
    # Create a test config
    test_config = {
        'DOWNLOADS_DIR': os.path.join(project_root, 'test_downloads'),
        'COOKIES_DIR': os.path.join(project_root, 'test_cookies'),
        'COOKIES_ENCRYPTION_KEY': 'test_encryption_key_1234567890abcdef',
        'GALLERY_DL_CONFIG': {
            "extractor": {
                'filename': '{category}_{username}_{post_shortcode|post_id|shortcode|id}_{filename}.{extension}',
                "write-info-json": True,
            }
        }
    }
    
    # Create test directories
    os.makedirs(test_config['DOWNLOADS_DIR'], exist_ok=True)
    os.makedirs(test_config['COOKIES_DIR'], exist_ok=True)
    
    service = DownloadService(test_config)
    
    # Test 1: Normal download completion
    print("\n1. Testing normal download completion...")
    test_url = "https://example.com/test1"
    output_dir = os.path.join(test_config['DOWNLOADS_DIR'], 'test1')
    os.makedirs(output_dir, exist_ok=True)
    download_id = service.start_download(test_url, output_dir)
    
    # Wait a bit for the download to start
    time.sleep(2)
    
    # Check resources during download
    during_fds = get_open_file_descriptors()
    during_threads = get_thread_count()
    print(f"File descriptors during download: {during_fds}")
    print(f"Threads during download: {during_threads}")
    
    # Wait for download to complete or timeout
    timeout = 30
    start_time = time.time()
    while time.time() - start_time < timeout:
        status = service.get_download_status(download_id)
        if status and status.get('status') in ['completed', 'failed', 'cancelled']:
            break
        time.sleep(0.5)
    
    # Give some time for cleanup
    time.sleep(2)
    
    # Check resources after download
    after_fds = get_open_file_descriptors()
    after_threads = get_thread_count()
    print(f"File descriptors after download: {after_fds}")
    print(f"Threads after download: {after_threads}")
    
    # Test 2: Concurrent downloads
    print("\n2. Testing concurrent downloads...")
    urls = [
        "https://example.com/test2",
        "https://example.com/test3", 
        "https://example.com/test4"
    ]
    
    download_ids = []
    for i, url in enumerate(urls):
        output_dir = os.path.join(test_config['DOWNLOADS_DIR'], f'test{i+2}')
        os.makedirs(output_dir, exist_ok=True)
        download_id = service.start_download(url, output_dir)
        download_ids.append(download_id)
    
    # Wait for all downloads to start
    time.sleep(3)
    
    concurrent_fds = get_open_file_descriptors()
    concurrent_threads = get_thread_count()
    print(f"File descriptors during concurrent downloads: {concurrent_fds}")
    print(f"Threads during concurrent downloads: {concurrent_threads}")
    
    # Wait for all downloads to complete
    for download_id in download_ids:
        timeout = 30
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = service.get_download_status(download_id)
            if status and status.get('status') in ['completed', 'failed', 'cancelled']:
                break
            time.sleep(0.5)
    
    # Give time for cleanup
    time.sleep(3)
    
    final_fds = get_open_file_descriptors()
    final_threads = get_thread_count()
    print(f"File descriptors after all downloads: {final_fds}")
    print(f"Threads after all downloads: {final_threads}")
    
    # Test 3: Cancelled downloads
    print("\n3. Testing cancelled downloads...")
    cancel_url = "https://example.com/cancel_test"
    cancel_output_dir = os.path.join(test_config['DOWNLOADS_DIR'], 'cancel_test')
    os.makedirs(cancel_output_dir, exist_ok=True)
    cancel_id = service.start_download(cancel_url, cancel_output_dir)
    
    time.sleep(1)  # Let it start
    service.cancel_download(cancel_id)
    
    time.sleep(3)  # Wait for cleanup
    
    cancel_fds = get_open_file_descriptors()
    cancel_threads = get_thread_count()
    print(f"File descriptors after cancelled download: {cancel_fds}")
    print(f"Threads after cancelled download: {cancel_threads}")
    
    # Analysis
    print("\n=== RESOURCE LEAK ANALYSIS ===")
    
    # Check for file descriptor leaks
    fd_leak = final_fds - initial_fds
    if fd_leak > 5:  # Allow small variance
        print(f"❌ WARNING: Potential file descriptor leak detected! ({fd_leak} more FDs)")
    else:
        print(f"✅ No significant file descriptor leak detected (difference: {fd_leak})")
    
    # Check for thread leaks
    thread_leak = final_threads - initial_threads
    if thread_leak > 3:  # Allow small variance for background threads
        print(f"❌ WARNING: Potential thread leak detected! ({thread_leak} more threads)")
    else:
        print(f"✅ No significant thread leak detected (difference: {thread_leak})")
    
    # Check for excessive resource usage during operations
    max_fds = max(initial_fds, during_fds, concurrent_fds, after_fds, final_fds)
    max_threads = max(initial_threads, during_threads, concurrent_threads, after_threads, final_threads, cancel_threads)
    
    print(f"\nMaximum file descriptors used: {max_fds}")
    print(f"Maximum threads used: {max_threads}")
    
    return {
        'initial_fds': initial_fds,
        'final_fds': final_fds,
        'initial_threads': initial_threads,
        'final_threads': final_threads,
        'fd_leak': fd_leak,
        'thread_leak': thread_leak,
        'max_fds': max_fds,
        'max_threads': max_threads,
        'service': service,  # Return service for use in other tests
        'downloads_dir': test_config['DOWNLOADS_DIR']
    }

def test_timeout_mechanisms(service, downloads_dir):
    """Test that timeout mechanisms work correctly."""
    print("\n\nTesting timeout mechanisms...")
    
    # Test with a URL that should timeout quickly
    timeout_url = "https://nonexistent-domain-12345.com/test"
    timeout_output_dir = os.path.join(downloads_dir, 'timeout_test')
    os.makedirs(timeout_output_dir, exist_ok=True)
    
    print(f"Starting download with timeout-prone URL: {timeout_url}")
    download_id = service.start_download(timeout_url, timeout_output_dir)
    
    # Monitor for timeout
    timeout = 120  # 2 minutes max
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        status = service.get_download_status(download_id)
        if status and status.get('status') == 'failed':
            print(f"✅ Download failed as expected: {status.get('error_message')}")
            break
        elif status and status.get('status') == 'completed':
            print("⚠️  Download completed unexpectedly")
            break
        time.sleep(1)
    else:
        print("⚠️  Download did not fail within expected timeout")
    
    print("Timeout mechanism test completed.")

if __name__ == "__main__":
    print("Subprocess Resource Leak Test Suite")
    print("=" * 40)
    
    try:
        # Run resource leak tests
        results = test_resource_leak_prevention()
        
        # Run timeout tests
        test_timeout_mechanisms(results['service'], results['downloads_dir'])
        
        print("\n" + "=" * 40)
        print("Test suite completed successfully!")
        
        # Summary
        if results['fd_leak'] <= 5 and results['thread_leak'] <= 3:
            print("✅ All resource leak tests PASSED")
        else:
            print("⚠️  Some resource leak tests may have issues")
            
    except Exception as e:
        print(f"❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()