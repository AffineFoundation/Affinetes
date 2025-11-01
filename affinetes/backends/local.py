"""Local backend - Docker + async HTTP execution"""

import time
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any

import nest_asyncio
nest_asyncio.apply()

from .base import AbstractBackend
from ..infrastructure import DockerManager, HTTPExecutor, EnvType
from ..infrastructure.ssh_tunnel import SSHTunnelManager
from ..utils.exceptions import BackendError, SetupError
from ..utils.logger import logger
from ..utils.config import Config


class LocalBackend(AbstractBackend):
    """
    Local execution backend using Docker containers and HTTP
    
    Lifecycle:
    1. __init__: Start Docker container with HTTP server
    2. call_method(): Execute methods via HTTP API
    3. cleanup(): Stop container
    """
    
    def __init__(
        self,
        image: str,
        host: Optional[str] = None,
        container_name: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        env_type_override: Optional[str] = None,
        force_recreate: bool = False,
        pull: bool = False,
        mem_limit: Optional[str] = None,
        **docker_kwargs
    ):
        """
        Initialize backend - starts Docker container
        
        Args:
            image: Docker image name
            host: Docker daemon address (None/"localhost" for local, "ssh://user@host" for remote)
            container_name: Optional container name
            env_vars: Environment variables to pass to container
            env_type_override: Override environment type detection
            force_recreate: If True, remove existing container and create new one
            pull: If True, pull image before starting container
            mem_limit: Memory limit (e.g., "512m", "1g", "2g")
            **docker_kwargs: Additional Docker container options
        """
        self.image = image
        self.host = host
        # Sanitize image name for container naming (remove / and :)
        safe_image = image.split('/')[-1].replace(':', '-')
        self.name = container_name or f"{safe_image}"
        
        self._container = None
        self._docker_manager = None
        self._http_executor = None
        self._is_setup = False
        self._env_type = None
        self._env_type_override = env_type_override
        self._force_recreate = force_recreate
        self._pull = pull
        self._mem_limit = mem_limit
        
        # SSH tunnel for remote access
        self._is_remote = host and host.startswith("ssh://")
        self._ssh_tunnel_manager = None
        
        # Start container with env vars
        self._start_container(env_vars=env_vars, **docker_kwargs)
    
    def _start_container(self, env_vars: Optional[Dict[str, str]] = None, **docker_kwargs) -> None:
        """Start Docker container with HTTP server
        
        Args:
            env_vars: Environment variables to pass to container
            **docker_kwargs: Additional Docker options
        """
        try:
            logger.debug(f"Starting container for image '{self.image}' on host '{self.host or 'localhost'}'")
            
            # Initialize Docker manager with host support (must be done before env_type detection)
            self._docker_manager = DockerManager(host=self.host)
            
            # Get environment type
            if self._env_type_override:
                self._env_type = self._env_type_override
                logger.info(f"Environment type (manual): {self._env_type}")
            else:
                self._env_type = self._get_env_type()
                logger.info(f"Environment type (detected): {self._env_type}")
            
            # Pull image if requested
            if self._pull:
                self._docker_manager.pull_image(self.image)
            
            # Merge environment variables
            if env_vars:
                if "environment" in docker_kwargs:
                    docker_kwargs["environment"].update(env_vars)
                else:
                    docker_kwargs["environment"] = env_vars
            
            # Prepare container configuration (no port exposure)
            container_config = {
                "image": self.image,
                "name": self.name,
                "detach": True,
                "restart_policy": {"Name": "always"},
                "force_recreate": self._force_recreate,
                "mem_limit": self._mem_limit,
                **docker_kwargs
            }
            
            # Start container
            self._container = self._docker_manager.start_container(**container_config)
            
            # Get container internal IP
            container_ip = self._docker_manager.get_container_ip(self._container)
            logger.info(f"Container started with internal IP: {container_ip}")
            
            # Determine access method: direct or via SSH tunnel
            if self._is_remote:
                # Remote deployment: create SSH tunnel
                logger.debug("Remote deployment detected, creating SSH tunnel")
                self._ssh_tunnel_manager = SSHTunnelManager(self.host)
                local_host, local_port = self._ssh_tunnel_manager.create_tunnel(
                    remote_ip=container_ip,
                    remote_port=8000
                )
                logger.info(f"Accessing via SSH tunnel: {local_host}:{local_port}")
            else:
                # Local deployment: direct access
                local_host = container_ip
                local_port = 8000
                logger.debug(f"Local deployment, direct access: {local_host}:{local_port}")
            
            # Create HTTP executor with accessible address
            self._http_executor = HTTPExecutor(
                container_ip=local_host,
                container_port=local_port,
                env_type=self._env_type,
                timeout=600
            )
            
            # Wait for HTTP server to be ready
            timeout = 120 if self._env_type == EnvType.HTTP_BASED else 60
            access_info = f"{local_host}:{local_port}"
            logger.debug(f"Waiting for HTTP server at {access_info} (timeout={timeout}s)")
            
            # Run async health check in sync context
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if not loop.run_until_complete(self._wait_for_http_ready(timeout=timeout)):
                raise BackendError(
                    f"HTTP server did not start within {timeout}s. "
                    "Check container logs for errors."
                )
            
            # Mark as setup - HTTP backend is ready after container starts
            self._is_setup = True
            logger.debug("Container started and HTTP server ready")
            
        except Exception as e:
            # Cleanup on failure
            if self._ssh_tunnel_manager:
                try:
                    self._ssh_tunnel_manager.cleanup()
                except:
                    pass
            if self._container:
                try:
                    self._docker_manager.stop_container(self._container)
                except:
                    pass
            raise BackendError(f"Failed to start container: {e}")
    
    def _get_env_type(self) -> str:
        """Get environment type from image labels"""
        try:
            img = self._docker_manager.client.images.get(self.image)
            labels = img.labels or {}
            env_type = labels.get("affinetes.env.type", EnvType.FUNCTION_BASED)
            logger.debug(f"Detected env_type from image labels: {env_type}")
            return env_type
        except Exception as e:
            logger.warning(f"Failed to get env type from image: {e}, defaulting to function_based")
            return EnvType.FUNCTION_BASED
    
    async def _wait_for_http_ready(self, timeout: int = 60) -> bool:
        """Wait for HTTP server to be ready (async)"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                if await self._http_executor.health_check():
                    return True
            except Exception as e:
                logger.debug(f"Health check failed: {e}")
            await asyncio.sleep(1)
        return False
    
    async def call_method(
        self,
        method_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Call a method from env.py via HTTP (async)
        
        Args:
            method_name: Method name to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Method result
        """
        try:
            return await self._http_executor.call_method(
                method_name,
                *args,
                **kwargs
            )
        except Exception as e:
            raise BackendError(f"Method call failed: {e}")
    
    async def list_methods(self) -> list:
        """
        List all available methods from env.py (async)
        
        Returns:
            List of method names
        """
        try:
            return await self._http_executor.list_methods()
        except Exception as e:
            raise BackendError(f"Failed to list methods: {e}")
    
    async def cleanup(self) -> None:
        """Stop container and close HTTP client (async)"""
        logger.debug(f"Cleaning up backend for container {self.name}")
        
        # Close HTTP client
        if self._http_executor:
            try:
                await self._http_executor.close()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
            finally:
                self._http_executor = None
        
        # Close SSH tunnel if exists
        if self._ssh_tunnel_manager:
            try:
                self._ssh_tunnel_manager.cleanup()
            except Exception as e:
                logger.warning(f"Error closing SSH tunnel: {e}")
            finally:
                self._ssh_tunnel_manager = None
        
        # Stop container
        if self._container and self._docker_manager:
            try:
                self._docker_manager.stop_container(self._container)
            except Exception as e:
                logger.warning(f"Error stopping container: {e}")
            finally:
                self._container = None
        
        self._is_setup = False
        logger.debug("Backend cleanup completed")
    
    def is_ready(self) -> bool:
        """
        Check if backend is ready for method calls
        
        Returns:
            True if setup completed
        """
        return self._is_setup
    
    def get_container_logs(self, tail: int = 100) -> str:
        """
        Get container logs for debugging
        
        Args:
            tail: Number of lines to return
            
        Returns:
            Log output
        """
        if not self._container:
            return ""
        
        try:
            logs = self._container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            return ""
    
    def __del__(self):
        """Cleanup on deletion"""
        # Run async cleanup in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule cleanup as a task
                asyncio.create_task(self.cleanup())
            else:
                loop.run_until_complete(self.cleanup())
        except Exception as e:
            logger.warning(f"Error during async cleanup in __del__: {e}")