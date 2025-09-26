#!/usr/bin/env python3
"""
Gallery-DL Web App Runner

This file handles starting the Flask application with proper configuration
for both development and production environments.
"""

import os
import sys
import logging
from app import create_app
from app.config import get_config

def setup_logging(config_class):
    """Configure logging for the application"""
    log_level = getattr(logging, config_class.LOG_LEVEL.upper())
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(config_class.LOG_FILE)
        ]
    )

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import subprocess
        result = subprocess.run(['gallery-dl', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ Gallery-dl found: {result.stdout.strip()}")
        else:
            raise Exception("Gallery-dl not working properly")
    except FileNotFoundError:
        print("❌ Error: gallery-dl is not installed!")
        print("Install it with: pip install gallery-dl")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Error: gallery-dl command timed out")
        return False
    except Exception as e:
        print(f"❌ Error checking gallery-dl: {e}")
        return False
    
    return True

def main():
    """Main function to run the application"""
    print("🎨 Starting Gallery-DL Web App...")
    
    # Get configuration
    config_name = os.environ.get('FLASK_ENV', 'development')
    config_class = get_config(config_name)
    
    # Setup logging
    setup_logging(config_class)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create Flask app with configuration
    app = create_app(config_name)
    
    # Get port from environment variable directly for Render compatibility
    port = int(os.environ.get('PORT', config_class.PORT))
    
    # Print startup information using config values
    print(f"🔧 Development mode active")
    print(f"📁 Downloads directory: {config_class.DOWNLOADS_DIR}")
    print(f"🌐 Server will run on {config_class.HOST}:{port}")
    print(f"🌐 Server starting on http://{config_class.HOST}:{port}")
    print(f"🔧 Environment: {config_name}")
    print(f"🔧 Debug mode: {'ON' if config_class.DEBUG else 'OFF'}")
    print(f"📁 Downloads will be saved to: {config_class.DOWNLOADS_DIR}")
    print("🚀 Ready to download media!")
    print("-" * 50)
    
    if __name__ == '__main__':
        try:
            # Run the Flask application using config values
            app.run(
                host=config_class.HOST,
                port=port,
                debug=config_class.DEBUG,
                threaded=True  # Allow multiple concurrent requests
            )
        except KeyboardInterrupt:
            print("\n👋 Shutting down gracefully...")
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            sys.exit(1)
    
    return app

# Create the app instance for WSGI servers (Gunicorn)
if __name__ == '__main__':
    app = main()
