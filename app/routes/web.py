"""
Web Routes Module

This module contains all web routes for the application.
"""

from flask import Blueprint, render_template

# Create blueprint for web routes
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Serve the main page"""
    return render_template("index.html")
