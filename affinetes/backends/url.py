"""URL backend - Remote HTTP-based execution for user-deployed environments"""

import httpx
import time
from typing import Optional, Any

from .base import AbstractBackend
from ..utils.exceptions import BackendError
from ..utils.logger import logger


class URLBackend(AbstractBackend):
    """
    URL backend for connecting to user-deployed environment services
    
    This backend allows users to deploy their own environment services and
    connect to them via HTTP URL. Unlike LocalBackend which manages Docker
    containers, URLBackend connects to already-running services that users
    have deployed themselves.
    
    The user-deployed service should implement the following endpoints:
    - GET /health - Health check endpoint
    - GET /methods - List available methods
    - POST /call - Call method with JSON body: {"method": "...", "args": [...], "kwargs": {...}}
    
    Usage:
        >>> env = load_env(
        ...     mode="url",
        ...     base_url="http://your-service.com:8080"
        ... )
        >>> result = await env.evaluate(task_type="sat", num_samples=1)
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 600,
        verify_ssl: bool = True,
        **kwargs
    ):
        """
        Initialize URL backend
        
        Args:
            base_url: Environment service base URL (e.g., "http://your-service.com:8080")
            timeout: Request timeout in seconds (default: 600)
            verify_ssl: Verify SSL certificates for HTTPS connections (default: True)
            **kwargs: Additional configuration
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.config = kwargs
        
        # Create HTTP client
        self.client = httpx.AsyncClient(
            timeout=timeout,
            verify=verify_ssl,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20
            )
        )
        
        # Generate unique name for this backend
        # Extract hostname from URL for a meaningful name
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.base_url)
            hostname = parsed.hostname or "unknown"
            port = f":{parsed.port}" if parsed.port else ""
            self.name = f"url-{hostname}{port}-{int(time.time())}"
        except Exception:
            self.name = f"url-{int(time.time())}"
        
        logger.info(f"URLBackend initialized: {self.base_url}")
    
    async def call_method(self, method_name: str, *args, **kwargs) -> Any:
        """
        Call method on remote environment service
        
        Args:
            method_name: Method name to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        try:
            logger.debug(f"Calling URL backend method: {method_name}")
            
            # Use standard /call endpoint with method dispatch
            response = await self.client.post(
                f"{self.base_url}/call",
                json={
                    "method": method_name,
                    "args": list(args),
                    "kwargs": kwargs
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Parse response (compatible with function_based format)
            if isinstance(data, dict):
                if "status" in data:
                    # MethodResponse format
                    if data["status"] != "success":
                        raise BackendError(f"Remote execution failed: {data}")
                    return data.get("result")
                else:
                    # Direct result
                    return data
            else:
                return data
            
        except httpx.HTTPStatusError as e:
            raise BackendError(
                f"URL backend HTTP {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            raise BackendError(f"Failed to call method '{method_name}': {e}")
    
    async def list_methods(self) -> list:
        """
        List available methods from remote environment
        
        Returns:
            List of method information
        """
        try:
            # Standard /methods endpoint
            response = await self.client.get(f"{self.base_url}/methods")
            response.raise_for_status()
            
            data = response.json()
            
            # Support both list format and dict format
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("methods", [])
            else:
                return []
            
        except Exception as e:
            logger.warning(f"Failed to list methods: {e}")
            return []
    
    async def health_check(self) -> bool:
        """
        Check if remote environment is healthy
        
        Returns:
            True if healthy
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
    
    async def cleanup(self) -> None:
        """Close HTTP client (no service cleanup needed)"""
        logger.info(f"Closing URL backend: {self.name}")
        await self.client.aclose()
    
    def is_ready(self) -> bool:
        """
        Check if backend is ready (URL environments are always ready)
        
        Returns:
            True
        """
        return True