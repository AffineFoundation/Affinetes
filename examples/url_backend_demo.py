import asyncio
import affinetes as af_env
import sys
import os

# User-deployed environment service URL
# This should be a service deployed by users themselves that implements
# the standard affinetes HTTP API endpoints:
# - GET /health - Health check
# - GET /methods - List available methods
# - POST /call - Call method with JSON body
ENVIRONMENT_SERVICE_URL = "http://your-service.com:8080"

async def main():
    """URL backend demo - connect to user-deployed environment service"""
    
    api_key = os.getenv("CHUTES_API_KEY")
    if not api_key:
        print("\n   ❌ CHUTES_API_KEY environment variable not set")
        print("   Please set: export CHUTES_API_KEY='your-key'")
        print("   Or create .env file with: CHUTES_API_KEY=your-key")
        sys.exit(1)

    # Load environment from user-deployed URL service
    env = af_env.load_env(
        mode="url",
        base_url=ENVIRONMENT_SERVICE_URL
    )
    
    try:
        # List available methods
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
        print("Result:", result)
        
    finally:
        await env.cleanup()


if __name__ == "__main__":
    print("=== URL Backend Demo ===\n")
    print("This demo shows how to connect to user-deployed environment services")
    print("via the URL mode.\n")
    print(f"Service URL: {ENVIRONMENT_SERVICE_URL}\n")
    print("Note: Update ENVIRONMENT_SERVICE_URL to your actual service URL before running\n")
    
    asyncio.run(main())