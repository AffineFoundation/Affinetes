"""
Affinetes: Container-based Environment Execution Framework

A framework for defining, building, and executing isolated environments
in Docker containers with HTTP-based remote execution.

Basic Usage:
    # Build environment image
    >>> from affinetes import build_image_from_env, load_env
    >>> build_image_from_env("environments/affine", "affine:latest")
    
    # Load and use environment
    >>> env = load_env(image="affine:latest", env_vars={"CHUTES_API_KEY": "xxx"})
    >>> result = env.evaluate(task_type="sat", num_samples=5)
    >>> env.cleanup()
    
    # Context manager (automatic cleanup)
    >>> with load_env(image="affine:latest", env_vars={"CHUTES_API_KEY": "xxx"}) as env:
    ...     result = env.evaluate(task_type="sat", num_samples=5)
"""

from .__version__ import __version__
from .api import (
    build_image_from_env,
    load_env,
    list_active_environments,
    cleanup_all_environments,
    get_environment,
)

__all__ = [
    "__version__",
    "build_image_from_env",
    "load_env",
    "list_active_environments",
    "cleanup_all_environments",
    "get_environment",
]