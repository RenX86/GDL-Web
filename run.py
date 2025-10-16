#!/usr/bin/env python3
"""
Gallery-DL Web App Runner

This file handles starting the Flask application with proper configuration
for both development and production environments.
"""

import os
import sys
from app import create_app
from app.config import get_config
from app.logging_config import setup_logging

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
    config_env = os.environ.get('FLASK_ENV')
    # Always default to development locally unless FLASK_ENV is explicitly set
    config_name = config_env or 'development'
    # Keep FLASK_ENV in sync so logging_config can determine environment-specific logger levels
    os.environ['FLASK_ENV'] = config_name
    config_class = get_config(config_name)
    
    # Setup logging using centralized configuration
    setup_logging(config_class.LOG_LEVEL, config_class.LOG_FILE)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create Flask app with configuration
    app = create_app(config_name)
    
    # Determine if running on a managed platform (Render or similar) where PORT is provided
    is_managed = 'PORT' in os.environ
    
    # Get port - prefer environment PORT when available
    port = int(os.environ.get('PORT', config_class.PORT))
    
    # Print startup information using config values
    if is_managed:
        print(f"🌐 Running on Render/Managed platform")
    else:
        print(f"🌐 Running locally")
    
    print(f"🔧 Environment: {config_name}")
    print(f"🔧 Debug mode: {'ON' if config_class.DEBUG else 'OFF'}")
    print(f"📁 Downloads will be saved to: {config_class.DOWNLOADS_DIR}")
    print(f"🌐 Server will listen on {config_class.HOST}:{port}")
    print("🚀 Ready to download media!")
    print("-" * 50)
    
    if __name__ == '__main__':
        if config_name == "production":
            print("❌ Refusing to start Flask dev server in production.")
            print("   Use a WSGI server (gunicorn, uvicorn) instead.")
            sys.exit(2)

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
    
    # Don't return app when running directly - it will be created for WSGI separately

# Create the app instance for WSGI servers (Gunicorn)
# Only create the app when this module is imported, don't run the server
app = None

if __name__ == '__main__':
    main()
else:
    # When imported by WSGI server, create app without running server
    config_name = os.environ.get('FLASK_ENV', 'production')
    config_class = get_config(config_name)
    setup_logging(config_class.LOG_LEVEL, config_class.LOG_FILE)
    app = create_app(config_name)
