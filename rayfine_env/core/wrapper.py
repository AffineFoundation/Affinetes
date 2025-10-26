"""Environment wrapper with async dynamic method dispatch"""

import time
import asyncio
from typing import Dict, Optional, Any, Union

from ..backends.base import AbstractBackend
from ..utils.exceptions import EnvironmentError
from ..utils.logger import logger


class EnvironmentWrapper:
    """
    User-facing wrapper for environment interaction
    
    Provides dynamic method dispatch via __getattr__ to expose
    all methods from the environment's env.py file.
    
    Example:
        env = load_env(image="affine:latest", env_vars={"CHUTES_API_KEY": "xxx"})
        result = env.evaluate(task_type="sat", num_samples=5)
        env.cleanup()
    """
    
    def __init__(
        self,
        backend: Union[AbstractBackend, 'InstancePool'],
    ):
        """
        Initialize environment wrapper
        
        Args:
            backend: Backend instance (LocalBackend, RemoteBackend, or InstancePool)
        """
        # Import here to avoid circular dependency
        from .instance_pool import InstancePool
        
        self._backend = backend
        self._is_pool = isinstance(backend, InstancePool)
        self.name = backend.name
        # Backend is ready immediately after initialization
        self._is_ready = backend.is_ready()
        
        backend_type = "InstancePool" if self._is_pool else "Backend"
        logger.debug(
            f"Created EnvironmentWrapper '{self.name}' "
            f"({backend_type}, ready: {self._is_ready})"
        )
    
    async def cleanup(self) -> None:
        """
        Clean up environment resources (async)
        
        Stops containers, disconnects HTTP client, and frees resources.
        Should be called when done using the environment.
        """
        try:
            logger.debug(f"Cleaning up environment '{self.name}'")
            await self._backend.cleanup()
            self._is_ready = False
            logger.debug(f"Environment '{self.name}' cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup of '{self.name}': {e}")
    
    async def list_methods(self, print_info: bool = True) -> list:
        """
        List all available methods in the environment (async)
        
        Args:
            print_info: If True, print formatted method information
        
        Returns:
            List of method information (format depends on environment type)
        """
        if not self._is_ready:
            raise EnvironmentError(
                f"Environment '{self.name}' not ready."
            )
        
        try:
            methods = await self._backend.list_methods()
            
            if print_info:
                self._print_method_info(methods)
            
            return methods
        except Exception as e:
            raise EnvironmentError(f"Failed to list methods: {e}")
    
    def _print_method_info(self, methods: list) -> None:
        """Print formatted method information"""
        if not methods:
            print("No methods available")
            return
        
        # Check if it's function_based or http_based format
        if isinstance(methods[0], dict):
            if "path" in methods[0]:
                # http_based: OpenAPI endpoints
                self._print_http_methods(methods)
            else:
                # function_based: function signatures
                self._print_function_methods(methods)
        else:
            # Fallback: simple list
            print("\nAvailable methods:")
            for method in methods:
                print(f"  - {method}")
    
    def _print_function_methods(self, methods: list) -> None:
        """Print function-based methods with signatures"""
        print("\n" + "="*60)
        print("Available Methods (function_based)")
        print("="*60)
        
        # Group by source
        actor_methods = [m for m in methods if m.get("source") == "Actor"]
        module_methods = [m for m in methods if m.get("source") == "module"]
        
        if actor_methods:
            print("\nActor Methods:")
            for method in actor_methods:
                sig = method.get("signature", "(...)")
                print(f"  env.{method['name']}{sig}")
        
        if module_methods:
            print("\nModule Functions:")
            for method in module_methods:
                sig = method.get("signature", "(...)")
                print(f"  env.{method['name']}{sig}")
        
        print("\n" + "="*60)
    
    def _print_http_methods(self, methods: list) -> None:
        """Print HTTP-based methods with endpoint details"""
        print("\n" + "="*60)
        print("Available Endpoints (http_based)")
        print("="*60)
        
        for endpoint in methods:
            path = endpoint.get("path", "")
            method = endpoint.get("method", "GET")
            summary = endpoint.get("summary", "")
            description = endpoint.get("description", "")
            params = endpoint.get("parameters", [])
            
            print(f"\n{method} {path}")
            if summary:
                print(f"  Summary: {summary}")
            if description and description != summary:
                print(f"  Description: {description}")
            
            if params:
                # Group by parameter location
                query_params = [p for p in params if p.get("in") == "query"]
                body_params = [p for p in params if p.get("in") == "body"]
                
                if query_params:
                    print("  Query Parameters:")
                    for p in query_params:
                        required = " (required)" if p.get("required") else " (optional)"
                        ptype = p.get("type", "unknown")
                        print(f"    - {p['name']}: {ptype}{required}")
                
                if body_params:
                    print("  Request Body:")
                    for p in body_params:
                        required = " (required)" if p.get("required") else " (optional)"
                        ptype = p.get("type", "unknown")
                        default = p.get("default")
                        default_str = f" = {default}" if default is not None else ""
                        print(f"    - {p['name']}: {ptype}{required}{default_str}")
        
        print("\n" + "="*60)
    
    def is_ready(self) -> bool:
        """
        Check if environment is ready for method calls
        
        Returns:
            True if backend is ready
        """
        return self._is_ready and self._backend.is_ready()
    
    def __getattr__(self, name: str):
        """
        Dynamic method dispatch
        
        Intercepts method calls and forwards them to the backend.
        This allows calling any method defined in env.py without
        hardcoding method names.
        
        Args:
            name: Method name
            
        Returns:
            Callable that executes the remote method
            
        Example:
            env.evaluate(...)  # Calls Actor.evaluate() or evaluate()
            env.custom_func()  # Calls any function from env.py
        """
        # Prevent infinite recursion for private attributes
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        
        # Check if environment is ready
        if not self._is_ready:
            raise EnvironmentError(
                f"Environment '{self.name}' not ready."
            )
        
        # Return an async callable that will invoke the remote method
        async def method_caller(*args, timeout: Optional[int] = None, **kwargs):
            """
            Execute remote method (async)
            
            Args:
                *args: Positional arguments
                timeout: Optional timeout in seconds
                **kwargs: Keyword arguments
                
            Returns:
                Method result
            """
            try:
                logger.debug(f"Calling method '{name}' on environment '{self.name}'")
                
                result = await self._backend.call_method(
                    name,
                    *args,
                    timeout=timeout,
                    **kwargs
                )
                
                logger.debug(f"Method '{name}' completed successfully")
                return result
                
            except Exception as e:
                raise EnvironmentError(
                    f"Method '{name}' failed on environment '{self.name}': {e}"
                )
        
        return method_caller
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatic cleanup"""
        # Run async cleanup in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.cleanup())
            else:
                loop.run_until_complete(self.cleanup())
        except Exception as e:
            logger.warning(f"Error during async cleanup in __exit__: {e}")
    
    def __del__(self):
        """Cleanup on deletion"""
        if self._is_ready:
            # Run async cleanup in sync context
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.cleanup())
                else:
                    loop.run_until_complete(self.cleanup())
            except Exception as e:
                logger.warning(f"Error during async cleanup in __del__: {e}")
    
    def get_stats(self) -> Optional[dict]:
        """
        Get statistics for multi-instance pools
        
        Returns:
            Pool statistics dict if using InstancePool, None otherwise
        """
        if self._is_pool:
            return self._backend.get_stats()
        return None
    
    def __repr__(self) -> str:
        """String representation"""
        status = "ready" if self.is_ready() else "not ready"
        if self._is_pool:
            stats = self._backend.get_stats()
            healthy = stats.get("healthy_instances", 0)
            total = stats.get("total_instances", 0)
            return f"<EnvironmentWrapper '{self.name}' (pool: {healthy}/{total} healthy, {status})>"
        return f"<EnvironmentWrapper '{self.name}' ({status})>"