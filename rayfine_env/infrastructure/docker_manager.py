"""Docker container lifecycle management"""

import docker
import time
from typing import Dict, Optional, Any

from ..utils.exceptions import ContainerError, ImageNotFoundError
from ..utils.logger import logger


class DockerManager:
    """Manages Docker container lifecycle operations"""
    
    def __init__(self, host: Optional[str] = None):
        """
        Initialize Docker manager
        
        Args:
            host: Docker daemon address
                - None or "localhost": Local socket connection
                - "ssh://user@host": SSH connection to remote daemon
        """
        try:
            if host and host.startswith("ssh://"):
                # SSH connection to remote Docker daemon
                self.client = docker.DockerClient(base_url=host)
                logger.info(f"Connected to remote Docker daemon via SSH: {host}")
            else:
                # Local socket connection
                self.client = docker.from_env()
                logger.debug("Connected to local Docker daemon")
            
            self.client.ping()
        except Exception as e:
            raise ContainerError(f"Failed to connect to Docker daemon: {e}")
    
    def get_existing_container(self, name: str) -> Optional[Any]:
        """
        Get existing container by name if it exists
        
        Args:
            name: Container name
            
        Returns:
            Container object if exists (running or stopped), None otherwise
        """
        try:
            container = self.client.containers.get(name)
            container.reload()
            logger.debug(f"Found container {name} with status: {container.status}")
            return container
                
        except docker.errors.NotFound:
            logger.debug(f"Container {name} not found")
            return None
        except Exception as e:
            logger.warning(f"Error checking for existing container {name}: {e}")
            return None
    
    def remove_container(self, name: str) -> bool:
        """
        Remove a container by name (force remove)
        
        Args:
            name: Container name
            
        Returns:
            True if removed, False if not found
        """
        try:
            container = self.client.containers.get(name)
            container.remove(force=True)
            logger.debug(f"Container {name} removed")
            return True
        except docker.errors.NotFound:
            return False
        except Exception as e:
            logger.warning(f"Error removing container {name}: {e}")
            return False
    
    def start_container(
        self,
        image: str,
        name: Optional[str] = None,
        detach: bool = True,
        force_recreate: bool = False,
        **kwargs
    ) -> Any:
        """
        Start a Docker container (no port exposure)
        
        Args:
            image: Docker image name (e.g., "affine:latest")
            name: Optional container name
            detach: Run container in background
            force_recreate: If True, remove existing container and create new one
            **kwargs: Additional docker.containers.run() parameters
            
        Returns:
            Container object
            
        Raises:
            ImageNotFoundError: If image doesn't exist
            ContainerError: If container fails to start
        """
        try:
            # Check if image exists
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                raise ImageNotFoundError(f"Image '{image}' not found. Build it first using build_image_from_env()")
            
            # Check for existing container if name is provided
            if name:
                existing = self.get_existing_container(name)
                if existing:
                    if force_recreate:
                        # Force recreate: remove and create new
                        logger.info(f"Force recreating container: {name}")
                        self.remove_container(name)
                    else:
                        # Reuse existing container
                        if existing.status == "running":
                            logger.info(f"Reusing running container: {name}")
                            return existing
                        else:
                            # Container exists but not running, restart it
                            logger.info(f"Restarting stopped container: {name}")
                            existing.start()
                            existing.reload()
                            if existing.status == "running":
                                return existing
                            else:
                                # Failed to restart, remove and recreate
                                logger.warning(f"Failed to restart container {name}, recreating")
                                self.remove_container(name)
            
            # Prepare container configuration (no port exposure)
            container_config = {
                "image": image,
                "detach": detach,
                "remove": False,
                "tty": True,
                "stdin_open": True,
                **kwargs
            }
            
            if name:
                container_config["name"] = name
            
            container = self.client.containers.run(**container_config)
            
            # Wait for container to be running
            container.reload()
            if container.status != "running":
                raise ContainerError(f"Container failed to start: {container.status}")
            
            logger.debug(f"Container {container.short_id} started successfully")
            return container
            
        except ImageNotFoundError:
            raise
        except docker.errors.APIError as e:
            raise ContainerError(f"Docker API error: {e}")
        except Exception as e:
            raise ContainerError(f"Failed to start container: {e}")
    
    def stop_container(self, container: Any, timeout: int = 10) -> None:
        """
        Stop and remove a container
        
        Args:
            container: Container object
            timeout: Seconds to wait before killing
        """
        try:
            container_id = container.short_id
            logger.debug(f"Stopping container {container_id}")
            
            container.stop(timeout=timeout)
            container.remove(force=True)
            
            logger.debug(f"Container {container_id} stopped and removed")
            
        except Exception as e:
            logger.warning(f"Error stopping container: {e}")
            # Try force removal
            try:
                container.remove(force=True)
            except:
                pass
    
    def get_container_ip(self, container: Any) -> str:
        """
        Get container IP address
        
        Args:
            container: Container object
            
        Returns:
            Container IP address
        """
        try:
            container.reload()
            networks = container.attrs["NetworkSettings"]["Networks"]
            # Get first network IP
            for network_name, network_info in networks.items():
                ip = network_info.get("IPAddress")
                if ip:
                    return ip
            
            raise ContainerError("No IP address found for container")
            
        except Exception as e:
            raise ContainerError(f"Failed to get container IP: {e}")
    
    def wait_for_port(
        self,
        container: Any,
        port: int,
        timeout: int = 30,
        interval: float = 0.5
    ) -> bool:
        """
        Wait for a port to be ready inside container
        
        Args:
            container: Container object
            port: Port number to check
            timeout: Maximum seconds to wait
            interval: Check interval in seconds
            
        Returns:
            True if port is ready, False if timeout
        """
        import socket
        
        start = time.time()
        container_ip = self.get_container_ip(container)
        
        logger.debug(f"Waiting for port {port} on {container_ip}")
        
        while time.time() - start < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((container_ip, port))
                sock.close()
                
                if result == 0:
                    logger.debug(f"Port {port} is ready")
                    return True
                    
            except Exception:
                pass
            
            time.sleep(interval)
        
        logger.warning(f"Timeout waiting for port {port}")
        return False
    
    def exec_command(
        self,
        container: Any,
        command: str,
        workdir: Optional[str] = None
    ) -> tuple:
        """
        Execute command inside container
        
        Args:
            container: Container object
            command: Command to execute
            workdir: Working directory
            
        Returns:
            (exit_code, output)
        """
        try:
            exec_config = {"cmd": command, "stdout": True, "stderr": True}
            if workdir:
                exec_config["workdir"] = workdir
            
            exit_code, output = container.exec_run(**exec_config)
            return exit_code, output.decode("utf-8")
            
        except Exception as e:
            raise ContainerError(f"Failed to execute command: {e}")
    
    def cleanup_all(self, name_pattern: Optional[str] = None) -> None:
        """
        Clean up containers matching pattern
        
        Args:
            name_pattern: Only remove containers with names containing this pattern
        """
        try:
            containers = self.client.containers.list(all=True)
            
            for container in containers:
                if name_pattern and name_pattern not in container.name:
                    continue
                
                try:
                    logger.info(f"Cleaning up container {container.short_id}")
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup {container.short_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")