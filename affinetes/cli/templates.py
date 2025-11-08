"""Environment template definitions for CLI init command"""

# Function-based environment with Actor class
ACTOR_ENV_PY = '''"""Environment implementation with Actor class"""

import os


class Actor:
    """Actor class for structured environments"""
    
    def __init__(self):
        """Initialize actor with environment variables"""
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            raise ValueError("API_KEY environment variable not set")
    
    async def process(self, data: dict) -> dict:
        """
        Process data
        
        Args:
            data: Input data dictionary
            
        Returns:
            Processed result dictionary
        """
        return {
            "status": "success",
            "input": data,
            "message": "Processed by Actor"
        }
    
    async def evaluate(self, task: str, **kwargs) -> dict:
        """
        Evaluate a task
        
        Args:
            task: Task name
            **kwargs: Additional parameters
            
        Returns:
            Evaluation result
        """
        return {
            "task": task,
            "score": 1.0,
            "success": True,
            "kwargs": kwargs
        }
'''

# Function-based environment with module-level functions
BASIC_ENV_PY = '''"""Environment implementation with module-level functions"""

import os


async def process(data: dict) -> dict:
    """
    Process data
    
    Args:
        data: Input data dictionary
        
    Returns:
        Processed result dictionary
    """
    api_key = os.getenv("API_KEY")
    
    return {
        "status": "success",
        "input": data,
        "api_key_set": bool(api_key),
        "message": "Processed successfully"
    }


async def evaluate(task: str, **kwargs) -> dict:
    """
    Evaluate a task
    
    Args:
        task: Task name
        **kwargs: Additional parameters
        
    Returns:
        Evaluation result
    """
    return {
        "task": task,
        "score": 1.0,
        "success": True,
        "kwargs": kwargs
    }
'''

# Function-based Dockerfile (HTTP server auto-injected)
FUNCTION_DOCKERFILE = '''FROM python:3.12-slim

WORKDIR /app

# Copy environment code
COPY . /app/

# Note: HTTP server will be auto-injected by affinetes
'''

# HTTP-based environment with FastAPI
FASTAPI_ENV_PY = '''"""Environment implementation with FastAPI"""

import os
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Custom Environment API")


class ProcessRequest(BaseModel):
    data: dict


class EvaluateRequest(BaseModel):
    task: str
    params: dict = {}


@app.get("/health")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Environment is running"}


@app.post("/process")
async def process(request: ProcessRequest):
    """Process data endpoint"""
    api_key = os.getenv("API_KEY")
    
    return {
        "status": "success",
        "input": request.data,
        "api_key_set": bool(api_key),
        "message": "Processed by FastAPI"
    }


@app.post("/evaluate")
async def evaluate(request: EvaluateRequest):
    """Evaluate task endpoint"""
    return {
        "task": request.task,
        "score": 1.0,
        "success": True,
        "params": request.params
    }
'''

# HTTP-based Dockerfile
FASTAPI_DOCKERFILE = '''FROM python:3.12-slim

WORKDIR /app

# Install FastAPI and Uvicorn
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Copy environment code
COPY . /app/

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "env:app", "--host", "0.0.0.0", "--port", "8000"]
'''