"""Basilica backend - Remote HTTP-based execution for pre-deployed environments"""

import httpx
import time
from typing import Optional, Any

from .base import AbstractBackend
from ..utils.exceptions import BackendError
from ..utils.logger import logger


class BasilicaBackend(AbstractBackend):
    """
    Basilica backend for calling pre-deployed environment services
    
    Basilica is a remote environment hosting service that provides HTTP APIs
    for accessing deployed container environments. Unlike LocalBackend which
    manages Docker containers, BasilicaBackend connects to already-running
    services.
    
    Usage:
        >>> env = load_env(
        ...     image="affine",
        ...     mode="basilica",
        ...     base_url="http://xx.xx.xx.xx:8080"
        ... )
    """
    
    def __init__(
        self,
        image: str,
        base_url: str,
        timeout: int = 600,
        **kwargs
    ):
        """
        Initialize Basilica backend
        
        Args:
            image: Environment name/identifier (e.g., "affine", "agentgym")
            base_url: Basilica service base URL
            timeout: Request timeout in seconds
            **kwargs: Additional configuration
        """
        self.image = image
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.config = kwargs
        
        # Construct environment endpoint
        self.env_endpoint = f"{self.base_url}/{image}"
        
        # Create HTTP client
        self.client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20
            )
        )
        
        # Generate unique name for this backend
        self.name = f"basilica-{image}-{int(time.time())}"
        
        logger.info(f"BasilicaBackend initialized: {self.env_endpoint}")
    
    async def call_method(self, method_name: str, *args, **kwargs) -> Any:
        """
        Call method on remote Basilica environment
        
        Args:
            method_name: Method name to call
            *args: Positional arguments (converted to kwargs)
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        try:
            logger.debug(f"Calling Basilica method: {method_name}")
            
            # Basilica uses direct endpoint routing: POST /{env}/{method}
            response = await self.client.post(
                f"{self.env_endpoint}/{method_name}",
                json=kwargs
            )
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            raise BackendError(
                f"Basilica HTTP {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            raise BackendError(f"Failed to call method '{method_name}': {e}")
    
    async def list_methods(self) -> list:
        """
        List available methods from Basilica environment
        
        Returns:
            List of method names or endpoint information
        """
        try:
            # Basilica provides /methods endpoint for introspection
            response = await self.client.get(f"{self.env_endpoint}/methods")
            response.raise_for_status()
            
            data = response.json()
            return data if isinstance(data, list) else data.get("methods", [])
            
        except Exception as e:
            logger.warning(f"Failed to list methods: {e}")
            return []
    
    async def health_check(self) -> bool:
        """
        Check if Basilica environment is healthy
        
        Returns:
            True if healthy
        """
        try:
            response = await self.client.get(
                f"{self.env_endpoint}/health",
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
    
    async def cleanup(self) -> None:
        """Close HTTP client (no container cleanup needed)"""
        logger.info(f"Closing Basilica backend: {self.name}")
        await self.client.aclose()
    
    def is_ready(self) -> bool:
        """
        Check if backend is ready (Basilica environments are always ready)
        
        Returns:
            True
        """
        return True