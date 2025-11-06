"""State management for CLI - tracks running environments"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime
from threading import Lock


class StateManager:
    """
    Manages persistent state for CLI
    
    Tracks running environments in a JSON file to enable
    cross-process container management.
    """
    
    def __init__(self, state_file: Optional[str] = None):
        """
        Initialize state manager
        
        Args:
            state_file: Path to state file (default: ~/.affinetes/state.json)
        """
        if state_file:
            self.state_file = Path(state_file)
        else:
            # Default location: ~/.affinetes/state.json
            self.state_file = Path.home() / ".affinetes" / "state.json"
        
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        
        # Initialize state file if not exists
        if not self.state_file.exists():
            self._save_state({"environments": {}})
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from file"""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"environments": {}}
    
    def _save_state(self, state: Dict[str, Any]) -> None:
        """Save state to file"""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def register_environment(
        self,
        name: str,
        container_id: str,
        image: str,
        env_vars: Optional[Dict[str, str]] = None,
        auto_cleanup: bool = True,
        **metadata
    ) -> None:
        """
        Register a running environment
        
        Args:
            name: Container name
            container_id: Docker container ID
            image: Docker image
            env_vars: Environment variables (sensitive values masked)
            auto_cleanup: Whether to auto cleanup on exit
            **metadata: Additional metadata
        """
        with self._lock:
            state = self._load_state()
            
            # Mask sensitive environment variables
            masked_env_vars = {}
            if env_vars:
                for key, value in env_vars.items():
                    if any(secret in key.upper() for secret in ['KEY', 'SECRET', 'PASSWORD', 'TOKEN']):
                        masked_env_vars[key] = '***'
                    else:
                        masked_env_vars[key] = value
            
            state["environments"][name] = {
                "name": name,
                "container_id": container_id,
                "image": image,
                "created_at": datetime.utcnow().isoformat(),
                "env_vars": masked_env_vars,
                "auto_cleanup": auto_cleanup,
                "status": "running",
                **metadata
            }
            
            self._save_state(state)
    
    def unregister_environment(self, name: str) -> None:
        """
        Unregister an environment
        
        Args:
            name: Container name
        """
        with self._lock:
            state = self._load_state()
            
            if name in state["environments"]:
                del state["environments"][name]
                self._save_state(state)
    
    def get_environment(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get environment info by name
        
        Args:
            name: Container name
            
        Returns:
            Environment info dict or None
        """
        state = self._load_state()
        return state["environments"].get(name)
    
    def list_environments(self, include_stopped: bool = False) -> List[Dict[str, Any]]:
        """
        List all registered environments
        
        Args:
            include_stopped: If True, include stopped containers
        
        Returns:
            List of environment info dicts
        """
        state = self._load_state()
        envs = list(state["environments"].values())
        
        if include_stopped:
            return envs
        else:
            # Only return running containers
            return [env for env in envs if env.get('status') == 'running']
    
    def update_status(self, name: str, status: str) -> None:
        """
        Update environment status
        
        Args:
            name: Container name
            status: New status (running, stopped, error)
        """
        with self._lock:
            state = self._load_state()
            
            if name in state["environments"]:
                state["environments"][name]["status"] = status
                state["environments"][name]["updated_at"] = datetime.utcnow().isoformat()
                self._save_state(state)
    
    def clear_all(self) -> None:
        """Clear all registered environments"""
        with self._lock:
            self._save_state({"environments": {}})


# Global state manager instance
_state_manager = None


def get_state_manager() -> StateManager:
    """Get global state manager instance"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager