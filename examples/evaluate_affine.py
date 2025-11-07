import affinetes as af_env
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)


async def main():
    print("\n" + "=" * 60)
    print("Affinetes: Async Environment Execution Example")
    print("=" * 60)

    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        print("   Or create .env file with: CHUTES_API_KEY=your-key")
        sys.exit(1)

    print("\n1. Loading environment from pre-built image 'affine:latest'...")
    
    env = af_env.load_env(
        image="bignickeye/affine:v2",
        mode="docker",
        env_vars={"CHUTES_API_KEY": api_key},
        pull=True
    )
    print("   ✓ Environment loaded (container started with HTTP server)")

    try:
        print("\n2. Available methods in environment:")
        await env.list_methods(print_info=True)

        print("\n3. Running evaluation in container (async)...")
        result = await env.evaluate(
            task_type="abd",
            model="deepseek-ai/DeepSeek-V3",
            base_url="https://llm.chutes.ai/v1"
        )
        
        if 'error' in result:
            print(f"\n   Error occurred:")
            print(f"     Error type: {result.get('error_type', 'unknown')}")
            print(f"     Error: {result['error'][:200]}...")
            return

        print(f"\nResults:")
        print(f"   Task: {result['task_name']}")
        print(f"   Reward: {result['score']}")
        print(f"   Success: {result['success']}")
        print(f"   Time taken: {result['time_taken']:.2f}s")
        if 'extra' in result:
            print(f"\n   extra:")
            print(f"     {result['extra']}...")
    except Exception as e:
        print(f"\n   ❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())