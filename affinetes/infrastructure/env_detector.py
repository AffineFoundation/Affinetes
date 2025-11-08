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
        Detect environment type by scanning all Python files
        
        Returns:
            EnvConfig with environment configuration
        """
        env_dir = Path(env_path).resolve()
        
        # Scan all Python files in the directory
        py_files = list(env_dir.glob("*.py"))
        
        # Check each Python file for HTTP server or function-based patterns
        for py_file in py_files:
            # Check if it's an HTTP server (by content, not filename)
            if EnvDetector._is_http_server(py_file):
                logger.info(f"Detected HTTP server in {py_file.name}")
                return EnvConfig(
                    env_type=EnvType.HTTP_BASED,
                    server_file=py_file.name,
                    server_port=8000
                )
        
        # If no HTTP server found, check for function-based patterns
        env_py = env_dir / "env.py"
        if env_py.exists():
            has_actor, has_funcs = EnvDetector._parse_env_py(env_py)
            if has_actor or has_funcs:
                logger.info("Detected function-based environment (Actor/functions in env.py)")
                return EnvConfig(
                    env_type=EnvType.FUNCTION_BASED,
                    server_file=None,
                    server_port=8000
                )
        
        raise ValueError(f"Cannot detect environment type in {env_path}")
    
    @staticmethod
    def _is_http_server(file_path: Path) -> bool:
        """Check if file is an HTTP server"""
        try:
            code = file_path.read_text()
            return any(fw in code for fw in EnvDetector.WEB_FRAMEWORKS)
        except Exception as e:
            logger.debug(f"Failed to parse {file_path}: {e}")
            return False
    
    @staticmethod
    def _parse_env_py(file_path: Path) -> tuple[bool, bool]:
        """Check env.py for Actor class and callable functions"""
        try:
            code = file_path.read_text()
            tree = ast.parse(code)
            
            has_actor = any(
                isinstance(node, ast.ClassDef) and node.name == "Actor"
                for node in ast.walk(tree)
            )
            
            has_funcs = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not node.name.startswith('_')
                for node in tree.body
            )
            
            return has_actor, has_funcs
        except Exception as e:
            logger.debug(f"Failed to parse {file_path}: {e}")
            return False, False