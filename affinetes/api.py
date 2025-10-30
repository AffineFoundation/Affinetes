"""Public API for affinetes"""

import time
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path

from .backends import LocalBackend, BasilicaBackend
from .infrastructure import ImageBuilder
from .core import EnvironmentWrapper, get_registry, InstancePool, InstanceInfo
from .utils.logger import logger
from .utils.exceptions import ValidationError, BackendError


def build_image_from_env(
    env_path: str,
    image_tag: str,
    nocache: bool = False,
    quiet: bool = False,
    buildargs: Optional[Dict[str, str]] = None,
    push: bool = False,
    registry: Optional[str] = None
) -> str:
    """
    Build Docker image from environment definition and optionally push to registry
    
    Args:
        env_path: Path to environment directory (must contain env.py and Dockerfile)
        image_tag: Image tag (e.g., "affine:latest")
        nocache: Don't use build cache
        quiet: Suppress build output
        buildargs: Docker build arguments (e.g., {"ENV_NAME": "webshop"})
        push: Push image to registry after build (default: False)
        registry: Registry URL (e.g., "docker.io/myuser"). If not specified, uses image_tag as-is
        
    Returns:
        Built image tag (with registry prefix if specified)
        
    Examples:
        >>> # Build only
        >>> build_image_from_env("environments/affine", "affine:latest")
        'affine:latest'
        
        >>> # Build and push to Docker Hub
        >>> build_image_from_env("environments/affine", "affine:latest",
        ...                      push=True, registry="docker.io/myuser")
        'docker.io/myuser/affine:latest'
        
        >>> # Build and push (image_tag already contains registry)
        >>> build_image_from_env("environments/affine", "myregistry.com/affine:latest", push=True)
        'myregistry.com/affine:latest'
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
        
        # Push to registry if requested
        if push:
            logger.info(f"Pushing image to registry...")
            builder.push_image(image_tag=image_tag, registry=registry)
            
            # Return final tag (with registry prefix if applicable)
            if registry:
                final_tag = f"{registry}/{image_tag}"
            else:
                final_tag = image_tag
            
            logger.info(f"Image pushed successfully: {final_tag}")
            return final_tag
        
        return image_tag
        
    except Exception as e:
        logger.error(f"Failed to build image: {e}")
        raise


def load_env(
    image: str,
    mode: str = "docker",
    replicas: int = 1,
    hosts: Optional[List[str]] = None,
    load_balance: str = "random",
    container_name: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    env_type: Optional[str] = None,
    force_recreate: bool = False,
    pull: bool = False,
    **backend_kwargs
) -> EnvironmentWrapper:
    """
    Load and start an environment with multi-instance support
    
    Args:
        image: Docker image name (for docker mode) or environment name (for basilica mode)
        mode: Execution mode - "docker" or "basilica"
        replicas: Number of instances to deploy (default: 1)
        hosts: List of Docker daemon addresses for deployment
               - None or ["localhost"]: Deploy all replicas locally
               - ["ssh://user@host1", "ssh://user@host2"]: Deploy to remote Docker daemons via SSH
               - Mix allowed: ["localhost", "ssh://user@host"]
        load_balance: Load balancing strategy - "random" or "round_robin" (default: "random")
        container_name: Optional container name prefix (local mode only)
        env_vars: Environment variables to pass to container(s)
        env_type: Override environment type detection ("function_based" or "http_based")
        force_recreate: If True, remove and recreate containers even if they exist (default: False)
        pull: If True, pull the image before deployment (default: False)
        **backend_kwargs: Additional backend-specific parameters
        
    Returns:
        EnvironmentWrapper instance
        
    Examples:
        # Single local instance
        >>> env = load_env(image="affine:latest")
        
        # 3 local instances with load balancing
        >>> env = load_env(image="affine:latest", replicas=3)
        
        # 2 remote instances via SSH
        >>> env = load_env(
        ...     image="affine:latest",
        ...     replicas=2,
        ...     hosts=["ssh://user@host1", "ssh://user@host2"]
        ... )
        
        # Mixed: 1 local + 2 remote
        >>> env = load_env(
        ...     image="affine:latest",
        ...     replicas=3,
        ...     hosts=["localhost", "ssh://user@host1", "ssh://user@host2"]
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
                host=hosts[0] if hosts else None,
                container_name=container_name,
                env_vars=env_vars,
                env_type=env_type,
                force_recreate=force_recreate,
                pull=pull,
                **backend_kwargs
            )
        
        # Multi-instance mode
        return _load_multi_instance(
            image=image,
            mode=mode,
            replicas=replicas,
            hosts=hosts,
            load_balance=load_balance,
            container_name=container_name,
            env_vars=env_vars,
            env_type=env_type,
            force_recreate=force_recreate,
            pull=pull,
            **backend_kwargs
        )
        
    except Exception as e:
        logger.error(f"Failed to load environment: {e}")
        raise


def _load_single_instance(
    image: str,
    mode: str,
    host: Optional[str],
    container_name: Optional[str],
    env_vars: Optional[Dict[str, str]],
    env_type: Optional[str],
    force_recreate: bool = False,
    pull: bool = False,
    **backend_kwargs
) -> EnvironmentWrapper:
    """Load a single instance"""
    
    # Create backend based on mode
    if mode == "docker":
        backend = LocalBackend(
            image=image,
            host=host,
            container_name=container_name,
            env_vars=env_vars,
            env_type_override=env_type,
            force_recreate=force_recreate,
            pull=pull,
            **backend_kwargs
        )
    elif mode == "basilica":
        # Basilica mode for pre-deployed remote environments
        if "base_url" not in backend_kwargs:
            raise ValidationError(
                "Basilica mode requires 'base_url' parameter. "
                "Example: base_url='http://xx.xx.xx.xx:8080'"
            )
        backend = BasilicaBackend(
            image=image,
            **backend_kwargs
        )
    else:
        raise ValidationError(
            f"Invalid mode: {mode}. Must be 'docker' or 'basilica'."
        )
    
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
    container_name: Optional[str],
    env_vars: Optional[Dict[str, str]],
    env_type: Optional[str],
    force_recreate: bool = False,
    pull: bool = False,
    **backend_kwargs
) -> EnvironmentWrapper:
    """Load multiple instances with load balancing"""
    
    logger.info(f"Deploying {replicas} instances with {load_balance} load balancing")
    
    # Determine target hosts
    if not hosts:
        hosts = [None] * replicas  # None means localhost
    
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
                    instance_id=i,
                    container_name=container_name,
                    env_vars=env_vars,
                    env_type=env_type,
                    force_recreate=force_recreate,
                    pull=pull,
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
    host: Optional[str],
    instance_id: int,
    container_name: Optional[str],
    env_vars: Optional[Dict[str, str]],
    env_type: Optional[str],
    force_recreate: bool = False,
    pull: bool = False,
    **backend_kwargs
) -> InstanceInfo:
    """Deploy a single instance (async)"""
    
    host_display = host or "localhost"
    logger.debug(f"Deploying instance {instance_id} on {host_display}")
    
    # Docker deployment (supports SSH remote via host parameter)
    if mode == "docker":
        # Generate unique container name (sanitize image name)
        safe_image = image.split('/')[-1].replace(':', '-')
        name_prefix = container_name or safe_image
        unique_name = f"{name_prefix}-{instance_id}"
        
        backend = LocalBackend(
            image=image,
            host=host,
            container_name=unique_name,
            env_vars=env_vars,
            env_type_override=env_type,
            force_recreate=force_recreate,
            pull=pull,
            **backend_kwargs
        )
    else:
        raise ValidationError(f"Mode '{mode}' not supported for multi-instance")
    
    # Create InstanceInfo (use container internal IP as identifier)
    instance_info = InstanceInfo(
        host=host_display,
        port=8000,  # Internal port (not exposed)
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