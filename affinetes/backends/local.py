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
            
            # Pull image if requested (must be done BEFORE env_type detection)
            if self._pull:
                self._docker_manager.pull_image(self.image)
            
            # Get environment type
            if self._env_type_override:
                self._env_type = self._env_type_override
                logger.info(f"Environment type (manual): {self._env_type}")
            else:
                self._env_type = self._get_env_type()
                logger.info(f"Environment type (detected): {self._env_type}")
            
            # Merge environment variables
            if env_vars:
                if "environment" in docker_kwargs:
                    docker_kwargs["environment"].update(env_vars)
                else:
                    docker_kwargs["environment"] = env_vars
            
            # Detect if running inside Docker (DinD scenario)
            is_running_in_docker = self._is_running_in_docker()
            
            # Prepare container configuration
            container_config = {
                "image": self.image,
                "name": self.name,
                "detach": True,
                "restart_policy": {"Name": "always"},
                "force_recreate": self._force_recreate,
                "mem_limit": self._mem_limit,
                **docker_kwargs
            }
            
            # If running in Docker, ensure network connectivity
            if is_running_in_docker and not self._is_remote:
                network_name = self._ensure_docker_network()
                container_config["network"] = network_name
                logger.debug(f"Running in Docker, using network: {network_name}")
            
            # Start container
            self._container = self._docker_manager.start_container(**container_config)
            
            # Determine access address
            if self._is_remote:
                # Remote deployment: create SSH tunnel
                container_ip = self._docker_manager.get_container_ip(self._container)
                logger.debug("Remote deployment detected, creating SSH tunnel")
                self._ssh_tunnel_manager = SSHTunnelManager(self.host)
                local_host, local_port = self._ssh_tunnel_manager.create_tunnel(
                    remote_ip=container_ip,
                    remote_port=8000
                )
                logger.info(f"Accessing via SSH tunnel: {local_host}:{local_port}")
            elif is_running_in_docker:
                # DinD scenario: use container name as hostname
                local_host = self.name
                local_port = 8000
                logger.info(f"DinD deployment, accessing via container name: {local_host}:{local_port}")
            else:
                # Normal local deployment: use container IP
                container_ip = self._docker_manager.get_container_ip(self._container)
                local_host = container_ip
                local_port = 8000
                logger.info(f"Local deployment, accessing via IP: {local_host}:{local_port}")
            
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
    
    def _is_running_in_docker(self) -> bool:
        """Check if affinetes itself is running inside a Docker container"""
        import os
        
        # Method 1: Check for .dockerenv file
        if os.path.exists("/.dockerenv"):
            return True
        
        # Method 2: Check cgroup (most reliable)
        try:
            with open("/proc/1/cgroup", "r") as f:
                content = f.read()
                # Docker containers have /docker/ in cgroup paths
                if "/docker/" in content or "/kubepods/" in content:
                    return True
        except (FileNotFoundError, PermissionError):
            pass
        
        # Method 3: Check for container-specific mount info
        try:
            with open("/proc/self/mountinfo", "r") as f:
                content = f.read()
                if "/docker/" in content or "overlay" in content:
                    return True
        except (FileNotFoundError, PermissionError):
            pass
        
        return False
    
    def _ensure_docker_network(self) -> str:
        """Ensure Docker network exists and affinetes container is connected to it"""
        import socket
        
        # Get current container's networks (affinetes container)
        try:
            hostname = socket.gethostname()
            current_container = self._docker_manager.client.containers.get(hostname)
            current_container.reload()
            
            # Get all networks the affinetes container is connected to
            current_networks = list(current_container.attrs["NetworkSettings"]["Networks"].keys())
            logger.debug(f"Current container networks: {current_networks}")
            
            # Prefer using an existing network (not 'bridge' or 'host')
            # This ensures env containers join the same network as affinetes
            for net_name in current_networks:
                if net_name not in ["bridge", "host", "none"]:
                    logger.info(f"Using affinetes container's network: {net_name}")
                    return net_name
            
            # If only on default bridge, create/use affinetes-network
            network_name = "affinetes-network"
            
            # Ensure network exists
            try:
                network = self._docker_manager.client.networks.get(network_name)
                logger.debug(f"Network {network_name} exists")
            except:
                # Create network
                network = self._docker_manager.client.networks.create(
                    network_name,
                    driver="bridge",
                    check_duplicate=True
                )
                logger.info(f"Created network: {network_name}")
            
            # Connect affinetes container to this network
            network.reload()
            if current_container.id not in [c.id for c in network.containers]:
                network.connect(current_container)
                logger.info(f"Connected affinetes container to {network_name}")
            else:
                logger.debug(f"Affinetes container already in {network_name}")
            
            return network_name
            
        except Exception as e:
            # Fallback: use default approach
            logger.warning(f"Could not determine current container network: {e}")
            logger.warning("Falling back to affinetes-network")
            
            network_name = "affinetes-network"
            try:
                self._docker_manager.client.networks.get(network_name)
            except:
                self._docker_manager.client.networks.create(
                    network_name,
                    driver="bridge",
                    check_duplicate=True
                )
            return network_name
    
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