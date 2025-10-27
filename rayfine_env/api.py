"""Public API for rayfine-env"""

import time
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path

from .backends import LocalBackend, RemoteBackend
from .infrastructure import ImageBuilder
from .core import EnvironmentWrapper, get_registry, InstancePool, InstanceInfo
from .utils.logger import logger
from .utils.exceptions import ValidationError, BackendError


def build_image_from_env(
    env_path: str,
    image_tag: str,
    nocache: bool = False,
    quiet: bool = False,
    buildargs: Optional[Dict[str, str]] = None
) -> str:
    """
    Build Docker image from environment definition
    
    Args:
        env_path: Path to environment directory (must contain env.py and Dockerfile)
        image_tag: Image tag (e.g., "affine:latest")
        nocache: Don't use build cache
        quiet: Suppress build output
        buildargs: Docker build arguments (e.g., {"ENV_NAME": "webshop"})
        
    Returns:
        Built image ID
        
    Example:
        >>> build_image_from_env("environments/affine", "affine:latest")
        'sha256:abc123...'
    """
    try:
        logger.info(f"Building image '{image_tag}' from '{env_path}'")
        
        builder = ImageBuilder()
        image_id = builder.build_from_env(
            env_path=env_path,
            image_tag=image_tag,
            nocache=nocache,
            quiet=quiet,
            buildargs=buildargs
        )
        
        logger.info(f"Image '{image_tag}' built successfully")
        return image_id
        
    except Exception as e:
        logger.error(f"Failed to build image: {e}")
        raise


def load_env(
    image: str,
    mode: str = "local",
    replicas: int = 1,
    hosts: Optional[List[str]] = None,
    load_balance: str = "random",
    base_port: int = 8000,
    container_name: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    env_type: Optional[str] = None,
    force_recreate: bool = False,
    **backend_kwargs
) -> EnvironmentWrapper:
    """
    Load and start an environment with multi-instance support
    
    Args:
        image: Docker image name (for local mode) or environment ID (for remote mode)
        mode: Execution mode - "local" or "remote"
        replicas: Number of instances to deploy (default: 1)
        hosts: List of target hosts for deployment
               - None or ["localhost"]: Deploy all replicas locally
               - ["192.168.1.10", "192.168.1.11"]: Deploy to remote hosts via SSH
               - Mix allowed: ["localhost", "192.168.1.10"]
        load_balance: Load balancing strategy - "random" or "round_robin" (default: "random")
        base_port: Starting HTTP port for instances (increments for each replica)
        container_name: Optional container name prefix (local mode only)
        env_vars: Environment variables to pass to container(s)
        env_type: Override environment type detection ("function_based" or "http_based")
        force_recreate: If True, remove and recreate containers even if they exist (default: False)
        **backend_kwargs: Additional backend-specific parameters
        
    Returns:
        EnvironmentWrapper instance
        
    Examples:
        # Single instance (backward compatible)
        >>> env = load_env(image="affine:latest")
        
        # 3 local instances with load balancing
        >>> env = load_env(image="affine:latest", replicas=3)
        
        # 2 remote instances via SSH (Phase 3)
        >>> env = load_env(
        ...     image="affine:latest",
        ...     replicas=2,
        ...     hosts=["192.168.1.10", "192.168.1.11"]
        ... )
        
        # Mixed: 1 local + 2 remote (Phase 3)
        >>> env = load_env(
        ...     image="affine:latest",
        ...     replicas=3,
        ...     hosts=["localhost", "192.168.1.10", "192.168.1.11"]
        ... )
    """
    try:
        logger.debug(f"Loading '{image}' in {mode} mode (replicas={replicas})")
        
        # Validate parameters
        if replicas < 1:
            raise ValidationError("replicas must be >= 1")
        
        if hosts and len(hosts) < replicas:
            raise ValidationError(
                f"Not enough hosts ({len(hosts)}) for replicas ({replicas}). "
                f"Either provide enough hosts or set hosts=None for local deployment."
            )
        
        # Single instance mode (backward compatible)
        if replicas == 1:
            return _load_single_instance(
                image=image,
                mode=mode,
                host=hosts[0] if hosts else "localhost",
                port=base_port,
                container_name=container_name,
                env_vars=env_vars,
                env_type=env_type,
                force_recreate=force_recreate,
                **backend_kwargs
            )
        
        # Multi-instance mode
        return _load_multi_instance(
            image=image,
            mode=mode,
            replicas=replicas,
            hosts=hosts,
            load_balance=load_balance,
            base_port=base_port,
            container_name=container_name,
            env_vars=env_vars,
            env_type=env_type,
            force_recreate=force_recreate,
            **backend_kwargs
        )
        
    except Exception as e:
        logger.error(f"Failed to load environment: {e}")
        raise


def _load_single_instance(
    image: str,
    mode: str,
    host: str,
    port: int,
    container_name: Optional[str],
    env_vars: Optional[Dict[str, str]],
    env_type: Optional[str],
    force_recreate: bool = False,
    **backend_kwargs
) -> EnvironmentWrapper:
    """Load a single instance (backward compatible path)"""
    
    # Remote SSH deployment (Phase 3 - not yet implemented)
    if host != "localhost":
        raise NotImplementedError(
            "Remote SSH deployment not yet implemented. "
            "Use hosts=['localhost'] or hosts=None for local deployment."
        )
    
    # Create local backend
    if mode == "local":
        backend = LocalBackend(
            image=image,
            container_name=container_name,
            http_port=port,
            env_vars=env_vars,
            env_type_override=env_type,
            force_recreate=force_recreate,
            **backend_kwargs
        )
    elif mode == "remote":
        backend = RemoteBackend(
            environment_id=image,
            **backend_kwargs
        )
    else:
        raise ValidationError(f"Invalid mode: {mode}. Must be 'local' or 'remote'")
    
    # Create wrapper
    wrapper = EnvironmentWrapper(backend=backend)
    
    # Register in global registry
    registry = get_registry()
    registry.register(backend.name, wrapper)
    
    logger.debug(f"Single instance '{backend.name}' loaded successfully")
    return wrapper


def _load_multi_instance(
    image: str,
    mode: str,
    replicas: int,
    hosts: Optional[List[str]],
    load_balance: str,
    base_port: int,
    container_name: Optional[str],
    env_vars: Optional[Dict[str, str]],
    env_type: Optional[str],
    force_recreate: bool = False,
    **backend_kwargs
) -> EnvironmentWrapper:
    """Load multiple instances with load balancing"""
    
    logger.info(f"Deploying {replicas} instances with {load_balance} load balancing")
    
    # Determine target hosts
    if not hosts:
        hosts = ["localhost"] * replicas
    
    # Validate remote hosts (Phase 3)
    for host in hosts:
        if host != "localhost":
            raise NotImplementedError(
                f"Remote SSH deployment to '{host}' not yet implemented. "
                "Currently only localhost deployment is supported."
            )
    
    # Create instances concurrently
    instances = []
    
    try:
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Deploy all instances concurrently
        async def deploy_all():
            tasks = [
                _deploy_instance(
                    image=image,
                    mode=mode,
                    host=hosts[i],
                    port=base_port + i,
                    instance_id=i,
                    container_name=container_name,
                    env_vars=env_vars,
                    env_type=env_type,
                    force_recreate=force_recreate,
                    **backend_kwargs
                )
                for i in range(replicas)
            ]
            return await asyncio.gather(*tasks)
        
        instances = loop.run_until_complete(deploy_all())
        
        logger.info(f"Successfully deployed {len(instances)} instances")
        
        # Create instance pool
        pool = InstancePool(
            instances=instances,
            load_balance_strategy=load_balance
        )
        
        # Create wrapper
        wrapper = EnvironmentWrapper(backend=pool)
        
        # Register in global registry
        registry = get_registry()
        registry.register(pool.name, wrapper)
        
        logger.debug(f"Multi-instance pool '{pool.name}' loaded successfully")
        return wrapper
        
    except Exception as e:
        # Cleanup any successfully deployed instances
        logger.error(f"Failed to deploy instances: {e}")
        
        if instances:
            logger.info("Cleaning up partially deployed instances")
            try:
                async def cleanup_all():
                    tasks = [inst.backend.cleanup() for inst in instances]
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                loop.run_until_complete(cleanup_all())
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup: {cleanup_error}")
        
        raise BackendError(f"Multi-instance deployment failed: {e}")


async def _deploy_instance(
    image: str,
    mode: str,
    host: str,
    port: int,
    instance_id: int,
    container_name: Optional[str],
    env_vars: Optional[Dict[str, str]],
    env_type: Optional[str],
    force_recreate: bool = False,
    **backend_kwargs
) -> InstanceInfo:
    """Deploy a single instance (async)"""
    
    logger.debug(f"Deploying instance {instance_id} on {host}:{port}")
    
    # Remote deployment (Phase 3)
    if host != "localhost":
        raise NotImplementedError("Remote SSH deployment not yet implemented")
    
    # Local deployment
    if mode == "local":
        # Generate unique container name
        name_prefix = container_name or image.replace(":", "-")
        unique_name = f"{name_prefix}-{instance_id}"
        
        backend = LocalBackend(
            image=image,
            container_name=unique_name,
            http_port=port,
            env_vars=env_vars,
            env_type_override=env_type,
            force_recreate=force_recreate,
            **backend_kwargs
        )
    else:
        raise ValidationError(f"Mode '{mode}' not supported for multi-instance")
    
    # Create InstanceInfo
    instance_info = InstanceInfo(
        host=host,
        port=port,
        backend=backend,
        healthy=True,
        last_check=time.time()
    )
    
    logger.debug(f"Instance {instance_id} deployed: {instance_info}")
    return instance_info


def list_active_environments() -> list:
    """
    List all currently active environments
    
    Returns:
        List of environment IDs
        
    Example:
        >>> list_active_environments()
        ['affine-latest_1234567890', 'custom-v1_1234567891']
    """
    registry = get_registry()
    return registry.list_all()


def cleanup_all_environments() -> None:
    """
    Clean up all active environments
    
    Stops all containers and frees resources.
    Automatically called on program exit.
    
    Example:
        >>> cleanup_all_environments()
    """
    logger.info("Cleaning up all environments")
    registry = get_registry()
    registry.cleanup_all()


def get_environment(env_id: str) -> Optional[EnvironmentWrapper]:
    """
    Get an environment by ID
    
    Args:
        env_id: Environment identifier
        
    Returns:
        EnvironmentWrapper instance or None if not found
        
    Example:
        >>> env = get_environment('affine-latest_1234567890')
    """
    registry = get_registry()
    return registry.get(env_id)