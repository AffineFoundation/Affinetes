"""
Producer-Consumer Pattern with Multi-Environment Pool

Demonstrates:
- Building multiple environment images
- Deploying 15 environment instances (5 affine + 10 agentgym variants)
- Producer thread generating random tasks
- Consumer thread executing tasks on appropriate environments
- Real-time result reporting with task details
"""

import asyncio
import random
import time
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from queue import Queue
from threading import Thread

import affinetes as af_env
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)


# Task definitions
@dataclass
class Task:
    """Represents a task to be executed"""

    task_id: int
    env_type: str  # "affine" or "agentgym"
    task_name: str  # "sat", "abd", "ded", "webshop", etc.
    params: Dict[str, Any]


@dataclass
class TaskResult:
    """Represents task execution result"""

    task_id: int
    env_type: str
    task_name: str
    score: float
    execution_time: float
    interaction_sample: Optional[str] = None
    error: Optional[str] = None


# Environment configurations
AFFINE_TASKS = ["sat", "abd", "ded"]
AGENTGYM_ENVS = ["webshop", "alfworld", "babyai", "sciworld", "textcraft"]


def generate_hosts(replicas_per_host: int) -> tuple[int, list]:
    """
    Generate hosts list based on environment variable AFFINETES_HOSTS

    Args:
        replicas_per_host: Number of replicas per host

    Returns:
        tuple: (total_replicas, hosts_list)

    Environment Variable:
        AFFINETES_HOSTS: Comma-separated list of hosts
            - Empty or not set: Use local only
            - Format: "host1,host2,host3"
            - Example: "ssh://root@192.168.1.100,ssh://root@192.168.1.101"
            - "localhost" or None will be treated as local deployment
    """
    hosts_env = os.getenv("AFFINETES_HOSTS", "").strip()

    if not hosts_env:
        # No hosts specified, use local only
        return replicas_per_host, [None] * replicas_per_host

    # Parse hosts from environment variable
    hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]

    # If no valid hosts after parsing, fall back to local
    if not hosts:
        return replicas_per_host, [None] * replicas_per_host

    # Generate host list by repeating each host replicas_per_host times
    expanded_hosts = []
    for host in hosts:
        expanded_hosts.extend([host] * replicas_per_host)

    total_replicas = len(expanded_hosts)

    return total_replicas, expanded_hosts


# Generate configurations dynamically
def create_env_configs():
    """Create environment configurations with dynamic host allocation"""

    # Define replicas per host for each environment
    affine_replicas_per_host = 2
    agentgym_replicas_per_host = 1

    # Generate hosts
    affine_total, affine_hosts = generate_hosts(affine_replicas_per_host)
    agentgym_total, agentgym_hosts = generate_hosts(agentgym_replicas_per_host)

    configs = {
        "affine": {
            "path": "environments/affine",
            "image": "bignickeye/affine:latest",
            "replicas": affine_total,
            "hosts": affine_hosts,
        }
    }

    # Add AgentGym environments
    for env_name in AGENTGYM_ENVS:
        configs[f"agentgym:{env_name}"] = {
            "path": "environments/agentgym",
            "image": f"bignickeye/agentgym:{env_name}",
            "replicas": agentgym_total,
            "hosts": agentgym_hosts.copy(),  # Use copy to avoid reference issues
            "buildargs": {"ENV_NAME": env_name},
        }

    return configs


# Create configurations
ENV_CONFIGS = create_env_configs()


def load_environments() -> Dict[str, Any]:
    """Load all environment instances into a pool"""
    print("\n" + "=" * 60)
    print("Loading Environment Instances")
    print("=" * 60)

    env_pool = {}

    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        sys.exit(1)

    # Common environment variables
    env_vars = {"CHUTES_API_KEY": api_key}

    for env_key, config in ENV_CONFIGS.items():
        print(
            f"\n[LOAD] Loading {config['replicas']} instances of '{config['image']}'..."
        )
        start = time.time()

        try:
            env = af_env.load_env(
                image=config["image"],
                mode="docker",
                replicas=config["replicas"],
                hosts=config["hosts"],
                load_balance="random",
                env_vars=env_vars,
                pull=True,
            )

            elapsed = time.time() - start
            print(
                f"[OK] Loaded '{env_key}' ({config['replicas']} replicas) in {elapsed:.1f}s"
            )

            # Store with simplified key
            if env_key == "affine":
                env_pool["affine"] = env
            else:
                # Extract env name from "agentgym:webshop" -> "webshop"
                env_name = env_key.split(":")[1]
                env_pool[env_name] = env

        except Exception as e:
            print(f"[ERROR] Failed to load '{env_key}': {e}")
            raise

    print("\n" + "=" * 60)
    print(f"Successfully loaded {len(env_pool)} environment types")
    print(
        f"Total instances: {sum(config['replicas'] for config in ENV_CONFIGS.values())}"
    )
    print("=" * 60)

    return env_pool


def generate_task(task_id: int) -> Task:
    """Generate a random task"""
    # Randomly select task type
    all_tasks = AFFINE_TASKS + AGENTGYM_ENVS
    task_name = random.choice(all_tasks)

    # Determine environment type and parameters
    if task_name in AFFINE_TASKS:
        env_type = "affine"
        params = {
            "task_type": task_name,
            "num_samples": 1,
            "model": "deepseek-ai/DeepSeek-V3.1",
            "base_url": "https://llm.chutes.ai/v1",
            "timeout": 120,
        }
    else:
        env_type = task_name
        params = {
            "model": "deepseek-ai/DeepSeek-V3.1",
            "base_url": "https://llm.chutes.ai/v1",
            "temperature": 0.7,
            "ids": [random.randint(0, 100)],
            "max_round": 10,
            "timeout": 200,
        }

    return Task(task_id=task_id, env_type=env_type, task_name=task_name, params=params)


def producer_worker(task_queue: Queue, num_tasks: int):
    """Producer: Generate tasks and put into queue"""
    print(f"\n[PRODUCER] Starting to generate {num_tasks} tasks...")

    for i in range(num_tasks):
        task = generate_task(i)
        task_queue.put(task)
        print(
            f"[PRODUCER] Generated task #{task.task_id}: {task.env_type}/{task.task_name}"
        )
        time.sleep(0.5)  # Simulate task generation delay

    # Signal completion
    task_queue.put(None)
    print(f"[PRODUCER] Finished generating {num_tasks} tasks")


async def execute_task(task: Task, env_pool: Dict[str, Any]) -> TaskResult:
    """Execute a single task on appropriate environment"""
    start = time.time()

    try:
        env = env_pool.get(task.env_type)
        if not env:
            raise ValueError(f"Environment '{task.env_type}' not found in pool")

        # Execute task
        result = await env.evaluate(**task.params)

        # Extract relevant information
        execution_time = time.time() - start

        # Parse result based on environment type
        if task.env_type == "affine":
            score = result.get("total_score", 0.0)

            # Get interaction sample from first detail
            interaction_sample = None
            details = result.get("details", [])
            if details:
                first_detail = details[0]
                exp = first_detail.get("experiences", {})
                prompt = exp.get("challenge", "")[:100]
                response = (exp.get("llm_response") or "")[:100]
                interaction_sample = f"Q: {prompt}... A: {response}..."
        else:
            # AgentGym result format
            score = result.get("total_score", 0.0)

            # Get interaction sample
            details = result.get("details", [{}])
            interaction_sample = str(details[0].get("experiences", []))[:100]

        return TaskResult(
            task_id=task.task_id,
            env_type=task.env_type,
            task_name=task.task_name,
            score=score,
            execution_time=execution_time,
            interaction_sample=interaction_sample,
        )

    except Exception as e:
        execution_time = time.time() - start
        return TaskResult(
            task_id=task.task_id,
            env_type=task.env_type,
            task_name=task.task_name,
            score=0.0,
            execution_time=execution_time,
            error=str(e),
        )


def print_result(result: TaskResult):
    """Print formatted task result"""
    print(f"\n{'='*60}")
    print(f"Task #{result.task_id} Result")
    print(f"{'='*60}")
    print(f"  Environment: {result.env_type}")
    print(f"  Task Name:   {result.task_name}")
    print(f"  Score:       {result.score:.2f}")
    print(f"  Time:        {result.execution_time:.2f}s")

    if result.interaction_sample:
        print(f"  Sample:      {result.interaction_sample}")

    # Print error if exists
    if result.error:
        print(f"  Error:       {result.error}")

    print(f"{'='*60}")


async def consumer_worker(
    task_queue: Queue, env_pool: Dict[str, Any], max_concurrency: int = 5
):
    """Consumer: Execute tasks from queue with controlled concurrency

    Args:
        task_queue: Queue containing tasks to execute
        env_pool: Pool of environment instances
        max_concurrency: Maximum number of concurrent task executions (default: 5)
    """
    print(
        f"\n[CONSUMER] Starting task execution (max concurrency: {max_concurrency})..."
    )

    # Semaphore to control concurrency
    semaphore = asyncio.Semaphore(max_concurrency)

    # Track running tasks
    running_tasks = []
    completed = 0

    async def execute_with_semaphore(task: Task):
        """Execute task with semaphore control"""
        nonlocal completed
        async with semaphore:
            print(
                f"[CONSUMER] Executing task #{task.task_id}: {task.env_type}/{task.task_name}"
            )
            result = await execute_task(task, env_pool)
            print_result(result)
            completed += 1
            task_queue.task_done()

    while True:
        # Get task from queue
        task = task_queue.get()

        # Check for completion signal
        if task is None:
            print(
                f"\n[CONSUMER] Received completion signal, waiting for {len(running_tasks)} running tasks..."
            )
            break

        # Create task and add to running list
        task_coro = asyncio.create_task(execute_with_semaphore(task))
        running_tasks.append(task_coro)

    # Wait for all running tasks to complete
    if running_tasks:
        await asyncio.gather(*running_tasks, return_exceptions=True)

    print(f"[CONSUMER] Finished executing {completed} tasks")


async def main():
    """Main orchestrator"""
    print("\n" + "=" * 60)
    print("Producer-Consumer Multi-Environment Demo")
    print("=" * 60)

    # Configuration
    NUM_TASKS = 50
    MAX_CONCURRENCY = 10  # Number of concurrent task executions

    # Step 1: Load environments
    env_pool = load_environments()

    # Step 2: Create task queue
    task_queue = Queue()

    # Step 3: Start producer thread
    producer_thread = Thread(
        target=producer_worker, args=(task_queue, NUM_TASKS), daemon=True
    )
    producer_thread.start()

    # Step 4: Start consumer (async)
    try:
        await consumer_worker(task_queue, env_pool, max_concurrency=MAX_CONCURRENCY)

    finally:
        # Step 6: Cleanup environments
        print("\n" + "=" * 60)
        print("Cleaning Up Environments")
        print("=" * 60)

        for env_name, env in env_pool.items():
            stats = env.get_stats()
            if stats:
                print(f"\n[STATS] {env_name}:")
                print(json.dumps(stats, indent=2))

            print(f"[CLEANUP] Stopping '{env_name}'...")
            try:
                await env.cleanup()
                print(f"[OK] Stopped '{env_name}'")
            except Exception as e:
                print(f"[ERROR] Failed to stop '{env_name}': {e}")

        print("\n" + "=" * 60)
        print("Demo Complete")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
