#!/usr/bin/env python3
"""
Gallery-DL Web App Runner

This file handles starting the Flask application with proper configuration
for both development and production environments.
"""

import os
import sys
import logging

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import create_app

def setup_logging():
    """Configure logging for the application"""
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log')
        ]
    )

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import subprocess
        result = subprocess.run(['gallery-dl', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Gallery-dl found: {result.stdout.strip()}")
        else:
            raise Exception("Gallery-dl not working properly")
    except FileNotFoundError:
        print("❌ Error: gallery-dl is not installed!")
        print("Install it with: pip install gallery-dl")
        return False
    except Exception as e:
        print(f"❌ Error checking gallery-dl: {e}")
        return False
    
    return True

def main():
    """Main function to run the application"""
    print("🎨 Starting Gallery-DL Web App...")
    
    # Setup logging
    setup_logging()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create Flask app
    app = create_app()
    
    # Get configuration from environment
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Print startup information
    print(f"📡 Server starting on http://{host}:{port}")
    print(f"🔧 Debug mode: {'ON' if debug else 'OFF'}")
    print(f"📁 Downloads will be saved to: {app.config['DOWNLOADS_DIR']}")
    print("🚀 Ready to download media!")
    print("-" * 50)
    
    try:
        # Run the Flask application
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True  # Allow multiple concurrent requests
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
