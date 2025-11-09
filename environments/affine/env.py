"""Affine Environment Actor"""

import os
import time
import gc
import httpx
import openai
import sys
import random

# Add /app to path to import local modules
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from sat import SATTask
from abd import ABDTask
from ded import DEDTask
from dataset import R2Dataset

# Global R2Dataset instance - created on module import to trigger background download
_global_dataset = R2Dataset(dataset_name="satpalsr/rl-python")

class Actor:
    """Multi-task evaluation actor"""
    
    # Task registry - map task_type to task class
    TASKS = {
        "sat": SATTask,
        "abd": ABDTask,
        "ded": DEDTask,
    }
    
    def __init__(self, api_key: str = None):
        """
        Initialize Actor with API key
        
        Args:
            api_key: API key for LLM service. If not provided, will use CHUTES_API_KEY env var
        """
        self.api_key = api_key or os.getenv("CHUTES_API_KEY")
    
    async def _llm_chat(self, prompt, model, base_url, timeout, temperature, current_api_key, seed=None):
        """Call LLM API with specified API key and optional seed"""
        # Unset SSL_CERT_FILE to avoid certificate path issues in container
        # Let httpx/certifi use default certificate bundle
        import os
        os.environ.pop('SSL_CERT_FILE', None)
        os.environ.pop('REQUESTS_CA_BUNDLE', None)
        
        client = openai.AsyncOpenAI(
            base_url=base_url.rstrip('/'),
            api_key=current_api_key,
            timeout=httpx.Timeout(timeout),
            max_retries=0
        )

        # Prepare API call parameters
        params = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": False
        }
        
        # Add seed if provided
        if seed is not None:
            params["seed"] = seed

        response = await client.chat.completions.create(**params)
        
        # Handle case where API returns None content
        if not response.choices:
            raise ValueError("LLM API returned empty choices list")
        
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM API returned None content (possible content filtering or API error)")
        
        return content.strip()
    
    async def evaluate(
        self,
        task_type="sat",
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        timeout=600,
        temperature=0.7,
        api_key: str = None,
        seed: int = None
    ):
        """
        Run evaluation on a single task
        
        Args:
            task_type: Type of task to evaluate (sat, abd, ded)
            model: Model name to use for evaluation
            base_url: Base URL for LLM API
            timeout: Timeout for LLM API calls
            temperature: Temperature for LLM generation
            api_key: Override API key for this evaluation. If not provided, uses instance api_key
            seed: Random seed for LLM generation. Used to ensure reproducible results. If not provided, a random seed will be generated.
        """
        # Generate random seed if not provided
        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        # Allow per-call api_key override
        current_api_key = api_key or self.api_key
        # Get task class from registry
        task_cls = self.TASKS.get(task_type)
        if not task_cls:
            raise ValueError(f"Unknown task: {task_type}. Available: {list(self.TASKS.keys())}")
        
        # Initialize task instance, passing global dataset if task supports it
        if task_type in ("abd", "ded"):
            task_instance = task_cls(dataset=_global_dataset)
        else:
            task_instance = task_cls()
        
        start = time.time()
        
        # Generate challenge (unified async interface)
        challenge = await task_instance.generate()
        
        # Call LLM
        try:
            resp = await self._llm_chat(challenge.prompt, model, base_url, timeout, temperature, current_api_key, seed)
            error = None
        except Exception as e:
            import traceback
            resp = None
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        
        # Evaluate (unified async interface)
        score = 0.0
        if resp:
            score = await task_instance.evaluate(resp, challenge)

        conversation = [
            {"role": "user", "content": challenge.prompt},
            {"role": "assistant", "content": resp}
        ]

        result = {
            "task_name": f"affine:{task_type}",
            "score": score,
            "success": score > 0,
            "time_taken": time.time() - start,
            "extra": {
                "conversation": conversation,
                "seed": seed
            }
        }
        
        # Add error info if present
        if error:
            result["error"] = error
            result["error_type"] = "llm_failure"

        # Force garbage collection to free memory immediately
        del task_instance
        gc.collect()

        return result