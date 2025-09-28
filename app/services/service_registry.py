"""
Service Registry Module

This module provides a centralized registry for all application services,
enabling proper dependency injection and service management.
"""

from .download_service_adapter import DownloadServiceAdapter

class ServiceRegistry:
    """
    A registry for managing application services with dependency injection support.
    
    This class allows services to be registered, retrieved, and managed centrally,
    making it easier to handle dependencies between services and enabling better
    testability through service mocking.
    """
    
    def __init__(self):
        """Initialize an empty service registry."""
        self._services = {}
        self._factories = {}
    
    def register(self, service_name, service_instance):
        """
        Register a service instance with the registry.
        
        Args:
            service_name (str): Name to identify the service
            service_instance (object): The service instance to register
        """
        self._services[service_name] = service_instance
    
    def register_factory(self, service_name, factory_func):
        """
        Register a factory function for lazy service instantiation.
        
        Args:
            service_name (str): Name to identify the service
            factory_func (callable): Function that creates the service when needed
        """
        self._factories[service_name] = factory_func
    
    def get(self, service_name):
        """
        Get a service instance by name.
        
        If the service was registered as a factory, it will be instantiated
        on first access and cached for subsequent calls.
        
        Args:
            service_name (str): Name of the service to retrieve
            
        Returns:
            object: The requested service instance
            
        Raises:
            KeyError: If the service is not registered
        """
        # Check if service is already instantiated
        if service_name in self._services:
            return self._services[service_name]
        
        # Check if we have a factory for this service
        if service_name in self._factories:
            # Create service using factory and cache it
            service = self._factories[service_name]()
            self._services[service_name] = service
            return service
        
        raise KeyError(f"Service '{service_name}' not registered")
    
    def has(self, service_name):
        """
        Check if a service is registered.
        
        Args:
            service_name (str): Name of the service to check
            
        Returns:
            bool: True if the service is registered, False otherwise
        """
        return service_name in self._services or service_name in self._factories
    
    def clear(self):
        """Clear all registered services and factories."""
        self._services.clear()
        self._factories.clear()
        
    def wrap_with_adapter(self, service_name, adapter_class):
        """
        Wrap an existing service with an adapter.
        
        Args:
            service_name (str): Name of the service to wrap
            adapter_class (class): Adapter class to wrap the service with
            
        Returns:
            object: The wrapped service
        """
        if not self.has(service_name):
            raise KeyError(f"Service '{service_name}' not registered")
            
        service = self.get(service_name)
        adapted_service = adapter_class(service)
        self.register(service_name, adapted_service)
        
        return adapted_service