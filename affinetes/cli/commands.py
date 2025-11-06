"""CLI command implementations"""

import asyncio
import json
from typing import Optional, Dict, Any, List
from tabulate import tabulate
from datetime import datetime
import os

from ..api import load_env, build_image_from_env
from ..infrastructure import ImageBuilder
from ..utils.logger import logger
from .state import StateManager


state_manager = StateManager()


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
        
        # Determine container name
        if name:
            container_name = name
        else:
            # Extract name from image (e.g., bignickeye/affine:v2 -> affine-v2)
            container_name = image.split('/')[-1].replace(':', '-')
        
        logger.info(f"Starting environment: {container_name}")
        if "CHUTES_API_KEY" not in env_vars and os.environ.get("CHUTES_API_KEY"):
            env_vars["CHUTES_API_KEY"] = os.environ.get("CHUTES_API_KEY")

        # Load environment using SDK with container_name
        env = load_env(
            image=image,
            container_name=container_name,
            env_vars=env_vars,
            cleanup=False,
            pull=pull,
            mem_limit=mem_limit
        )
        
        # Get container info
        container_id = env._backend._container.id if hasattr(env._backend, '_container') else None
        
        if not container_id:
            logger.error("Failed to get container ID")
            return
        
        # Get actual container name from Docker
        import docker
        client = docker.from_env()
        container = client.containers.get(container_id)
        actual_name = container.name
        
        # Use the actual container name from Docker
        container_name = actual_name
        
        # Register in state
        state_manager.register_environment(
            name=container_name,
            container_id=container_id,
            image=image or f"built-from-{env_dir}",
            env_vars=env_vars,
            auto_cleanup=False
        )
        
        logger.info(f"✓ Environment started successfully")
        logger.info(f"  Name: {container_name}")
        logger.info(f"  Container ID: {container_id[:12]}")
        
        # Show available methods (using HTTP directly)
        try:
            import aiohttp
            networks = container.attrs['NetworkSettings']['Networks']
            if networks:
                ip = list(networks.values())[0]['IPAddress']
                async with aiohttp.ClientSession() as session:
                    url = f"http://{ip}:8000/methods"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            data = await response.json()
                            methods = data.get('methods', [])
                            if methods:
                                logger.info(f"  Available methods: {', '.join(methods)}")
        except Exception:
            pass
        
        logger.info(f"\nUse 'afs call {container_name} <method>' to interact with the environment")
        logger.info(f"Use 'afs inspect {container_name}' to see available methods")
        logger.info(f"Use 'afs stop {container_name}' to stop the environment")
    
    except Exception as e:
        logger.error(f"Failed to start environment: {e}")
        raise


async def list_environments(show_all: bool, json_output: bool) -> None:
    """List running environments"""
    
    try:
        envs = state_manager.list_environments(include_stopped=show_all)
        
        if not envs:
            logger.info("No environments found")
            return
        
        if json_output:
            # JSON output
            print(json.dumps(envs, indent=2))
        else:
            # Table output
            headers = ["NAME", "CONTAINER ID", "IMAGE", "STATUS", "CREATED"]
            rows = []
            
            for env in envs:
                created_time = datetime.fromisoformat(env['created_at']).strftime('%Y-%m-%d %H:%M:%S')
                rows.append([
                    env['name'],
                    env['container_id'][:12],
                    env['image'][:40] + '...' if len(env['image']) > 40 else env['image'],
                    env['status'],
                    created_time,
                ])
            
            print(tabulate(rows, headers=headers, tablefmt='simple'))
            print(f"\nTotal: {len(envs)} environment(s)")
    
    except Exception as e:
        logger.error(f"Failed to list environments: {e}")
        raise


async def call_method(
    name: str,
    method: str,
    args: Dict[str, Any],
    timeout: Optional[int]
) -> None:
    """Call a method on running environment"""
    
    try:
        # Get environment info
        env_info = state_manager.get_environment(name)
        if not env_info:
            logger.error(f"Environment '{name}' not found")
            logger.info("Use 'afs list' to see running environments")
            return
        
        if env_info['status'] != 'running':
            logger.error(f"Environment '{name}' is not running (status: {env_info['status']})")
            return
        
        logger.info(f"Calling {method}({args}) on {name}...")
        
        # Use docker client directly to call method via HTTP
        import docker
        import aiohttp
        
        client = docker.from_env()
        
        try:
            container = client.containers.get(env_info['container_id'])
            
            # Get container IP
            networks = container.attrs['NetworkSettings']['Networks']
            if not networks:
                logger.error("Container has no network")
                return
            
            ip = list(networks.values())[0]['IPAddress']
            
            # Call method via HTTP
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:8000/call"
                payload = {
                    "method": method,
                    "kwargs": args
                }
                
                timeout_seconds = timeout or 300
                
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Method call failed: {error_text}")
                        return
                    
                    result = await response.json()
        
        except docker.errors.NotFound:
            logger.error(f"Container not found (may have been removed)")
            state_manager.update_status(name, 'stopped')
            return
        
        # Display result
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


async def inspect_environment(name: str) -> None:
    """Show environment details and available methods"""
    
    try:
        # Get environment info
        env_info = state_manager.get_environment(name)
        if not env_info:
            logger.error(f"Environment '{name}' not found")
            logger.info("Use 'afs list' to see running environments")
            return
        
        # Display basic info
        print(f"\n{'='*60}")
        print(f"Environment: {env_info['name']}")
        print(f"{'='*60}")
        print(f"Container ID:  {env_info['container_id']}")
        print(f"Image:         {env_info['image']}")
        print(f"Status:        {env_info['status']}")
        print(f"Created:       {env_info['created_at']}")
        print(f"Auto cleanup:  {'enabled' if env_info['auto_cleanup'] else 'disabled'}")
        
        # Display environment variables (masked)
        if env_info.get('env_vars'):
            print(f"\nEnvironment Variables:")
            for key, value in env_info['env_vars'].items():
                print(f"  {key} = {value}")
        
        # Try to get available methods using env.list_methods()
        if env_info['status'] == 'running':
            try:
                from ..api import get_environment
                
                # Try to get the environment from the global registry
                env = get_environment(name)
                
                if not env or not env.is_ready():
                    # Environment not in registry, temporarily reconnect to existing container
                    logger.debug(f"Reconnecting to existing container '{name}'")
                    env = load_env(
                        image=env_info['image'],
                        container_name=name,
                        env_vars=env_info.get('env_vars', {}),
                        cleanup=False,
                        pull=False,
                        force_recreate=False
                    )
                
                # Use the existing list_methods functionality
                await env.list_methods(print_info=True)
                
                print(f"\nUsage:")
                print(f"  afs call {name} <method> --arg key=value")
            except Exception as e:
                logger.warning(f"Could not retrieve methods: {e}")
        
        print(f"{'='*60}\n")
    
    except Exception as e:
        logger.error(f"Failed to inspect environment: {e}")
        raise


async def stop_environment(names: List[str]) -> None:
    """Stop running environment(s)"""
    
    for name in names:
        try:
            env_info = state_manager.get_environment(name)
            if not env_info:
                logger.warning(f"Environment '{name}' not found")
                continue
            
            if env_info['status'] != 'running':
                logger.info(f"Environment '{name}' is already stopped")
                state_manager.unregister_environment(name)
                continue
            
            logger.info(f"Stopping {name}...")
            
            # Use docker client directly to stop container
            import docker
            client = docker.from_env()
            
            try:
                container = client.containers.get(env_info['container_id'])
                container.stop(timeout=10)
                container.remove()
            except docker.errors.NotFound:
                logger.warning(f"Container already removed")
            except Exception as e:
                logger.error(f"Error stopping container: {e}")
                raise
            
            # Update state
            state_manager.unregister_environment(name)
            
            logger.info(f"✓ Environment '{name}' stopped successfully")
        
        except Exception as e:
            logger.error(f"Failed to stop '{name}': {e}")


async def show_logs(name: str, tail: int, follow: bool) -> None:
    """View container logs"""
    
    try:
        env_info = state_manager.get_environment(name)
        if not env_info:
            logger.error(f"Environment '{name}' not found")
            logger.info("Use 'afs list' to see running environments")
            return
        
        # Use docker client directly
        import docker
        client = docker.from_env()
        
        try:
            container = client.containers.get(env_info['container_id'])
            
            if follow:
                logger.info(f"Following logs for {name} (Ctrl+C to stop)...")
                for line in container.logs(stream=True, follow=True, tail=tail):
                    print(line.decode('utf-8'), end='')
            else:
                logs = container.logs(tail=tail).decode('utf-8')
                print(logs)
        
        except docker.errors.NotFound:
            logger.error(f"Container not found (may have been removed)")
            state_manager.update_status(name, 'stopped')
    
    except KeyboardInterrupt:
        logger.info("\nStopped following logs")
    except Exception as e:
        logger.error(f"Failed to show logs: {e}")
        raise