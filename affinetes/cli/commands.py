"""CLI command implementations"""

import asyncio
import json
import os
from typing import Optional, Dict, Any

from ..api import load_env, build_image_from_env, get_environment
from ..utils.logger import logger


async def run_environment(
    image: Optional[str],
    env_dir: Optional[str],
    tag: Optional[str],
    name: Optional[str],
    env_vars: Dict[str, str],
    pull: bool,
    mem_limit: Optional[str],
    no_cache: bool
) -> None:
    """Start an environment container"""
    
    try:
        # Build image from directory if env_dir is provided
        if env_dir:
            if not tag:
                # Auto-generate tag from directory name
                dir_name = env_dir.rstrip('/').split('/')[-1]
                tag = f"{dir_name}:latest"
            
            logger.info(f"Building image '{tag}' from '{env_dir}'")
            
            # Build image
            image = build_image_from_env(
                env_path=env_dir,
                image_tag=tag,
                nocache=no_cache,
                quiet=False
            )
            
            logger.info(f"Image '{image}' built successfully")
        
        # Validate image parameter
        if not image:
            logger.error("Either image or env_dir must be specified")
            return
        
        if "CHUTES_API_KEY" not in env_vars and os.environ.get("CHUTES_API_KEY"):
            env_vars["CHUTES_API_KEY"] = os.environ.get("CHUTES_API_KEY")

        # Load environment using SDK
        env = load_env(
            image=image,
            container_name=name,
            env_vars=env_vars,
            cleanup=False,
            pull=pull,
            mem_limit=mem_limit
        )
        
        logger.info(f"✓ Environment started: {env.name}")
        
        # Show available methods immediately
        await env.list_methods(print_info=True)
        
        print(f"\nUsage:")
        print(f"  afs call {env.name} <method> --arg key=value")
    
    except Exception as e:
        logger.error(f"Failed to start environment: {e}")
        raise


async def call_method(
    name: str,
    method: str,
    args: Dict[str, Any],
    timeout: Optional[int] = 300
) -> None:
    """Call a method on running environment"""
    
    try:
        logger.info(f"Calling {method}({args}) on {name}...")
        
        # Try to get from registry first
        env = get_environment(name)
        
        if not env or not env.is_ready():
            # Not in registry, try to connect to existing container
            logger.debug(f"Environment '{name}' not in registry, connecting to container...")
            try:
                env = load_env(
                    container_name=name,
                    cleanup=False,
                    connect_only=True
                )
                logger.debug(f"Successfully connected to container '{name}'")
            except Exception as e:
                logger.error(
                    f"Failed to connect to container '{name}': {e}\n"
                    f"Please ensure the container is running with: docker ps"
                )
                return
        
        # Call method using SDK's dynamic dispatch
        method_func = getattr(env, method)
        result = await method_func(_timeout=timeout, **args)
        
        logger.info("✓ Method completed successfully")
        
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)
    
    except asyncio.TimeoutError:
        logger.error(f"Method call timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Failed to call method: {e}")
        raise