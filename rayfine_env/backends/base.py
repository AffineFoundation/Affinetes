"""Abstract backend interface for environment execution"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any


class AbstractBackend(ABC):
    """Base class for environment execution backends"""
    
    @abstractmethod
    def setup(self, env_vars: Optional[Dict[str, str]] = None) -> None:
        """
        Initialize the environment with configuration
        
        Args:
            env_vars: Environment variables to inject
        """
        pass
    
    @abstractmethod
    def call_method(self, method_name: str, *args, **kwargs) -> Any:
        """
        Call a method from the environment
        
        Args:
            method_name: Name of method to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        pass
    
    @abstractmethod
    def list_methods(self) -> list:
        """
        List available methods in the environment
        
        Returns:
            List of method names
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources (stop containers, disconnect Ray, etc.)"""
        pass
    
    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if backend is ready for method calls
        
        Returns:
            True if ready
        """
        pass