import asyncio
import affinetes as af_env
import sys
import os

BASILICA_BASE_URL = "http://xx.xx.xx.xx:8080"

async def run_basilica_demo():
    """Basilica backend demo - connect and evaluate remote environment"""
    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        print("   Or create .env file with: CHUTES_API_KEY=your-key")
        sys.exit(1)

    # Load environment from Basilica service
    env = af_env.load_env(
        image="affine",
        mode="basilica",
        base_url=BASILICA_BASE_URL
    )
    
    try:
        await env.list_methods(print_info=True)

        # Call evaluate method
        result = await env.evaluate(
            task_type="sat",
            model="deepseek-ai/DeepSeek-V3.1",
            base_url="https://llm.chutes.ai/v1",
            num_samples=1,
            timeout=120,
            api_key=api_key,
        )
        print("result", result)
        
    finally:
        await env.cleanup()


if __name__ == "__main__":
    asyncio.run(run_basilica_demo())