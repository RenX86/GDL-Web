"""
Centralized logging configuration for the Flask application.

This module provides a single source of truth for logging setup,
eliminating duplication between run.py and config classes.
"""

import os
import sys
import logging
from pathlib import Path


def setup_logging(log_level='INFO', log_file='app.log'):
    """
    Configure logging for the application.
    
    Args:
        log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file (str): Path to the log file
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file)
        ]
    )
    
    # Set specific logger levels for third-party libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


def get_logger(name=None):
    """
    Get a logger instance with the specified name.
    
    Args:
        name (str): Logger name (defaults to calling module)
    
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name or __name__)