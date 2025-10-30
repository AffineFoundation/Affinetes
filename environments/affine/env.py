"""Affine Environment Actor"""

import os
import time
import httpx
import openai
import sys

# Add /app to path to import local modules
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from sat import SATTask
from abd import ABDTask
from ded import DEDTask

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
    
    async def _llm_chat(self, prompt, model, base_url, timeout, temperature, current_api_key):
        """Call LLM API with specified API key"""
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
        
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            stream=False
        )
        
        return response.choices[0].message.content.strip()
    
    async def evaluate(
        self,
        task_type="sat",
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        num_samples=1,
        timeout=600,
        temperature=0.7,
        api_key: str = None
    ):
        """
        Run evaluation
        
        Args:
            task_type: Type of task to evaluate (sat, abd, ded)
            model: Model name to use for evaluation
            base_url: Base URL for LLM API
            num_samples: Number of samples to evaluate
            timeout: Timeout for LLM API calls
            temperature: Temperature for LLM generation
            api_key: Override API key for this evaluation. If not provided, uses instance api_key
        """
        # Allow per-call api_key override
        current_api_key = api_key or self.api_key
        # Get task class from registry
        task_cls = self.TASKS.get(task_type)
        if not task_cls:
            raise ValueError(f"Unknown task: {task_type}. Available: {list(self.TASKS.keys())}")
        
        # Initialize task instance (all tasks now use instance methods)
        task_instance = task_cls()
        
        start = time.time()
        details = []
        total_score = 0.0
        
        for i in range(num_samples):
            # Generate challenge (unified async interface)
            challenge = await task_instance.generate()
            
            # Call LLM
            try:
                resp = await self._llm_chat(challenge.prompt, model, base_url, timeout, temperature, current_api_key)
                error = None
            except Exception as e:
                import traceback
                resp = None
                error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            
            # Evaluate (unified async interface)
            score = 0.0
            if resp:
                score = await task_instance.evaluate(resp, challenge)
            
            total_score += score
            details.append({
                "id": i,
                "reward": score,
                "success": score > 0,
                "experiences": {"challenge": challenge.prompt, "llm_response": resp},
                **({} if not error else {"error": error, "error_type": "llm_failure"})
            })
        
        return {
            "task_name": f"affine:{task_type}",
            "total_score": total_score,
            "success_rate": sum(1 for d in details if d["success"]) / num_samples,
            "num_evaluated": num_samples,
            "time_taken": time.time() - start,
            "details": details
        }