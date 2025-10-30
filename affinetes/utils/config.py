"""Global configuration with environment variable overrides"""

import os
from typing import Tuple


class Config:
    """Global configuration with sensible defaults"""
    
    # Container configuration
    CONTAINER_STARTUP_TIMEOUT: int = 30  # seconds
    CONTAINER_NAME_PREFIX: str = "affinetes"
    
    # Image configuration
    IMAGE_BUILD_TIMEOUT: int = 600  # seconds
    DEFAULT_IMAGE_PREFIX: str = "affinetes"
    DEFAULT_REGISTRY: str | None = None
    
    # Logging
    LOG_LEVEL: str = os.getenv("AFFINETES_LOG_LEVEL", "INFO")
    
    # Environment file path (inside container)
    ENV_MODULE_PATH: str = "/app/env.py"
    
    @classmethod
    def get_log_level(cls) -> str:
        """Get log level from env or default"""
        return os.getenv("AFFINETES_LOG_LEVEL", cls.LOG_LEVEL)