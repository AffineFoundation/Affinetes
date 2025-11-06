"""Global environment registry for tracking active environments"""

import atexit
import asyncio
from typing import Dict, Optional
from threading import Lock

from ..utils.logger import logger


class EnvironmentRegistry:
    """
    Singleton registry for tracking active environment instances
    
    Ensures proper cleanup of all environments on exit and
    provides global access to environment instances.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._environments: Dict[str, any] = {}
        self._lock = Lock()
        self._initialized = True
        
        # Register cleanup on exit
        atexit.register(self.cleanup_all)
        
        logger.debug("EnvironmentRegistry initialized")
    
    def register(self, env_id: str, environment: any) -> None:
        """
        Register an environment instance
        
        Args:
            env_id: Unique environment identifier
            environment: Environment wrapper instance
        """
        with self._lock:
            if env_id in self._environments:
                logger.warning(f"Environment '{env_id}' already registered, replacing")
            
            self._environments[env_id] = environment
            logger.debug(f"Registered environment '{env_id}'")
    
    def unregister(self, env_id: str) -> None:
        """
        Unregister an environment
        
        Args:
            env_id: Environment identifier
        """
        with self._lock:
            if env_id in self._environments:
                del self._environments[env_id]
                logger.debug(f"Unregistered environment '{env_id}'")
    
    def get(self, env_id: str) -> Optional[any]:
        """
        Get environment by ID
        
        Args:
            env_id: Environment identifier
            
        Returns:
            Environment instance or None
        """
        with self._lock:
            return self._environments.get(env_id)
    
    def list_all(self) -> list:
        """
        List all registered environment IDs
        
        Returns:
            List of environment IDs
        """
        with self._lock:
            return list(self._environments.keys())
    
    def cleanup_all(self) -> None:
        """Clean up all registered environments"""
        with self._lock:
            if not self._environments:
                return
            
            # Copy keys to avoid modification during iteration
            env_ids = list(self._environments.keys())
            
            for env_id in env_ids:
                try:
                    env = self._environments[env_id]
                    
                    # Check if backend has auto_cleanup enabled
                    auto_cleanup = getattr(env._backend, '_auto_cleanup', True)
                    if not auto_cleanup:
                        logger.debug(f"Skipping cleanup for '{env_id}' (auto_cleanup=False)")
                        continue
                    
                    logger.debug(f"Cleaning up environment '{env_id}'")
                    
                    # Handle async cleanup properly
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # If loop is running, schedule cleanup as a task
                            asyncio.create_task(env.cleanup())
                        else:
                            loop.run_until_complete(env.cleanup())
                    except RuntimeError:
                        # No event loop, create new one
                        asyncio.run(env.cleanup())
                        
                except Exception as e:
                    logger.error(f"Error cleaning up environment '{env_id}': {e}")
                finally:
                    # Remove from registry even if cleanup failed
                    self._environments.pop(env_id, None)
            
            logger.debug("All environments cleaned up")
    
    def count(self) -> int:
        """
        Get number of registered environments
        
        Returns:
            Environment count
        """
        with self._lock:
            return len(self._environments)


# Global registry instance
_registry = EnvironmentRegistry()


def get_registry() -> EnvironmentRegistry:
    """
    Get global environment registry
    
    Returns:
        EnvironmentRegistry instance
    """
    return _registry