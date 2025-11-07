# Affinetes

Lightweight container orchestration framework for Python environments.

Define environments once, deploy anywhere with Docker containers and secure HTTP communication.

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
import affinetes as af_env

# Build Docker image from environment directory
image_id = af_env.build_image_from_env(
    env_path="environments/affine",
    image_tag="affine:latest"
)
# HTTP server is automatically injected for function-based environments
```

### 3. Load and Execute

```python
import affinetes as af_env

# Load environment (starts container with env vars)
env = af_env.load_env(
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
async with af_env.load_env(
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
```

**Requirements:**
- Python 3.8+
- Docker daemon running
- For remote deployment: SSH access to remote Docker hosts

## Command-Line Interface (CLI)

Affinetes provides a simple CLI tool (`afs`) for managing containerized environments.

### Installation

After installing the package, the `afs` command will be available:

```bash
pip install -e .
afs --help
```

### Quick Start

```bash
# Terminal 1: Start environment (auto-displays available methods)
afs run bignickeye/affine:v2 --env CHUTES_API_KEY=xxx

# If CHUTES_API_KEY is already set as environment variable or in .env:
afs run bignickeye/affine:v2

# Start from local directory (auto-build):
afs run --dir environments/affine --tag affine:v2

# Terminal 2: Call methods (supports cross-process)
afs call affine-v2 evaluate --arg task_type=abd --arg num_samples=2
```

### CLI Commands

#### `afs run` - Start Environment

Start a container and automatically display available methods.

**From Docker image:**
```bash
afs run IMAGE [OPTIONS]

Options:
  --name NAME              Container name (default: derived from image)
  --env KEY=VALUE          Environment variable (can be repeated)
  --pull                   Pull image before starting
  --mem-limit MEM          Memory limit (e.g., 512m, 1g, 2g)
  --no-cache               Do not use cache when building (only with --dir)

Examples:
  afs run bignickeye/affine:v2 --env CHUTES_API_KEY=xxx
  afs run affine:latest --name my-affine --mem-limit 1g
```

**From directory (auto-build):**
```bash
afs run --dir PATH [OPTIONS]

Options:
  --dir PATH               Build from environment directory
  --tag TAG                Image tag (default: auto-generated)
  --no-cache               Do not use cache when building
  --env KEY=VALUE          Environment variable (can be repeated)

Examples:
  afs run --dir environments/affine --tag affine:v2
  afs run --dir ./my-env --env API_KEY=xxx --no-cache
```

**Output:**
After starting, available methods are automatically displayed:
```
✓ Environment started: affine-v2

Available Methods:
  - evaluate
  - reset

Usage:
  afs call affine-v2 <method> --arg key=value
```

#### `afs call` - Call Method

Execute a method on a running environment. Automatically connects to containers across different processes.

```bash
afs call NAME METHOD [OPTIONS]

Options:
  --arg KEY=VALUE          Method argument (can be repeated)
  --json JSON_STRING       JSON string for complex arguments
  --timeout SECONDS        Timeout in seconds (default: 300)

Examples:
  # Simple arguments
  afs call affine-v2 evaluate --arg task_type=abd --arg num_samples=2
  
  # Complex JSON arguments
  afs call affine-v2 evaluate --json '{"task_type": "sat", "num_samples": 5}'
  
  # With timeout
  afs call affine-v2 evaluate --arg task_type=ded --timeout 600
  
  # Mix both (--json overrides --arg)
  afs call my-env process --arg mode=fast --json '{"config": {"batch": 10}}'
```

**Argument Types:**
- Simple values: `--arg key=value`
- Numbers: `--arg count=10` (auto-parsed)
- Booleans: `--arg enabled=true`
- Complex: `--json '{"key": [1, 2, 3]}'`

### CLI Design Philosophy
**Workflow:**
```bash
# 1. Start environment (displays methods automatically)
afs run --dir environments/affine --tag affine:v2

# 2. Call methods (from same or different terminal)
afs call affine-v2 evaluate --arg task_type=abd --arg num_samples=2

# 3. Stop container when done (standard Docker command)
docker stop affine-v2
```

**Use Docker commands for container management:**
```bash
# List all containers
docker ps

# View logs
docker logs affine-v2 --tail 50

# Stop containers
docker stop affine-v2

# Remove containers
docker rm affine-v2
```

### CLI vs SDK

| Feature | CLI (`afs`) | SDK (`affinetes`) |
|---------|-------------|-------------------|
| Use case | Quick testing, cross-process | Programmatic control |
| State | No state, Docker-native | In-process registry |
| Commands | 2 commands (run, call) | Full API |
| Reconnect | Auto-reconnect by name | Manual registry management |
| Best for | Terminal workflows, debugging | Production apps, complex logic |

**When to use CLI:**
- Quick environment testing
- Cross-terminal method calls
- Simple deployment workflows
- Learning and debugging

**When to use SDK:**
- Production applications
- Complex workflows with logic
- Multi-instance deployments
- Need programmatic control

## API Reference

### `build_image_from_env()`

Build Docker image from environment directory.

```python
af_env.build_image_from_env(
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
af_env.load_env(
    image: str,                             # Docker image name
    mode: str = "docker",                   # "docker" or "basilica"
    replicas: int = 1,                      # Number of instances
    hosts: List[str] = None,                # Docker daemon addresses
    load_balance: str = "random",           # "random" or "round_robin"
    container_name: str = None,             # Optional container name prefix
    env_vars: Dict[str, str] = None,        # Environment variables
    env_type: str = None,                   # Override type detection
    force_recreate: bool = False,           # Force container recreation
    pull: bool = False,                     # Pull image before deployment
    mem_limit: str = None,                  # Memory limit (e.g., "512m", "1g", "2g")
    cleanup: bool = True,                   # Auto cleanup container on exit
    **kwargs                                # Additional backend options
) -> EnvironmentWrapper
```

**Important:** Environment variables should be passed via `env_vars` parameter.

**Multi-Instance Deployment:**

```python
# Deploy 3 local instances with load balancing
env = af_env.load_env(
    image="affine:latest",
    replicas=3,
    load_balance="random"
)

# Deploy to remote Docker daemons via SSH
env = af_env.load_env(
    image="affine:latest",
    replicas=2,
    hosts=["ssh://user@host1", "ssh://user@host2"]
)

# Mixed deployment (1 local + 2 remote)
env = af_env.load_env(
    image="affine:latest",
    replicas=3,
    hosts=["localhost", "ssh://user@host1", "ssh://user@host2"]
)

# Keep container running for debugging
env = af_env.load_env(
    image="affine:latest",
    cleanup=False  # Container persists after program exits
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
af_env.list_active_environments()      # List all active environment IDs
af_env.cleanup_all_environments()      # Cleanup all environments (auto on exit)
af_env.get_environment(env_id)         # Get environment by ID
```

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      User Application                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  import affinetes as af_env                          │ │
│  │  env = af_env.load_env("affine:latest", replicas=3)    │ │
│  │  result = await env.evaluate(...)                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Affinetes Framework                     │
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
import affinetes as af_env
import asyncio

async def main():
    # Build image
    image = af_env.build_image_from_env(
        env_path="environments/affine",
        image_tag="affine:latest"
    )
    
    # Load environment
    env = af_env.load_env(
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
import affinetes as af_env
import asyncio

async def main():
    # Deploy 3 local instances
    env = af_env.load_env(
        image="affine:latest",
        replicas=3,
        load_balance="round_robin",
        env_vars={"CHUTES_API_KEY": "your-key"}
    )
    
    # Check pool statistics
    stats = env.get_stats()
    print(f"Total instances: {stats['total_instances']}")
    
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
import affinetes as af_env
import asyncio

async def main():
    # Deploy to remote Docker daemons via SSH
    env = af_env.load_env(
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
import affinetes as af_env
import asyncio

async def main():
    # Deploy multiple environments
    env1 = af_env.load_env(
        image="affine:latest",
        replicas=3,
        env_vars={"API_KEY": "key1"}
    )
    
    env2 = af_env.load_env(
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

### Memory Limits and Auto-Restart

```python
# Set memory limit to prevent memory leaks
# Container will be killed and auto-restarted when exceeding limit
env = af_env.load_env(
    image="affine:latest",
    mem_limit="512m",        # Limit memory to 512MB
    env_vars={"API_KEY": "your-key"}
)

# Multi-instance with memory limits (each instance limited)
env = af_env.load_env(
    image="affine:latest",
    replicas=3,
    mem_limit="1g",          # Each instance limited to 1GB
    load_balance="random"
)
```

**How it works:**
- When container exceeds `mem_limit`, Docker's OOM killer terminates it
- Due to `restart_policy="always"`, container automatically restarts
- This prevents memory leaks from consuming all system resources
- See [`examples/memory_limit_example.py`](examples/memory_limit_example.py:1) for complete examples

### Container Reuse

```python
# First run: creates container
env1 = af_env.load_env(
    image="affine:latest",
    container_name="my-affine"
)
await env1.cleanup()

# Second run: reuses existing container (if still exists)
env2 = af_env.load_env(
    image="affine:latest",
    container_name="my-affine"
)

# Force recreation
env3 = af_env.load_env(
    image="affine:latest",
    container_name="my-affine",
    force_recreate=True  # Removes and recreates container
)
```

### Image Pull Before Deployment

```python
# Pull latest image from registry before deployment
env = af_env.load_env(
    image="affine:latest",
    pull=True  # Ensures using latest version
)

# Useful for:
# - Remote deployments (ensure image exists on remote host)
# - Production updates (pull latest tag)
# - Shared registries (sync image versions)
```

### Container Lifecycle Control

```python
# Default: Auto cleanup on exit
env = af_env.load_env(image="affine:latest")
# Container is stopped and removed when program exits

# Keep container running (for debugging)
env = af_env.load_env(
    image="affine:latest",
    cleanup=False
)
# Container continues running after program exits
# Manually stop with: docker stop <container_name>

# Use case 1: Debug environment after crash
env = af_env.load_env(
    image="affine:latest",
    container_name="debug-env",
    cleanup=False
)
# If program crashes, inspect container:
# docker logs debug-env
# docker exec -it debug-env /bin/bash

# Use case 2: Long-running background service
env = af_env.load_env(
    image="service:latest",
    cleanup=False
)
# Service stays running for external access
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
env = af_env.load_env(
    image="affine:latest",
    replicas=3,
    load_balance="random"
)

# Round-robin (even distribution)
env = af_env.load_env(
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

### SSH Tunnel for Secure Remote Access

When deploying to remote Docker hosts, Affinetes automatically creates **SSH tunnels** to securely access Docker containers' internal network without exposing any ports:

```
┌──────────────────┐                    ┌──────────────────┐
│  Local Machine   │                    │  Remote Host     │
│                  │                    │                  │
│  Affinetes       │  SSH Connection    │  Docker Daemon   │
│  Framework       │◄──────────────────►│                  │
│                  │  (Encrypted)       │                  │
│  127.0.0.1:XXXX ─┼────────────────────┼→ 172.17.0.X:8000 │
│  (Local Port)    │   Port Forwarding  │  (Container IP)  │
└──────────────────┘                    └──────────────────┘
```

**Key Features:**
- **Zero Port Exposure**: Remote containers never expose ports to internet
- **Encrypted by Default**: All traffic through SSH tunnel (port 22 only)
- **Fully Automatic**: Framework handles tunnel creation/cleanup transparently
- **Multi-Container**: Each remote container gets isolated tunnel with dynamic port allocation

**Implementation:**
```python
# Automatic tunnel creation and management
env = af_env.load_env(
    image="affine:latest",
    hosts=["ssh://user@remote-host"]  # SSH tunnel auto-created
)
result = await env.evaluate(...)  # Traffic via tunnel
await env.cleanup()  # Tunnel auto-closed
```

**Technical Details:**
- Native Python `paramiko` library (no external dependencies)
- SSH public key authentication (see SSH Setup section above)
- Channel-based port forwarding with proper cleanup
- Implementation: [`affinetes/infrastructure/ssh_tunnel.py`](affinetes/infrastructure/ssh_tunnel.py:1)

**Troubleshooting:** See "SSH connection issues" section below for setup verification and common problems.

### Why Two-Stage Build?

- **Clean separation**: Base image (dependencies) + Server layer (framework)
- **Zero burden**: Environment developers don't write HTTP code
- **Maintainability**: HTTP server updates don't require image rebuilds
- **Flexibility**: Framework can inject different server implementations

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
env = af_env.load_env(
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
