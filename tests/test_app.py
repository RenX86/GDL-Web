import pytest
from app import create_app
from app.config import TestingConfig


class TestAppFactory:
    """Test application factory."""
    
    def test_create_app(self):
        """Test app creation with different configs."""
        app = create_app('testing')
        assert app is not None
        assert app.config['TESTING'] is True
        # SECRET_KEY might be auto-generated, so just check it exists
        assert app.config['SECRET_KEY'] is not None
    
    def test_service_registry_initialization(self, app):
        """Test that service registry is properly initialized."""
        with app.app_context():
            assert hasattr(app, 'service_registry')
            assert app.service_registry is not None
    
    def test_blueprints_registered(self, app):
        """Test that blueprints are registered."""
        # Check that main and api blueprints are registered
        assert 'main' in app.blueprints
        assert 'api' in app.blueprints


class TestAppContext:
    """Test application context."""
    
    def test_service_registry_available_in_context(self, app):
        """Test service registry is available in app context."""
        with app.app_context():
            from flask import current_app
            assert hasattr(current_app, 'service_registry')
            assert current_app.service_registry is not None