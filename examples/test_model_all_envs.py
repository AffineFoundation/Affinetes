"""
Test a Model on All Environments (Local GPU)

This script demonstrates how to:
1. Build all environment images (Affine + AgentGym variants)
2. Deploy them to your local GPU
3. Test a specific model across all environments
4. Collect and report results

Usage:
    python examples/test_model_all_envs.py --model "deepseek-ai/DeepSeek-V3" --samples 5
"""

import asyncio
import argparse
import json
import time
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import affinetes as af_env
from dotenv import load_dotenv

load_dotenv(override=True)


# ============================================================================
# Environment Configurations
# ============================================================================

# Affine tasks (SAT, ABD, DED)
AFFINE_TASKS = ["sat", "abd", "ded"]

# AgentGym environments
AGENTGYM_ENVS = [
    "webshop",
    "alfworld", 
    "babyai",
    "sciworld",
    "textcraft"
]


# ============================================================================
# Configuration Functions
# ============================================================================

def create_env_configs(use_local_images: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Create environment configurations for all tasks
    
    Args:
        use_local_images: If True, build images locally. If False, pull from registry
        
    Returns:
        Dictionary of environment configurations
    """
    configs = {}
    
    # Affine environment (handles SAT, ABD, DED)
    if use_local_images:
        configs["affine"] = {
            "path": "environments/affine",
            "image": "affine:latest",
            "build": True
        }
    else:
        configs["affine"] = {
            "image": "bignickeye/affine:latest",
            "build": False
        }
    
    # AgentGym environments (one container per environment)
    for env_name in AGENTGYM_ENVS:
        if use_local_images:
            configs[f"agentgym:{env_name}"] = {
                "path": "environments/agentgym",
                "image": f"agentgym:{env_name}",
                "build": True,
                "buildargs": {"ENV_NAME": env_name}
            }
        else:
            configs[f"agentgym:{env_name}"] = {
                "image": f"bignickeye/agentgym:{env_name}",
                "build": False
            }
    
    return configs


# ============================================================================
# Image Building
# ============================================================================

def build_images(configs: Dict[str, Dict[str, Any]], force_rebuild: bool = False) -> None:
    """
    Build all environment images
    
    Args:
        configs: Environment configurations
        force_rebuild: Force rebuild even if image exists
    """
    print("\n" + "=" * 80)
    print("STEP 1: Building Environment Images")
    print("=" * 80)
    
    for env_key, config in configs.items():
        if not config.get("build", False):
            print(f"\n[SKIP] Skipping build for '{env_key}' (using pre-built image)")
            continue
        
        print(f"\n[BUILD] Building '{config['image']}'...")
        start = time.time()
        
        try:
            af_env.build_image_from_env(
                env_path=config["path"],
                image_tag=config["image"],
                nocache=force_rebuild,
                quiet=False,
                buildargs=config.get("buildargs")
            )
            elapsed = time.time() - start
            print(f"[OK] Built '{config['image']}' in {elapsed:.1f}s")
        except Exception as e:
            print(f"[ERROR] Failed to build '{env_key}': {e}")
            raise


# ============================================================================
# Environment Loading
# ============================================================================

def load_environments(
    configs: Dict[str, Dict[str, Any]],
    replicas: int = 1,
    api_key: str = None
) -> Dict[str, Any]:
    """
    Load all environment instances
    
    Args:
        configs: Environment configurations
        replicas: Number of replicas per environment
        api_key: API key for LLM service
        
    Returns:
        Dictionary of loaded environments {env_name: wrapper}
    """
    print("\n" + "=" * 80)
    print(f"STEP 2: Loading Environments (replicas={replicas})")
    print("=" * 80)
    
    if not api_key:
        api_key = os.getenv("CHUTES_API_KEY")
        if not api_key:
            print("\n❌ ERROR: CHUTES_API_KEY not set")
            print("   Set it via: export CHUTES_API_KEY='your-key'")
            print("   Or create .env file with: CHUTES_API_KEY=your-key")
            sys.exit(1)
    
    env_pool = {}
    env_vars = {"CHUTES_API_KEY": api_key}
    
    for env_key, config in configs.items():
        print(f"\n[LOAD] Loading '{config['image']}' with {replicas} replica(s)...")
        start = time.time()
        
        try:
            env = af_env.load_env(
                image=config["image"],
                mode="docker",
                replicas=replicas,
                load_balance="random",
                env_vars=env_vars,
                pull=not config.get("build", False),  # Pull if not building locally
                mem_limit="8g"  # Limit memory for GPU usage
            )
            
            elapsed = time.time() - start
            print(f"[OK] Loaded '{env_key}' in {elapsed:.1f}s")
            
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
    
    print("\n" + "=" * 80)
    print(f"Successfully loaded {len(env_pool)} environment types")
    print("=" * 80)
    
    return env_pool


# ============================================================================
# Model Testing
# ============================================================================

async def test_affine_task(
    env,
    task_type: str,
    model: str,
    base_url: str,
    num_samples: int,
    temperature: float = 0.7,
    timeout: int = 600,
    seed: int = None,
    use_seed: bool = False
) -> Dict[str, Any]:
    """Test model on Affine task (SAT, ABD, DED)"""
    print(f"\n[TEST] Testing {model} on affine:{task_type} ({num_samples} samples)...")
    start = time.time()
    
    try:
        # Build kwargs conditionally based on seed support
        kwargs = {
            "task_type": task_type,
            "model": model,
            "base_url": base_url,
            "num_samples": num_samples,
            "timeout": timeout,
            "temperature": temperature
        }
        
        # Only add seed if explicitly requested (for locally built images)
        if use_seed and seed is not None:
            kwargs["seed"] = seed
        
        result = await env.evaluate(**kwargs)
        
        elapsed = time.time() - start
        print(f"[OK] Completed affine:{task_type} - Score: {result['total_score']:.2f}, Time: {elapsed:.1f}s")
        return result
        
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)
        
        # Check if error is due to seed parameter
        if "unexpected keyword argument 'seed'" in error_msg:
            print(f"[WARNING] Image doesn't support 'seed' parameter, retrying without it...")
            try:
                # Retry without seed
                result = await env.evaluate(
                    task_type=task_type,
                    model=model,
                    base_url=base_url,
                    num_samples=num_samples,
                    timeout=timeout,
                    temperature=temperature
                )
                elapsed = time.time() - start
                print(f"[OK] Completed affine:{task_type} - Score: {result['total_score']:.2f}, Time: {elapsed:.1f}s")
                return result
            except Exception as retry_e:
                elapsed = time.time() - start
                print(f"[ERROR] Failed affine:{task_type}: {retry_e}")
                return {
                    "task_name": f"affine:{task_type}",
                    "total_score": 0.0,
                    "success_rate": 0.0,
                    "num_evaluated": 0,
                    "time_taken": elapsed,
                    "error": str(retry_e)
                }
        else:
            print(f"[ERROR] Failed affine:{task_type}: {e}")
            return {
                "task_name": f"affine:{task_type}",
                "total_score": 0.0,
                "success_rate": 0.0,
                "num_evaluated": 0,
                "time_taken": elapsed,
                "error": error_msg
            }


async def test_agentgym_env(
    env,
    env_name: str,
    model: str,
    base_url: str,
    num_samples: int,
    max_round: int = 10,
    temperature: float = 0.7,
    timeout: int = 2400,
    seed: int = None,
    use_seed: bool = False
) -> Dict[str, Any]:
    """Test model on AgentGym environment"""
    print(f"\n[TEST] Testing {model} on {env_name} ({num_samples} samples)...")
    start = time.time()
    
    try:
        # Generate sample IDs (0 to num_samples-1)
        sample_ids = list(range(num_samples))
        
        # Build kwargs conditionally based on seed support
        kwargs = {
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "ids": sample_ids,
            "max_round": max_round,
            "timeout": timeout
        }
        
        # Only add seed if explicitly requested (for locally built images)
        if use_seed and seed is not None:
            kwargs["seed"] = seed
        
        result = await env.evaluate(**kwargs)
        
        elapsed = time.time() - start
        print(f"[OK] Completed {env_name} - Score: {result['total_score']:.3f}, Time: {elapsed:.1f}s")
        return result
        
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)
        
        # Check if error is due to seed parameter
        if "unexpected keyword argument 'seed'" in error_msg:
            print(f"[WARNING] Image doesn't support 'seed' parameter, retrying without it...")
            try:
                # Retry without seed
                result = await env.evaluate(
                    model=model,
                    base_url=base_url,
                    temperature=temperature,
                    ids=sample_ids,
                    max_round=max_round,
                    timeout=timeout
                )
                elapsed = time.time() - start
                print(f"[OK] Completed {env_name} - Score: {result['total_score']:.3f}, Time: {elapsed:.1f}s")
                return result
            except Exception as retry_e:
                elapsed = time.time() - start
                print(f"[ERROR] Failed {env_name}: {retry_e}")
                return {
                    "task_name": env_name,
                    "total_score": 0.0,
                    "success_rate": 0.0,
                    "num_evaluated": 0,
                    "time_taken": elapsed,
                    "error": str(retry_e)
                }
        else:
            print(f"[ERROR] Failed {env_name}: {e}")
            return {
                "task_name": env_name,
                "total_score": 0.0,
                "success_rate": 0.0,
                "num_evaluated": 0,
                "time_taken": elapsed,
                "error": error_msg
            }


async def run_all_tests(
    env_pool: Dict[str, Any],
    model: str,
    base_url: str,
    num_samples: int,
    temperature: float = 0.7,
    seed: int = None,
    max_concurrent: int = 3,
    use_local_images: bool = False
) -> List[Dict[str, Any]]:
    """
    Run tests on all environments with controlled concurrency
    
    Args:
        env_pool: Dictionary of loaded environments
        model: Model name to test
        base_url: API base URL
        num_samples: Number of samples per task
        temperature: Temperature for generation
        seed: Random seed for reproducibility
        max_concurrent: Maximum concurrent tests
        use_local_images: Whether using locally built images (supports seed parameter)
        
    Returns:
        List of test results
    """
    print("\n" + "=" * 80)
    print(f"STEP 3: Testing Model '{model}' on All Environments")
    print(f"Samples per task: {num_samples}, Concurrency: {max_concurrent}")
    if use_local_images and seed:
        print(f"Seed: {seed} (reproducible mode)")
    else:
        print(f"Seed: Not used (pre-built images don't support seed parameter)")
    print("=" * 80)
    
    # Create test tasks
    tasks = []
    
    # Affine tasks
    if "affine" in env_pool:
        for task_type in AFFINE_TASKS:
            tasks.append(
                test_affine_task(
                    env_pool["affine"],
                    task_type=task_type,
                    model=model,
                    base_url=base_url,
                    num_samples=num_samples,
                    temperature=temperature,
                    seed=seed,
                    use_seed=use_local_images
                )
            )
    
    # AgentGym environments
    for env_name in AGENTGYM_ENVS:
        if env_name in env_pool:
            tasks.append(
                test_agentgym_env(
                    env_pool[env_name],
                    env_name=env_name,
                    model=model,
                    base_url=base_url,
                    num_samples=num_samples,
                    temperature=temperature,
                    seed=seed,
                    use_seed=use_local_images
                )
            )
    
    # Run with controlled concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_with_semaphore(task):
        async with semaphore:
            return await task
    
    results = await asyncio.gather(*[run_with_semaphore(t) for t in tasks])
    
    return results


# ============================================================================
# Results Reporting
# ============================================================================

def print_results_summary(results: List[Dict[str, Any]]) -> None:
    """Print formatted summary of all test results"""
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    
    # Calculate overall statistics
    total_tasks = len(results)
    successful_tasks = sum(1 for r in results if "error" not in r)
    total_score = sum(r.get("total_score", 0.0) for r in results)
    avg_score = total_score / total_tasks if total_tasks > 0 else 0.0
    total_time = sum(r.get("time_taken", 0.0) for r in results)
    
    print(f"\nOverall Statistics:")
    print(f"  Total Tasks:       {total_tasks}")
    print(f"  Successful:        {successful_tasks}")
    print(f"  Failed:            {total_tasks - successful_tasks}")
    print(f"  Average Score:     {avg_score:.3f}")
    print(f"  Total Time:        {total_time:.1f}s")
    
    print(f"\nPer-Task Results:")
    print(f"{'Task':<25} {'Score':<10} {'Success Rate':<15} {'Time':<10} {'Status'}")
    print("-" * 80)
    
    for result in results:
        task_name = result.get("task_name", "unknown")
        score = result.get("total_score", 0.0)
        success_rate = result.get("success_rate", 0.0)
        time_taken = result.get("time_taken", 0.0)
        status = "✓ OK" if "error" not in result else "✗ FAILED"
        
        print(f"{task_name:<25} {score:<10.3f} {success_rate*100:<14.1f}% {time_taken:<9.1f}s {status}")
    
    print("=" * 80)


def save_results(results: List[Dict[str, Any]], output_file: str = "test_results.json") -> None:
    """Save results to JSON file"""
    output_path = Path(output_file)
    
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n[SAVED] Results saved to: {output_path.absolute()}")


# ============================================================================
# Main Function
# ============================================================================

async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Test a model on all environments")
    parser.add_argument("--model", type=str, default="deepseek-ai/DeepSeek-V3",
                       help="Model name to test")
    parser.add_argument("--base-url", type=str, default="https://llm.chutes.ai/v1",
                       help="API base URL")
    parser.add_argument("--samples", type=int, default=2,
                       help="Number of samples per task")
    parser.add_argument("--replicas", type=int, default=1,
                       help="Number of container replicas per environment")
    parser.add_argument("--temperature", type=float, default=0.7,
                       help="Temperature for generation")
    parser.add_argument("--seed", type=int, default=None,
                       help="Random seed for reproducibility")
    parser.add_argument("--max-concurrent", type=int, default=3,
                       help="Maximum concurrent tests")
    parser.add_argument("--build-local", action="store_true",
                       help="Build images locally instead of pulling from registry")
    parser.add_argument("--force-rebuild", action="store_true",
                       help="Force rebuild images (no cache)")
    parser.add_argument("--output", type=str, default="test_results.json",
                       help="Output file for results")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("MODEL TESTING ON ALL ENVIRONMENTS")
    print("=" * 80)
    print(f"Model:           {args.model}")
    print(f"Base URL:        {args.base_url}")
    print(f"Samples/task:    {args.samples}")
    print(f"Replicas:        {args.replicas}")
    print(f"Temperature:     {args.temperature}")
    print(f"Seed:            {args.seed or 'random'}")
    print(f"Max Concurrent:  {args.max_concurrent}")
    print(f"Build Strategy:  {'Local build' if args.build_local else 'Pull from registry'}")
    print("=" * 80)
    
    # Create configurations
    configs = create_env_configs(use_local_images=args.build_local)
    
    # Build images if needed
    if args.build_local:
        build_images(configs, force_rebuild=args.force_rebuild)
    
    # Load environments
    env_pool = load_environments(configs, replicas=args.replicas)
    
    try:
        # Run tests
        results = await run_all_tests(
            env_pool=env_pool,
            model=args.model,
            base_url=args.base_url,
            num_samples=args.samples,
            temperature=args.temperature,
            seed=args.seed,
            max_concurrent=args.max_concurrent,
            use_local_images=args.build_local
        )
        
        # Print and save results
        print_results_summary(results)
        save_results(results, args.output)
        
    finally:
        # Cleanup all environments
        print("\n" + "=" * 80)
        print("CLEANUP")
        print("=" * 80)
        
        for env_name, env in env_pool.items():
            print(f"[CLEANUP] Stopping '{env_name}'...")
            try:
                await env.cleanup()
                print(f"[OK] Stopped '{env_name}'")
            except Exception as e:
                print(f"[ERROR] Failed to stop '{env_name}': {e}")
        
        print("\n" + "=" * 80)
        print("COMPLETE")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())