"""SSH tunnel management for remote Docker container access"""

import socket
import threading
import select
from typing import Optional, Tuple
from contextlib import closing

import paramiko

from ..utils.logger import logger
from ..utils.exceptions import BackendError


def find_free_port() -> int:
    """Find an available local port"""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class SSHTunnelManager:
    """Manages SSH port forwarding for remote container access using paramiko"""
    
    def __init__(self, ssh_url: str):
        """
        Initialize SSH tunnel manager
        
        Args:
            ssh_url: SSH URL in format "ssh://user@host" or "ssh://user@host:port"
        """
        self._parse_ssh_url(ssh_url)
        self._ssh_client: Optional[paramiko.SSHClient] = None
        self._transport: Optional[paramiko.Transport] = None
        self._local_port: Optional[int] = None
        self._server_socket: Optional[socket.socket] = None
        self._tunnel_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
    def _parse_ssh_url(self, ssh_url: str):
        """Parse SSH URL into components"""
        if not ssh_url.startswith("ssh://"):
            raise ValueError(f"Invalid SSH URL: {ssh_url}")
        
        # Remove ssh:// prefix
        url = ssh_url[6:]
        
        # Parse user@host:port
        if '@' not in url:
            raise ValueError(f"SSH URL must contain user: {ssh_url}")
        
        user_host = url.split('@', 1)
        self.ssh_user = user_host[0]
        
        host_port = user_host[1].split(':', 1)
        self.ssh_host = host_port[0]
        self.ssh_port = int(host_port[1]) if len(host_port) > 1 else 22
        
        logger.debug(
            f"Parsed SSH URL: user={self.ssh_user}, "
            f"host={self.ssh_host}, port={self.ssh_port}"
        )
    
    def _connect_ssh(self):
        """Establish SSH connection using system SSH agent"""
        try:
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using SSH agent (no need to specify key files)
            self._ssh_client.connect(
                hostname=self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                look_for_keys=True,
                allow_agent=True,
                timeout=10
            )
            
            self._transport = self._ssh_client.get_transport()
            logger.debug(f"SSH connection established to {self.ssh_host}")
            
        except Exception as e:
            if self._ssh_client:
                self._ssh_client.close()
            raise BackendError(f"Failed to connect via SSH: {e}")
    
    def _forward_tunnel(self, local_port: int, remote_ip: str, remote_port: int):
        """Background thread for port forwarding"""
        def forward_data(src, dst):
            try:
                while True:
                    data = src.recv(1024)
                    if not data:
                        break
                    dst.sendall(data)
            except:
                pass
            finally:
                src.close()
                dst.close()
        
        try:
            while not self._stop_event.is_set():
                ready = select.select([self._server_socket], [], [], 1.0)
                if not ready[0]:
                    continue
                
                client_socket, addr = self._server_socket.accept()
                
                try:
                    channel = self._transport.open_channel(
                        "direct-tcpip",
                        (remote_ip, remote_port),
                        addr
                    )
                    
                    for src, dst in [(client_socket, channel), (channel, client_socket)]:
                        t = threading.Thread(target=forward_data, args=(src, dst), daemon=True)
                        t.start()
                    
                except Exception as e:
                    logger.debug(f"Error forwarding connection: {e}")
                    client_socket.close()
                    
        except Exception as e:
            logger.error(f"Tunnel thread error: {e}")
    
    def create_tunnel(
        self,
        remote_ip: str,
        remote_port: int
    ) -> Tuple[str, int]:
        """
        Create SSH port forward from local to remote
        
        Args:
            remote_ip: Remote container IP (e.g., "172.17.0.4")
            remote_port: Remote container port (e.g., 8000)
            
        Returns:
            (local_host, local_port) tuple for accessing the remote service
        """
        with self._lock:
            if self._ssh_client:
                raise BackendError("Tunnel already active for this manager")
            
            try:
                # Connect SSH
                self._connect_ssh()
                
                # Find available local port
                self._local_port = find_free_port()
                
                # Create local server socket
                self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server_socket.bind(('127.0.0.1', self._local_port))
                self._server_socket.listen(5)
                
                logger.debug(
                    f"Creating SSH tunnel: localhost:{self._local_port} -> "
                    f"{self.ssh_host} -> {remote_ip}:{remote_port}"
                )
                
                # Start forwarding thread
                self._stop_event.clear()
                self._tunnel_thread = threading.Thread(
                    target=self._forward_tunnel,
                    args=(self._local_port, remote_ip, remote_port),
                    daemon=True
                )
                self._tunnel_thread.start()
                
                logger.info(
                    f"SSH tunnel established: localhost:{self._local_port} -> "
                    f"{remote_ip}:{remote_port}"
                )
                
                return ("127.0.0.1", self._local_port)
                
            except Exception as e:
                self.cleanup()
                raise BackendError(f"Failed to create SSH tunnel: {e}")
    
    def is_active(self) -> bool:
        """Check if tunnel is active"""
        return (self._ssh_client is not None and
                self._transport is not None and
                self._transport.is_active())
    
    def cleanup(self):
        """Close SSH tunnel"""
        with self._lock:
            # Stop forwarding thread
            if self._tunnel_thread:
                self._stop_event.set()
                self._tunnel_thread.join(timeout=2)
                self._tunnel_thread = None
            
            # Close server socket
            if self._server_socket:
                try:
                    self._server_socket.close()
                except:
                    pass
                self._server_socket = None
            
            # Close SSH connection
            if self._ssh_client:
                try:
                    logger.debug("Closing SSH connection")
                    self._ssh_client.close()
                    logger.debug("SSH connection closed")
                except Exception as e:
                    logger.warning(f"Error closing SSH connection: {e}")
                finally:
                    self._ssh_client = None
                    self._transport = None
    
    def __del__(self):
        """Cleanup on deletion"""
        self.cleanup()
    
    def __repr__(self) -> str:
        """String representation"""
        status = "active" if self.is_active() else "inactive"
        return f"<SSHTunnelManager {self.ssh_user}@{self.ssh_host} ({status})>"