import asyncio
import os
import sys
import affinetes as af_env
from dotenv import load_dotenv
load_dotenv(override=True)

async def main():
    agentgym_type = "textcraft-v2"

    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        print("   Or create .env file with: CHUTES_API_KEY=your-key")
        sys.exit(1)

    env = af_env.load_env(
        image=f"bignickeye/agentgym:{agentgym_type}",
        mode="docker",
        env_vars={"CHUTES_API_KEY": api_key},
        pull=True,
    )

    print("\nRunning evaluation...")
    result = await env.evaluate(
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://llm.chutes.ai/v1",
        temperature=0.7,
        task_id=10,
        max_round=10,
        timeout=600
    )

    if result.get('error'):
        print(f"\nError occurred:")
        print(f"  {result['error']}")
        return

    print(f"\nResults:")
    print(f"Task: {result['task_name']}")
    print(f"Reward: {result['score']:.3f}")
    print(f"Success: {result['success']}")
    print(f"Time: {result['time_taken']:.1f}s")

    if result.get('extra'):
        print(f"\nextra:")
        print(f"  {result['extra']}")

if __name__ == "__main__":
    asyncio.run(main())