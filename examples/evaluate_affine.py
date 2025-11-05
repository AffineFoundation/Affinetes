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

    image = af_env.build_image_from_env(
        env_path="environments/affine",
        image_tag="affine:latest",
        nocache=False,
        quiet=False
    )

    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        print("   Or create .env file with: CHUTES_API_KEY=your-key")
        sys.exit(1)

    print("\n1. Loading environment from pre-built image 'affine:latest'...")
    
    env = af_env.load_env(
        image=image,
        mode="docker",
        env_vars={"CHUTES_API_KEY": api_key}
    )
    print("   ✓ Environment loaded (container started with HTTP server)")

    try:
        print("\n2. Available methods in environment:")
        await env.list_methods(print_info=True)

        print("\n3. Running evaluation in container (async)...")
        result = await env.evaluate(
            task_type="abd",
            model="deepseek-ai/DeepSeek-V3",
            base_url="https://llm.chutes.ai/v1",
            num_samples=2
        )
        
        print(f"\n4. Results:")
        print(f"   Task: {result['task_name']}")
        print(f"   Total score: {result['total_score']}")
        print(f"   Success rate: {result['success_rate'] * 100:.1f}%")
        print(f"   Time taken: {result['time_taken']:.2f}s")
        
        print(f"\n   Sample details:")
        for detail in result['details']:
            print(f"\n   Sample {detail['id']}:")
            print(f"     Success: {detail['success']}")
            print(f"     Reward: {detail['reward']}")
            
            if 'error' in detail:
                print(f"     Error type: {detail.get('error_type', 'unknown')}")
                print(f"     Error: {detail['error'][:200]}...")
            
            if 'experiences' in detail:
                print(f"     Challenge: {str(detail['experiences'])[:200]}...")
    except Exception as e:
        print(f"\n   ❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())