"""Environment type detection"""

from pathlib import Path
from typing import Literal
import ast

from ..utils.logger import logger


class EnvType:
    """Environment type constants"""
    FUNCTION_BASED = "function_based"  # Needs server injection
    HTTP_BASED = "http_based"          # Has existing server


class EnvConfig:
    """Environment configuration"""
    
    def __init__(
        self,
        env_type: Literal["function_based", "http_based"],
        server_file: str = None,
        server_port: int = 8000
    ):
        self.env_type = env_type
        self.server_file = server_file  # For http_based, record server filename
        self.server_port = server_port


class EnvDetector:
    """Detect environment type and configuration"""
    
    # Known server file names (excluding env.py which needs special handling)
    SERVER_FILES = ["server.py", "app.py", "main.py"]
    
    # Web framework indicators
    WEB_FRAMEWORKS = [
        "FastAPI", "flask", "Flask", 
        "Starlette", "aiohttp",
        "@app.route", "@app.get", "@app.post",
        "app = FastAPI", "app = Flask"
    ]
    
    @staticmethod
    def detect(env_path: str) -> EnvConfig:
        """
        Detect environment type by checking env.py only
        
        Simple rule:
        - If env.py contains FastAPI and 'app', it's http_based
        - Otherwise, it's function_based
        
        Returns:
            EnvConfig with environment configuration
        """
        env_dir = Path(env_path).resolve()
        env_py = env_dir / "env.py"
        
        if not env_py.exists():
            raise ValueError(f"env.py not found in {env_path}")
        
        # Check if env.py contains FastAPI HTTP server
        try:
            code = env_py.read_text()
            
            # Check for FastAPI and app variable
            has_fastapi = "FastAPI" in code
            has_app = "app = " in code or "app=" in code
            
            if has_fastapi and has_app:
                logger.info("Detected HTTP server in env.py")
                return EnvConfig(
                    env_type=EnvType.HTTP_BASED,
                    server_file="env.py",
                    server_port=8000
                )
            else:
                logger.info("Detected function-based environment")
                return EnvConfig(
                    env_type=EnvType.FUNCTION_BASED,
                    server_file=None,
                    server_port=8000
                )
        except Exception as e:
            logger.error(f"Failed to read env.py: {e}")
            raise ValueError(f"Cannot detect environment type in {env_path}: {e}")