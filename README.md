# Affine-Kubernetes-Env

Container-based environment execution framework with secure HTTP communication and multi-instance deployment support.

Define environments once, execute anywhere with Docker containers accessed via internal networking.

## Features
- **Two Environment Types**: 
  - Function-based (auto-injected HTTP server)
  - HTTP-based (existing FastAPI servers)
- **Simple Environment Definition**: Only requires `env.py` file
- **Container Isolation**: All environments run in isolated Docker containers
- **Secure Communication**: Internal network access (no exposed ports)
- **SSH Remote Deployment**: Deploy to remote Docker daemons via SSH protocol
- **Dynamic Method Dispatch**: Automatic method exposure via `__getattr__`
- **Multi-Instance Support**: Deploy multiple replicas with load balancing
- **Container Reuse**: Reuse existing containers to avoid conflicts
- **Backend Abstraction**: Local (Docker+HTTP) and Remote modes
- **Zero Burden**: Environment developers only write business logic

## Quick Start

### 1. Define Environment

Create an environment directory with `env.py`:

```python
# environments/affine/env.py
import os

class Actor:
    """Actor class for structured environments"""
    
    def __init__(self):
        self.api_key = os.getenv("CHUTES_API_KEY")
        if not self.api_key:
            raise ValueError("CHUTES_API_KEY not set")
    
    async def evaluate(self, task_type="sat", num_samples=1, **kwargs):
        # Your implementation
        return {
            "task_name": task_type, 
            "total_score": 1.0,
            "samples": num_samples
        }

# Or define module-level functions (simpler approach)
async def evaluate(task_type="sat", num_samples=1, **kwargs):
    api_key = os.getenv("CHUTES_API_KEY")
    # Your implementation
    return {"task_name": task_type, "total_score": 1.0}
```

Optional `Dockerfile` (base image for dependencies):

```dockerfile
# environments/affine/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
```

### 2. Build Image

```python
import rayfine_env as rf_env

# Build Docker image from environment directory
image_id = rf_env.build_image_from_env(
    env_path="environments/affine",
    image_tag="affine:latest"
)
# HTTP server is automatically injected for function-based environments
```

### 3. Load and Execute

```python
import rayfine_env as rf_env

# Load environment (starts container with env vars)
env = rf_env.load_env(
    image="affine:latest",
    mode="docker",
    env_vars={"CHUTES_API_KEY": "your-api-key"}
)

# Execute methods dynamically
result = await env.evaluate(task_type="sat", num_samples=5)

# Cleanup
await env.cleanup()
```

### 4. Async Context Manager (Auto-cleanup)

```python
async with rf_env.load_env(
    image="affine:latest",
    env_vars={"CHUTES_API_KEY": "xxx"}
) as env:
    result = await env.evaluate(task_type="sat", num_samples=5)
# Container automatically cleaned up
```

## Installation

```bash
# Install from source
pip install -e .

# Or install with dev dependencies
pip install -e .[dev]
```

**Requirements:**
- Python 3.8+
- Docker daemon running
- For remote deployment: SSH access to remote Docker hosts

## API Reference

### `build_image_from_env()`

Build Docker image from environment directory.

```python
rf_env.build_image_from_env(
    env_path: str,                          # Path to environment directory
    image_tag: str,                         # Image tag (e.g., "affine:latest")
    nocache: bool = False,                  # Don't use build cache
    quiet: bool = False,                    # Suppress build output
    buildargs: Dict[str, str] = None        # Docker build arguments
) -> str  # Returns image tag
```

**Requirements:**
- `env_path` must contain `env.py` file
- Optional: `Dockerfile`, `requirements.txt`, other Python files

**Behavior:**
- Detects environment type (function-based or http-based)
- For function-based: Builds base image, then injects HTTP server (two-stage build)
- For http-based: Uses existing Dockerfile as-is

### `load_env()`

Load environment from pre-built Docker image.

```python
rf_env.load_env(
    image: str,                             # Docker image name
    mode: str = "docker",                   # "docker" or "rayfine"
    replicas: int = 1,                      # Number of instances
    hosts: List[str] = None,                # Docker daemon addresses
    load_balance: str = "random",           # "random" or "round_robin"
    container_name: str = None,             # Optional container name prefix
    env_vars: Dict[str, str] = None,        # Environment variables
    env_type: str = None,                   # Override type detection
    force_recreate: bool = False,           # Force container recreation
    pull: bool = False,                     # Pull image before deployment
    **kwargs                                # Additional backend options
) -> EnvironmentWrapper
```

**Important:** Environment variables should be passed via `env_vars` parameter.

**Multi-Instance Deployment:**

```python
# Deploy 3 local instances with load balancing
env = rf_env.load_env(
    image="affine:latest",
    replicas=3,
    load_balance="random"
)

# Deploy to remote Docker daemons via SSH
env = rf_env.load_env(
    image="affine:latest",
    replicas=2,
    hosts=["ssh://user@host1", "ssh://user@host2"]
)

# Mixed deployment (1 local + 2 remote)
env = rf_env.load_env(
    image="affine:latest",
    replicas=3,
    hosts=["localhost", "ssh://user@host1", "ssh://user@host2"]
)
```

### EnvironmentWrapper Methods

```python
await env.cleanup()                 # Stop container(s) and cleanup
await env.list_methods()            # List available methods
env.is_ready()                      # Check if ready for execution
await env.<method_name>(**kwargs)   # Call any method from env.py
env.get_stats()                     # Get pool statistics (multi-instance)
```

**Call-Level Timeout:**

```python
# Set timeout for specific method call
result = await env.evaluate(
    task_type="sat",
    _timeout=90  # Timeout after 90 seconds
)
```

### Utility Functions

```python
rf_env.list_active_environments()      # List all active environment IDs
rf_env.cleanup_all_environments()      # Cleanup all environments (auto on exit)
rf_env.get_environment(env_id)         # Get environment by ID
```

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      User Application                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  import rayfine_env as rf_env                          │ │
│  │  env = rf_env.load_env("affine:latest", replicas=3)    │ │
│  │  result = await env.evaluate(...)                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Rayfine-Env Framework                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  API Layer   │  │ Core Layer   │  │  Backend     │      │
│  │  - build_*   │→ │ - Wrapper    │→ │  - Local     │      │
│  │  - load_env  │  │ - Registry   │  │  - Pool      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                           │                   │              │
│  ┌──────────────┐        │                   │              │
│  │Infrastructure│◄───────┘                   │              │
│  │- ImageBuilder│                            │              │
│  │- EnvDetector │                            │              │
│  │- HTTPExecutor│◄───────────────────────────┘              │
│  └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ Docker Internal Network
┌─────────────────────────────────────────────────────────────┐
│                   Docker Container(s)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         HTTP Server (Uvicorn) - 172.17.0.x:8000        │ │
│  │  - GET  /health                                        │ │
│  │  - GET  /methods                                       │ │
│  │  - POST /call  {"method": "evaluate", "args": [...]}   │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              User's env.py                             │ │
│  │  class Actor:                                          │ │
│  │      def __init__(self): ...                           │ │
│  │      async def evaluate(self, ...): ...                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Security Features

**No Port Exposure**: Containers are accessed via Docker's internal network (e.g., `172.17.0.2:8000`) instead of exposing ports to the host machine. This prevents unauthorized external access.

**SSH Remote Access**: Remote Docker daemons are accessed via SSH protocol (`ssh://user@host`) using public key authentication, providing secure encrypted communication.

## Usage Examples

### Basic Single Instance

```python
import rayfine_env as rf_env
import asyncio

async def main():
    # Build image
    image = rf_env.build_image_from_env(
        env_path="environments/affine",
        image_tag="affine:latest"
    )
    
    # Load environment
    env = rf_env.load_env(
        image=image,
        env_vars={"CHUTES_API_KEY": "your-key"}
    )
    
    # Execute method
    result = await env.evaluate(task_type="sat", num_samples=5)
    print(f"Score: {result['total_score']}")
    
    # Cleanup
    await env.cleanup()

asyncio.run(main())
```

### Multi-Instance with Load Balancing

```python
import rayfine_env as rf_env
import asyncio

async def main():
    # Deploy 3 local instances
    env = rf_env.load_env(
        image="affine:latest",
        replicas=3,
        load_balance="round_robin",
        env_vars={"CHUTES_API_KEY": "your-key"}
    )
    
    # Check pool statistics
    stats = env.get_stats()
    print(f"Total instances: {stats['total_instances']}")
    print(f"Healthy instances: {stats['healthy_instances']}")
    
    # Execute concurrent tasks (automatically load balanced)
    tasks = [
        env.evaluate(task_type="abd", num_samples=1)
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)
    
    # Check load distribution
    stats = env.get_stats()
    for inst in stats['instances']:
        print(f"{inst['host']}: {inst['requests']} requests")
    
    await env.cleanup()

asyncio.run(main())
```

### SSH Remote Deployment

```python
import rayfine_env as rf_env
import asyncio

async def main():
    # Deploy to remote Docker daemons via SSH
    env = rf_env.load_env(
        image="affine:latest",
        replicas=2,
        hosts=[
            "ssh://user@192.168.1.10",
            "ssh://user@192.168.1.11"
        ],
        env_vars={"CHUTES_API_KEY": "your-key"}
    )
    
    # Execute on remote instances
    result = await env.evaluate(task_type="sat", num_samples=5)
    
    await env.cleanup()

asyncio.run(main())
```

**SSH Setup:**

```bash
# Generate SSH key (if not exists)
ssh-keygen -t rsa -b 4096

# Copy public key to remote host
ssh-copy-id user@remote-host

# Test connection
ssh user@remote-host docker ps
```

### Concurrent Multi-Environment Execution

```python
import rayfine_env as rf_env
import asyncio

async def main():
    # Deploy multiple environments
    env1 = rf_env.load_env(
        image="affine:latest",
        replicas=3,
        env_vars={"API_KEY": "key1"}
    )
    
    env2 = rf_env.load_env(
        image="agentgym:webshop",
        replicas=2,
        env_vars={"API_KEY": "key2"}
    )
    
    # Execute tasks concurrently across environments
    tasks = []
    for i in range(5):
        tasks.append(env1.evaluate(task_type="abd", num_samples=1))
        tasks.append(env2.evaluate(ids=[0], max_round=10))
    
    results = await asyncio.gather(*tasks)
    
    # Cleanup
    await env1.cleanup()
    await env2.cleanup()

asyncio.run(main())
```

### Container Reuse

```python
# First run: creates container
env1 = rf_env.load_env(
    image="affine:latest",
    container_name="my-affine"
)
await env1.cleanup()

# Second run: reuses existing container (if still exists)
env2 = rf_env.load_env(
    image="affine:latest",
    container_name="my-affine"
)

# Force recreation
env3 = rf_env.load_env(
    image="affine:latest",
    container_name="my-affine",
    force_recreate=True  # Removes and recreates container
)
```

### Image Pull Before Deployment

```python
# Pull latest image from registry before deployment
env = rf_env.load_env(
    image="affine:latest",
    pull=True  # Ensures using latest version
)

# Useful for:
# - Remote deployments (ensure image exists on remote host)
# - Production updates (pull latest tag)
# - Shared registries (sync image versions)
```

## Environment Types

### Function-Based (Recommended)

**Definition:**
```python
# env.py
class Actor:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
    
    async def evaluate(self, **kwargs):
        return {"result": "success"}
```

**Dockerfile:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app/
# No CMD needed - HTTP server auto-injected
```

**Characteristics:**
- Framework auto-injects HTTP server
- Zero HTTP code required
- Lazy Actor initialization (env vars available at runtime)

### HTTP-Based (Advanced)

**Definition:**
```python
# env.py
from fastapi import FastAPI

app = FastAPI()

@app.post("/evaluate")
async def evaluate(request: EvalRequest):
    return {"result": "success"}
```

**Dockerfile:**
```dockerfile
FROM python:3.9
WORKDIR /app
COPY . /app/
RUN pip install fastapi uvicorn
CMD ["uvicorn", "env:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Characteristics:**
- Full control over HTTP server
- Can use existing FastAPI applications
- Suitable for complex services

## Advanced Features

### Call-Level Timeout

Control timeout for individual method calls:

```python
# Set strict timeout for expensive operations
result = await env.evaluate(
    task_type="sat",
    num_samples=100,
    _timeout=300  # Timeout after 5 minutes
)
```

### Load Balancing Strategies

```python
# Random selection (default, better for uneven workloads)
env = rf_env.load_env(
    image="affine:latest",
    replicas=3,
    load_balance="random"
)

# Round-robin (even distribution)
env = rf_env.load_env(
    image="affine:latest",
    replicas=3,
    load_balance="round_robin"
)
```

### Pool Statistics

```python
stats = env.get_stats()

# Available fields:
# - total_instances: Total number of instances
# - healthy_instances: Number of healthy instances
# - total_requests: Total requests processed
# - instances: List of instance details
#   - host: Instance host
#   - port: Instance port
#   - healthy: Health status
#   - requests: Number of requests handled

for inst in stats['instances']:
    pct = inst['requests'] / stats['total_requests'] * 100
    print(f"{inst['host']}: {pct:.1f}%")
```

## Key Design Decisions

### Why HTTP over Ray?

| Aspect | Ray | HTTP |
|--------|-----|------|
| Python version | Must match exactly | Any version |
| Serialization | Ray-specific | Language-agnostic JSON |
| Complexity | Cluster management | Simple REST API |
| Dependencies | Ray SDK required | Standard httpx |
| Debugging | Difficult | Standard HTTP logs |

### Why Internal Network?

- **Security**: No exposed ports prevents unauthorized access
- **Performance**: Direct container-to-container communication
- **Simplicity**: No port management or conflicts
- **Encryption**: SSH tunnel for remote access

### Why Two-Stage Build?

- **Clean separation**: Base image (dependencies) + Server layer (framework)
- **Zero burden**: Environment developers don't write HTTP code
- **Maintainability**: HTTP server updates don't require image rebuilds
- **Elegance**: `FROM affine:latest-base` vs concatenating Dockerfiles

## Troubleshooting

### Container startup timeout

```python
# Check Docker logs if container fails to start
# docker logs <container_name>

# Verify image CMD starts HTTP server on port 8000
# Ensure /health endpoint is accessible
```

### Environment type detection

```python
# Manually override if detection fails
env = rf_env.load_env(
    image="my:image",
    env_type="http_based"  # or "function_based"
)
```

### Method not found

```python
# List available methods
methods = await env.list_methods()
print(methods)
```

### SSH connection issues

```bash
# Test SSH access to Docker daemon
ssh user@remote-host docker ps

# Check SSH key permissions
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub

# Verify Docker daemon is accessible
docker -H ssh://user@remote-host ps
```

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- Code follows existing patterns
- Tests pass (when available)
- Documentation is updated
