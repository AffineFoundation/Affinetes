"""Instance pool for managing multiple environment instances"""

import asyncio
import time
from typing import List, Optional, Any

from .load_balancer import LoadBalancer, InstanceInfo
from ..backends.base import AbstractBackend
from ..utils.logger import logger
from ..utils.exceptions import BackendError


class InstancePool:
    """Manages multiple environment instances with load balancing"""
    
    def __init__(
        self,
        instances: List[InstanceInfo],
        load_balance_strategy: str = "random"
    ):
        """
        Initialize instance pool
        
        Args:
            instances: List of InstanceInfo objects
            load_balance_strategy: Load balancing strategy ("random" or "round_robin")
        """
        if not instances:
            raise BackendError("Cannot create InstancePool with empty instances list")
        
        self._instances = instances
        self._load_balancer = LoadBalancer(strategy=load_balance_strategy)
        self._lock = asyncio.Lock()  # For thread-safe instance updates
        
        # Pool metadata
        self.name = f"pool-{len(instances)}-instances"
        
        logger.info(
            f"InstancePool created with {len(instances)} instances, "
            f"strategy: {load_balance_strategy}"
        )
        
        # Log instance details
        for i, inst in enumerate(instances):
            logger.debug(f"  Instance {i}: {inst}")
    
    async def call_method(
        self,
        method_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Call method on a selected instance (load-balanced)
        
        Args:
            method_name: Method name to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Method result from selected instance
        """
        # Select instance using load balancer
        instance = self._load_balancer.select_instance(self._instances)
        
        try:
            logger.debug(
                f"Routing '{method_name}' to instance {instance.host}:{instance.port}"
            )
            
            # Call method on selected backend
            result = await instance.backend.call_method(
                method_name,
                *args,
                **kwargs
            )
            
            # Update statistics
            instance.request_count += 1
            
            return result
            
        except Exception as e:
            logger.error(
                f"Method '{method_name}' failed on instance {instance}: {e}"
            )
            # Mark instance as unhealthy
            async with self._lock:
                instance.healthy = False
                instance.last_check = time.time()
            raise
    
    async def list_methods(self) -> list:
        """
        List methods from any healthy instance
        
        Returns:
            List of available methods
        """
        # Use first healthy instance to get method list
        instance = self._load_balancer.select_instance(self._instances)
        
        try:
            return await instance.backend.list_methods()
        except Exception as e:
            raise BackendError(f"Failed to list methods: {e}")
    
    async def cleanup(self) -> None:
        """Cleanup all instances in the pool"""
        logger.info(f"Cleaning up instance pool ({len(self._instances)} instances)")
        
        # Cleanup all instances concurrently
        cleanup_tasks = [
            inst.backend.cleanup()
            for inst in self._instances
        ]
        
        results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Log any cleanup failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    f"Failed to cleanup instance {self._instances[i]}: {result}"
                )
        
        logger.info("Instance pool cleanup completed")
    
    def is_ready(self) -> bool:
        """
        Check if pool has at least one healthy instance
        
        Returns:
            True if at least one instance is healthy
        """
        return any(inst.healthy for inst in self._instances)
    
    def get_healthy_count(self) -> int:
        """Get number of healthy instances"""
        return sum(1 for inst in self._instances if inst.healthy)
    
    def get_total_count(self) -> int:
        """Get total number of instances"""
        return len(self._instances)
    
    def get_instances(self) -> List[InstanceInfo]:
        """Get list of all instances"""
        return self._instances.copy()
    
    def get_stats(self) -> dict:
        """
        Get pool statistics
        
        Returns:
            Dictionary with pool statistics
        """
        healthy_count = self.get_healthy_count()
        total_requests = sum(inst.request_count for inst in self._instances)
        
        return {
            "total_instances": len(self._instances),
            "healthy_instances": healthy_count,
            "unhealthy_instances": len(self._instances) - healthy_count,
            "total_requests": total_requests,
            "instances": [
                {
                    "host": inst.host,
                    "port": inst.port,
                    "healthy": inst.healthy,
                    "requests": inst.request_count,
                    "last_check": inst.last_check
                }
                for inst in self._instances
            ]
        }
    
    def __repr__(self) -> str:
        """String representation"""
        healthy = self.get_healthy_count()
        total = self.get_total_count()
        return f"<InstancePool {healthy}/{total} healthy instances>"