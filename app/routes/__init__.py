"""
Routes Package

This package contains all route definitions for the application,
organized into separate modules for better maintainability.
"""

from .api import api_bp
from .web import main_bp

# Export blueprints
__all__ = ["api_bp", "main_bp"]
