"""Load balancing strategies for multi-instance deployment"""

import random
from typing import List, Optional
from dataclasses import dataclass

from ..utils.logger import logger
from ..utils.exceptions import BackendError


@dataclass
class InstanceInfo:
    """Information about a single environment instance"""
    host: str                       # "localhost" or IP address
    port: int                       # HTTP port
    backend: 'AbstractBackend'      # Backend instance
    healthy: bool = True            # Health status
    last_check: float = 0.0         # Last health check timestamp
    request_count: int = 0          # Total requests handled
    
    def __str__(self):
        status = "healthy" if self.healthy else "unhealthy"
        return f"{self.host}:{self.port} ({status})"


class LoadBalancer:
    """Load balancing strategies for instance selection"""
    
    STRATEGY_RANDOM = "random"
    STRATEGY_ROUND_ROBIN = "round_robin"
    
    def __init__(self, strategy: str = STRATEGY_RANDOM):
        """
        Initialize load balancer
        
        Args:
            strategy: Load balancing strategy
                - "random": Random selection among healthy instances
                - "round_robin": Round-robin among healthy instances
        """
        if strategy not in [self.STRATEGY_RANDOM, self.STRATEGY_ROUND_ROBIN]:
            raise ValueError(
                f"Invalid strategy: {strategy}. "
                f"Must be '{self.STRATEGY_RANDOM}' or '{self.STRATEGY_ROUND_ROBIN}'"
            )
        
        self._strategy = strategy
        self._round_robin_index = 0
        logger.debug(f"LoadBalancer initialized with strategy: {strategy}")
    
    def select_instance(self, instances: List[InstanceInfo]) -> InstanceInfo:
        """
        Select a healthy instance based on configured strategy
        
        Args:
            instances: List of available instances
            
        Returns:
            Selected instance
            
        Raises:
            BackendError: If no healthy instances available
        """
        # Filter healthy instances
        healthy = [inst for inst in instances if inst.healthy]
        
        if not healthy:
            raise BackendError(
                "No healthy instances available. "
                "All instances failed health check."
            )
        
        # Select based on strategy
        if self._strategy == self.STRATEGY_RANDOM:
            selected = self._select_random(healthy)
        elif self._strategy == self.STRATEGY_ROUND_ROBIN:
            selected = self._select_round_robin(healthy)
        else:
            # Fallback to random
            selected = self._select_random(healthy)
        
        logger.debug(f"Selected instance: {selected}")
        return selected
    
    def _select_random(self, instances: List[InstanceInfo]) -> InstanceInfo:
        """Randomly select an instance"""
        return random.choice(instances)
    
    def _select_round_robin(self, instances: List[InstanceInfo]) -> InstanceInfo:
        """Select instance using round-robin"""
        selected = instances[self._round_robin_index % len(instances)]
        self._round_robin_index += 1
        return selected
    
    def reset(self):
        """Reset internal state (e.g., round-robin counter)"""
        self._round_robin_index = 0
        logger.debug("LoadBalancer state reset")