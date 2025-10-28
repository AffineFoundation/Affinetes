"""Global configuration with environment variable overrides"""

import os
from typing import Tuple


class Config:
    """Global configuration with sensible defaults"""
    
    # Ray configuration
    RAY_PORT_RANGE: Tuple[int, int] = (6379, 6479)
    RAY_CONNECTION_TIMEOUT: int = 30  # seconds
    RAY_START_TIMEOUT: int = 30  # seconds to wait for Ray cluster to start
    
    # Container configuration
    CONTAINER_STARTUP_TIMEOUT: int = 30  # seconds
    CONTAINER_NAME_PREFIX: str = "affinetes"
    
    # Image configuration
    IMAGE_BUILD_TIMEOUT: int = 600  # seconds
    DEFAULT_IMAGE_PREFIX: str = "affinetes"
    DEFAULT_REGISTRY: str | None = None
    
    # Logging
    LOG_LEVEL: str = os.getenv("RAYFINE_LOG_LEVEL", "INFO")
    
    # Environment file path (inside container)
    ENV_MODULE_PATH: str = "/app/env.py"
    
    @classmethod
    def get_ray_port_range(cls) -> Tuple[int, int]:
        """Get Ray port range from env or default"""
        start = int(os.getenv("RAYFINE_RAY_PORT_START", cls.RAY_PORT_RANGE[0]))
        end = int(os.getenv("RAYFINE_RAY_PORT_END", cls.RAY_PORT_RANGE[1]))
        return (start, end)
    
    @classmethod
    def get_log_level(cls) -> str:
        """Get log level from env or default"""
        return os.getenv("RAYFINE_LOG_LEVEL", cls.LOG_LEVEL)