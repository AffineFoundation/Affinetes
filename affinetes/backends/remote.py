"""Remote backend - API-based execution (stub)"""

from typing import Dict, Optional, Any

from .base import AbstractBackend
from ..utils.exceptions import BackendError, NotImplementedError
from ..utils.logger import logger


class RemoteBackend(AbstractBackend):
    """
    Remote execution backend via API calls
    
    This is a stub implementation for future API-based execution.
    Users would call a remote service instead of running local containers.
    """
    
    def __init__(
        self,
        api_endpoint: str,
        api_key: str,
        environment_id: str,
        **kwargs
    ):
        """
        Initialize remote backend
        
        Args:
            api_endpoint: Remote API endpoint URL
            api_key: Authentication API key
            environment_id: Environment identifier on remote service
            **kwargs: Additional configuration
        """
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.environment_id = environment_id
        self.config = kwargs
        
        logger.info(f"RemoteBackend initialized for environment '{environment_id}'")
        logger.warning("RemoteBackend is not yet implemented - this is a stub")
    
    def call_method(self, method_name: str, *args, **kwargs) -> Any:
        """
        Call method via remote API
        
        Args:
            method_name: Method name
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        raise NotImplementedError(
            "RemoteBackend is not yet implemented. "
            "Use LocalBackend for Docker-based execution."
        )
    
    def list_methods(self) -> list:
        """
        List available methods from remote environment
        
        Returns:
            List of method names
        """
        raise NotImplementedError(
            "RemoteBackend is not yet implemented."
        )
    
    def cleanup(self) -> None:
        """Clean up remote session"""
        logger.info("RemoteBackend cleanup (stub)")
    
    def is_ready(self) -> bool:
        """
        Check if backend is ready
        
        Returns:
            False (not implemented)
        """
        return False


# Future implementation outline:
# 
# class RemoteBackend(AbstractBackend):
#     """API-based remote execution"""
#     
#     def setup(self, env_vars):
#         # POST /environments/{id}/setup with env_vars
#         response = requests.post(
#             f"{self.api_endpoint}/environments/{self.environment_id}/setup",
#             headers={"Authorization": f"Bearer {self.api_key}"},
#             json={"env_vars": env_vars}
#         )
#         # Handle response
#     
#     def call_method(self, method_name, *args, **kwargs):
#         # POST /environments/{id}/call with method and args
#         response = requests.post(
#             f"{self.api_endpoint}/environments/{self.environment_id}/call",
#             headers={"Authorization": f"Bearer {self.api_key}"},
#             json={
#                 "method": method_name,
#                 "args": args,
#                 "kwargs": kwargs
#             }
#         )
#         return response.json()["result"]