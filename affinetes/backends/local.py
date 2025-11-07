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
        image: Optional[str] = None,
        host: Optional[str] = None,
        container_name: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        env_type_override: Optional[str] = None,
        force_recreate: bool = False,
        pull: bool = False,
        mem_limit: Optional[str] = None,
        auto_cleanup: bool = True,
        connect_only: bool = False,
        **docker_kwargs
    ):
        """
        Initialize backend - starts Docker container or connects to existing one
        
        Args:
            image: Docker image name (required unless connect_only=True)
            host: Docker daemon address (None/"localhost" for local, "ssh://user@host" for remote)
            container_name: Container name (required if connect_only=True)
            env_vars: Environment variables to pass to container
            env_type_override: Override environment type detection
            force_recreate: If True, remove existing container and create new one
            pull: If True, pull image before starting container
            mem_limit: Memory limit (e.g., "512m", "1g", "2g")
            auto_cleanup: If True, automatically stop and remove container on cleanup (default: True)
                         If False, container will continue running after cleanup
            connect_only: If True, only connect to existing container without creating new one
            **docker_kwargs: Additional Docker container options
        """
        self.image = image
        self.host = host
        self._connect_only = connect_only
        
        # Validate parameters
        if connect_only:
            if not container_name:
                raise ValueError("container_name is required when connect_only=True")
            self.name = container_name
        else:
            if not image:
                raise ValueError("image is required when connect_only=False")
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
        self._auto_cleanup = auto_cleanup
        
        # SSH tunnel for remote access
        self._is_remote = host and host.startswith("ssh://")
        self._ssh_tunnel_manager = None
        
        # Connect to existing container or start new one
        if connect_only:
            self._connect_to_container()
        else:
            self._start_container(env_vars=env_vars, **docker_kwargs)
    
    def _connect_to_container(self) -> None:
        """Connect to existing Docker container without creating new one"""
        try:
            logger.debug(f"Connecting to existing container '{self.name}' on host '{self.host or 'localhost'}'")
            
            # Initialize Docker manager
            self._docker_manager = DockerManager(host=self.host)
            
            # Get existing container
            try:
                self._container = self._docker_manager.client.containers.get(self.name)
            except Exception as e:
                raise BackendError(f"Container '{self.name}' not found: {e}")
            
            # Check container status
            self._container.reload()
            if self._container.status != 'running':
                raise BackendError(f"Container '{self.name}' is not running (status: {self._container.status})")
            
            # Get environment type from container labels
            if self._env_type_override:
                self._env_type = self._env_type_override
                logger.info(f"Environment type (manual): {self._env_type}")
            else:
                labels = self._container.labels or {}
                self._env_type = labels.get("affinetes.env.type", EnvType.FUNCTION_BASED)
                logger.info(f"Environment type (from container): {self._env_type}")
            
            # Determine access address (same logic as _start_container)
            if self._is_remote:
                # Remote: create SSH tunnel
                container_ip = self._docker_manager.get_container_ip(self._container)
                logger.debug("Remote connection detected, creating SSH tunnel")
                self._ssh_tunnel_manager = SSHTunnelManager(self.host)
                local_host, local_port = self._ssh_tunnel_manager.create_tunnel(
                    remote_ip=container_ip,
                    remote_port=8000
                )
                logger.info(f"Accessing via SSH tunnel: {local_host}:{local_port}")
            else:
                # Local deployment: check if in DinD scenario
                is_running_in_docker = self._is_running_in_docker()
                if is_running_in_docker:
                    # DinD: use container name as hostname
                    local_host = self.name
                    local_port = 8000
                    logger.info(f"Local DinD detected, accessing via container name: {local_host}:{local_port}")
                else:
                    # Normal local: use container IP
                    container_ip = self._docker_manager.get_container_ip(self._container)
                    local_host = container_ip
                    local_port = 8000
                    logger.info(f"Local connection, accessing via IP: {local_host}:{local_port}")
            
            # Create HTTP executor
            self._http_executor = HTTPExecutor(
                container_ip=local_host,
                container_port=local_port,
                env_type=self._env_type,
                timeout=600
            )
            
            # Verify HTTP server is ready
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if not loop.run_until_complete(self._wait_for_http_ready(timeout=10)):
                raise BackendError(
                    f"HTTP server not responding. "
                    f"Container '{self.name}' may not be ready or misconfigured."
                )
            
            self._is_setup = True
            logger.debug(f"Successfully connected to container '{self.name}'")
            
        except Exception as e:
            # Cleanup on failure
            if self._ssh_tunnel_manager:
                try:
                    self._ssh_tunnel_manager.cleanup()
                except:
                    pass
            raise BackendError(f"Failed to connect to container: {e}")
    
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
            
            # Network handling: Only needed for local DinD deployment
            # Remote deployment uses SSH tunnel, so no network configuration needed
            if not self._is_remote:
                # Local deployment: check if running inside Docker (DinD scenario)
                is_running_in_docker = self._is_running_in_docker()
                if is_running_in_docker:
                    network_name = self._ensure_docker_network()
                    # Set the network for the new environment container
                    # This ensures it joins the same network as affinetes container
                    container_config["network"] = network_name
                    logger.info(f"Local DinD detected, connecting environment container to network: {network_name}")
            
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
            else:
                # Local deployment: check if in DinD scenario
                is_running_in_docker = self._is_running_in_docker()
                if is_running_in_docker:
                    # DinD scenario: use container name as hostname
                    local_host = self.name
                    local_port = 8000
                    logger.info(f"Local DinD deployment, accessing via container name: {local_host}:{local_port}")
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
        p1 = open("/proc/1/comm").read().strip().lower()
        if p1 not in ("systemd", "init"):
            return True
        return False

    def _ensure_docker_network(self) -> str:
        """Get the network name that affinetes container is connected to
        
        Strategy: Parse container ID from mountinfo using regex pattern matching
        This works for all Docker environments and is resilient to path changes.
        """
        import re
        
        try:
            # Regex pattern to match 64-character hex container IDs in mountinfo
            # Matches IDs in paths like:
            # - /var/lib/docker/containers/<id>/...
            # - /docker/containers/<id>/...
            # - Any other path containing containers/<id>/
            container_id_pattern = re.compile(r'/containers/([0-9a-f]{64})/')
            
            container_id = None
            with open("/proc/self/mountinfo", "r") as f:
                for line in f:
                    match = container_id_pattern.search(line)
                    if match:
                        container_id = match.group(1)
                        logger.debug(f"Found container ID from mountinfo: {container_id[:12]}...")
                        break
            
            if not container_id:
                logger.warning("Could not extract container ID from mountinfo")
                return "bridge"
            
            # Query Docker API with full container ID
            try:
                current_container = self._docker_manager.client.containers.get(container_id)
                logger.debug(f"Found container: {current_container.name}")
                
                # Extract network information
                current_container.reload()
                networks = current_container.attrs["NetworkSettings"]["Networks"]
                network_names = list(networks.keys())
                logger.info(f"Container '{current_container.name}' networks: {network_names}")
            except Exception as container_err:
                logger.debug(f"Container {container_id[:12]}... not found or inaccessible: {container_err}")
                logger.info("Using default bridge network")
                return "bridge"
            
            # Return first non-default network, or first network if all are default
            for net_name in network_names:
                if net_name not in ["host", "none"]:
                    logger.info(f"Environment containers will use network: {net_name}")
                    return net_name
            
            if network_names:
                logger.info(f"Using network: {network_names[0]}")
                return network_names[0]
            
        except FileNotFoundError:
            logger.warning("Not running in Docker (mountinfo not found)")
        except Exception as e:
            logger.warning(f"Failed to detect network: {e}")
        
        # Fallback when not running in Docker
        logger.warning("Using default bridge network")
        return "bridge"
    
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
    
    async def health_check(self) -> bool:
        """
        Check if backend is healthy and responsive
        
        Returns:
            True if healthy, False otherwise
        """
        if not self._is_setup or not self._http_executor:
            return False
        
        try:
            # Check if container is still running
            if self._container:
                self._container.reload()
                if self._container.status != 'running':
                    logger.warning(f"Container {self.name} is not running (status: {self._container.status})")
                    return False
            
            # Check HTTP endpoint
            return await self._http_executor.health_check()
        
        except Exception as e:
            logger.debug(f"Health check failed for {self.name}: {e}")
            return False
    
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
