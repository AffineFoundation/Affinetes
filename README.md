# Affinetes

Lightweight container orchestration framework for Python environments.

Define environments once, deploy anywhere with Docker containers and secure HTTP communication.

## Features
- **Simple Environment Definition**: Only requires `env.py` file
- **Container Isolation**: Isolated Docker containers with automatic cleanup
- **Secure Communication**: Internal network (no exposed ports) + SSH tunnels for remote access
- **Multi-Instance Support**: Deploy multiple replicas with load balancing
- **Dynamic Method Dispatch**: Automatic method exposure via HTTP API
- **Zero Burden**: Environment developers only write business logic

## Quick Start

### 1. Load Pre-built Image

```python
import affinetes as af_env
import asyncio

async def main():
    # Load environment from Docker image
    env = af_env.load_env(
        image="bignickeye/agentgym:sciworld-v2",
        env_vars={"CHUTES_API_KEY": "your-api-key"}
    )
    
    # Execute methods
    result = await env.evaluate(
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        task_id=10
    )
    
    print(f"Score: {result['score']}")
    
    # Cleanup
    await env.cleanup()

asyncio.run(main())
```

### 2. Async Context Manager (Recommended)

```python
async with af_env.load_env(
    image="bignickeye/agentgym:sciworld-v2",
    env_vars={"CHUTES_API_KEY": "your-api-key"}
) as env:
    result = await env.evaluate(
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        task_id=10
    )
# Auto cleanup
```

### 3. Build Custom Environment

Create `env.py`:

```python
import os

class Actor:
    def __init__(self):
        self.api_key = os.getenv("CHUTES_API_KEY")
    
    async def evaluate(self, **kwargs):
        # Your implementation
        return {"score": 1.0, "success": True}
```

Build and run:

```python
# Build image
af_env.build_image_from_env(
    env_path="environments/my-env",
    image_tag="my-env:latest"
)

# Load and execute
env = af_env.load_env(
    image="my-env:latest",
    env_vars={"CHUTES_API_KEY": "xxx"}
)
result = await env.evaluate()
```

## Installation

```bash
pip install -e .
```

**Requirements:**
- Python 3.8+
- Docker daemon running
- (Optional) SSH access for remote deployment

## Command-Line Interface

The `afs` CLI follows the **init → build → run → call** workflow.

### Workflow Overview

```bash
# 1. Initialize environment directory
afs init my-env --template actor

# 2. Build Docker image
afs build my-env --tag my-env:v1

# 3. Start environment container
afs run my-env:v1 --name my-env --env API_KEY=xxx

# 4. Call environment methods
afs call my-env evaluate --arg task_id=10
```

---

### `afs init` - Initialize Environment

Create a new environment directory with template files.

**Syntax:**
```bash
afs init NAME [--type TYPE] [--template TEMPLATE]
```

**Parameters:**
- `NAME`: Environment name (creates directory with this name)
- `--type`: Environment type
  - `function` (default): Function/class-based environment
  - `http`: HTTP-based environment
- `--template`: Template type
  - `basic` (default): Module functions
  - `actor`: Actor class
  - `fastapi`: FastAPI application

**Examples:**
```bash
# Create Actor class environment
afs init my-env --template actor

# Create FastAPI environment
afs init web-env --type http --template fastapi
```

**Generated Files:**
- `env.py` - Environment implementation
- `Dockerfile` - Docker build configuration

---

### `afs build` - Build Image

Build Docker image from environment directory.

**Syntax:**
```bash
afs build ENV_DIR --tag TAG [OPTIONS]
```

**Parameters:**
- `ENV_DIR`: Environment directory path
- `--tag TAG`: Image tag (required), format: `name:version`
- `--push`: Push to registry after build
- `--registry URL`: Registry URL (used with --push)
- `--no-cache`: Don't use build cache
- `--quiet`: Suppress build output
- `--build-arg KEY=VALUE`: Docker build arguments (can be specified multiple times)

**Examples:**
```bash
# Local build
afs build environments/affine --tag affine:v2

# Build and push
afs build my-env --tag my-env:v1 --push --registry docker.io/username

# Build without cache
afs build my-env --tag my-env:v1 --no-cache

# Build with arguments
afs build my-env --tag my-env:v1 --build-arg ENV_NAME=prod
```

**Directory Requirements:**
- Required: `env.py` - Environment implementation
- Required: `Dockerfile` - Build configuration
- Optional: `requirements.txt` - Python dependencies
- Optional: `config.py` - Configuration file

---

### `afs run` - Start Environment

Start environment container from image or directory.

**Syntax:**
```bash
afs run [IMAGE] [--dir ENV_DIR] [OPTIONS]
```

**Parameters:**
- `IMAGE`: Docker image name
- `--dir ENV_DIR`: Build from directory and start (auto-build)
- `--tag TAG`: Image tag when using --dir (default: auto-generated)
- `--name NAME`: Container name (default: derived from image)
- `--env KEY=VALUE`: Environment variables (can be specified multiple times)
- `--pull`: Pull image before starting
- `--mem-limit MEM`: Memory limit (e.g., 512m, 1g, 2g)
- `--no-cache`: Don't use cache when building (only with --dir)

**Examples:**
```bash
# Start from image
afs run bignickeye/agentgym:webshop-v2 --env CHUTES_API_KEY=xxx

# Specify container name and memory limit
afs run affine:v2 --name affine-prod --mem-limit 2g

# Build from directory and start
afs run --dir environments/my-env --tag my-env:latest

# Pull latest image before starting
afs run my-env:latest --pull
```

**After Starting:**
- Shows container name
- Lists available methods
- Displays usage examples

---

### `afs call` - Call Method

Call methods on running environment.

**Syntax:**
```bash
afs call NAME METHOD [OPTIONS]
```

**Parameters:**
- `NAME`: Environment/container name
- `METHOD`: Method name
- `--arg KEY=VALUE`: Method arguments (can be specified multiple times)
- `--json STRING`: JSON-formatted arguments
- `--timeout SECS`: Timeout in seconds (default: 300)

**Argument Parsing:**
- Auto-parse JSON values: `--arg ids=[10,20]` → `{"ids": [10, 20]}`
- String values: `--arg model="gpt-4"` → `{"model": "gpt-4"}`
- `--json` overrides `--arg` for same keys

**Examples:**
```bash
# Simple arguments
afs call my-env evaluate --arg task_id=10

# Complex arguments (lists, objects)
afs call webshop evaluate --arg ids=[10,20,30] --arg model="deepseek-ai/DeepSeek-V3"

# JSON arguments
afs call affine evaluate --json '{"task_type": "abd", "num_samples": 5}'

# Custom timeout
afs call my-env long_task --arg task_id=1 --timeout 600

# Combined arguments
afs call agentgym evaluate \
  --arg ids=[10] \
  --arg model="deepseek-ai/DeepSeek-V3" \
  --arg base_url="https://llm.chutes.ai/v1" \
  --arg seed=2717596881
```

**Notes:**
- Container must be running (started via `afs run` or verify with `docker ps`)
- Method must exist in environment's `env.py`
- Results output as JSON

---

### Complete Workflow Example

```bash
# 1. Initialize new environment
afs init eval-env --template actor

# 2. Edit env.py to implement logic
vim eval-env/env.py

# 3. Build image
afs build eval-env --tag eval-env:v1

# 4. Start environment
afs run eval-env:v1 --name eval --env API_KEY=xxx

# 5. Call methods
afs call eval evaluate --arg task_id=100

# 6. Stop container
docker stop eval
```

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

Load environment from Docker image.

```python
af_env.load_env(
    image: str,                    # Docker image name
    env_vars: Dict[str, str] = None,  # Environment variables
    replicas: int = 1,             # Number of instances
    hosts: List[str] = None,       # Remote hosts via SSH
    load_balance: str = "random",  # Load balancing: "random" or "round_robin"
    mem_limit: str = None,         # Memory limit: "512m", "1g", "2g"
    pull: bool = False,            # Pull image before starting
    cleanup: bool = True,          # Auto cleanup on exit
    **kwargs
) -> EnvironmentWrapper
```

**Examples:**

```python
# Basic usage
env = af_env.load_env(
    image="my-env:latest",
    env_vars={"API_KEY": "xxx"}
)

# Multi-instance with load balancing
env = af_env.load_env(
    image="my-env:latest",
    replicas=3,
    load_balance="round_robin"
)

# Remote deployment via SSH
env = af_env.load_env(
    image="my-env:latest",
    hosts=["ssh://user@host1", "ssh://user@host2"]
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

### Multi-Instance with Load Balancing

```python
# Deploy 3 instances with round-robin load balancing
env = af_env.load_env(
    image="my-env:latest",
    replicas=3,
    load_balance="round_robin"
)

# Concurrent execution (auto-balanced)
tasks = [env.evaluate(task_id=i) for i in range(10)]
results = await asyncio.gather(*tasks)

# Check distribution
stats = env.get_stats()
for inst in stats['instances']:
    print(f"{inst['host']}: {inst['requests']} requests")
```

### Remote Deployment via SSH

```python
# Deploy to remote hosts
env = af_env.load_env(
    image="my-env:latest",
    hosts=[
        "ssh://user@host1",
        "ssh://user@host2"
    ]
)

result = await env.evaluate(task_id=10)
```

### Memory Limits

```python
# Set memory limit (auto-restart on OOM)
env = af_env.load_env(
    image="my-env:latest",
    mem_limit="512m"
)

# Multi-instance with limits
env = af_env.load_env(
    image="my-env:latest",
    replicas=3,
    mem_limit="1g"  # Each instance limited
)
```

### Advanced Options

```python
# Keep container running for debugging
env = af_env.load_env(
    image="my-env:latest",
    cleanup=False  # Manual cleanup required
)

# Pull latest image before starting
env = af_env.load_env(
    image="my-env:latest",
    pull=True
)

# Custom timeout for method calls
result = await env.evaluate(
    task_id=10,
    _timeout=600  # 10 minutes
)
```

## Environment Types

### Function-Based (Recommended)

Define `env.py` with Actor class or module functions:

```python
class Actor:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
    
    async def evaluate(self, **kwargs):
        return {"score": 1.0, "success": True}
```

Framework automatically injects HTTP server - no HTTP code needed.

### HTTP-Based (Advanced)

Use existing FastAPI application:

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/evaluate")
async def evaluate(data: dict):
    return {"score": 1.0}
```

Requires `CMD` in Dockerfile to start server.


## Design Principles

### Why HTTP-based Communication?

- **Language-agnostic**: JSON over HTTP works with any language
- **Simple debugging**: Standard HTTP logs and tools
- **No version conflicts**: Independent of Python version
- **Production-ready**: Battle-tested protocol

### Why Internal Network?

- **Security**: No exposed ports to internet
- **Performance**: Direct container-to-container communication
- **Simplicity**: No port conflicts or management
- **SSH tunnels**: Secure remote access without exposure

### SSH Tunnels for Remote Access

Affinetes automatically creates SSH tunnels for secure remote deployment:

```python
env = af_env.load_env(
    image="my-env:latest",
    hosts=["ssh://user@remote-host"]
)
# Automatic SSH tunnel: local -> encrypted -> remote container
```

**Features:**
- Zero port exposure on remote host
- Encrypted communication via SSH
- Automatic tunnel management
- No manual configuration needed

**Setup:**
```bash
# Generate SSH key
ssh-keygen -t rsa -b 4096

# Copy to remote host
ssh-copy-id user@remote-host

# Test
ssh user@remote-host docker ps
```

## Troubleshooting

**Container won't start:**
```bash
# Check logs
docker logs <container_name>

# Verify HTTP server on port 8000
docker exec <container_name> curl localhost:8000/health
```

**Method not found:**
```python
# List available methods
methods = await env.list_methods()
print(methods)
```

**SSH connection fails:**
```bash
# Test SSH + Docker access
ssh user@remote-host docker ps

# Fix key permissions
chmod 600 ~/.ssh/id_rsa
```

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- Code follows existing patterns
- Tests pass (when available)
- Documentation is updated
