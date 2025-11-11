#!/usr/bin/env python3
"""
Simple evaluation script for affinetes environments

Usage:
    # Evaluate AgentGym environment
    python evaluate_model.py --image bignickeye/agentgym:sciworld-v2 --model deepseek-ai/DeepSeek-V3 --base-url https://llm.chutes.ai/v1 --task-id 10

    # Evaluate Affine environment  
    python evaluate_model.py --image bignickeye/affine:v2 --model deepseek-ai/DeepSeek-V3 --base-url https://llm.chutes.ai/v1 --task-type sat

    # Multiple samples
    python evaluate_model.py --image bignickeye/agentgym:webshop-v2 --model your-model --base-url http://localhost:8000/v1 --samples 5 --task-id 0
"""
import asyncio
import argparse
import sys
import os
import json
from dotenv import load_dotenv
import affinetes as af_env

load_dotenv(override=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate models on affinetes environments",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--image", required=True, help="Docker image (e.g., bignickeye/agentgym:sciworld-v2)")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--base-url", required=True, help="Model API base URL")
    parser.add_argument("--task-id", type=int, help="Task ID for AgentGym environments")
    parser.add_argument("--task-type", help="Task type for Affine environments (sat/abd/ded)")
    parser.add_argument("--samples", type=int, default=1, help="Number of samples (default: 1)")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature (default: 0.7)")
    parser.add_argument("--max-round", type=int, default=10, help="Max rounds for AgentGym (default: 10)")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--mem-limit", default="1g", help="Memory limit (default: 1g)")
    
    return parser.parse_args()


async def main():
    args = parse_args()
    
    # Check API key
    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("❌ CHUTES_API_KEY not set")
        print("   Set it: export CHUTES_API_KEY='your-key'")
        print("   Or add to .env file: CHUTES_API_KEY=your-key")
        sys.exit(1)
    
    print("=" * 60)
    print(f"Image: {args.image}")
    print(f"Model: {args.model}")
    print(f"Base URL: {args.base_url}")
    print(f"Samples: {args.samples}")
    print(f"Temperature: {args.temperature}")
    if args.task_id is not None:
        print(f"Task ID: {args.task_id}")
    if args.task_type:
        print(f"Task Type: {args.task_type}")
    print("=" * 60)
    
    # Load environment
    print(f"\nLoading environment from {args.image}...")
    env = af_env.load_env(
        image=args.image,
        mode="docker",
        env_vars={"CHUTES_API_KEY": api_key},
        pull=True,
        mem_limit=args.mem_limit,
    )
    print("✓ Environment loaded")
    
    # Build evaluation parameters
    eval_params = {
        "model": args.model,
        "base_url": args.base_url,
        "temperature": args.temperature,
        "timeout": args.timeout,
    }
    
    if args.task_id is not None:
        eval_params["task_id"] = args.task_id
        eval_params["max_round"] = args.max_round
    
    if args.task_type:
        eval_params["task_type"] = args.task_type
    
    # Run evaluation
    print(f"\nRunning {args.samples} evaluation(s)...")
    results = []
    total_score = 0.0
    total_time = 0.0
    
    for i in range(args.samples):
        print(f"\r  Progress: {i+1}/{args.samples}", end="", flush=True)
        
        result = await env.evaluate(**eval_params)
        
        score = result.get("score", 0.0)
        time_taken = result.get("time_taken", 0.0)
        total_score += score
        total_time += time_taken
        
        results.append({
            "index": i,
            "score": score,
            "success": result.get("success", False),
            "time_taken": time_taken,
            "task_name": result.get("task_name", "unknown"),
            "error": result.get("error"),
        })
    
    print()  # New line after progress
    
    # Summary
    avg_score = total_score / args.samples
    avg_time = total_time / args.samples
    
    summary = {
        "image": args.image,
        "model": args.model,
        "base_url": args.base_url,
        "samples": args.samples,
        "total_score": total_score,
        "average_score": avg_score,
        "total_time": total_time,
        "average_time": avg_time,
        "results": results,
    }
    
    if args.task_id is not None:
        summary["task_id"] = args.task_id
    if args.task_type:
        summary["task_type"] = args.task_type
    
    # Save to file if specified
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            print(f"✓ Results saved to: {args.output}")
        except Exception as e:
            print(f"✗ Failed to save results: {e}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total Samples: {args.samples}")
    print(f"  Average Score: {avg_score:.4f}")
    print(f"  Average Time: {avg_time:.2f}s")
    
    if args.samples > 1:
        print(f"\nDetailed Results:")
        for r in results:
            status = "✓" if r["success"] else "✗"
            print(f"  [{status}] Sample {r['index']}: score={r['score']:.4f}, time={r['time_taken']:.2f}s")
            if r.get("error"):
                print(f"      Error: {r['error']}")
    
    print("=" * 60)
    
    # Cleanup
    await env.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)