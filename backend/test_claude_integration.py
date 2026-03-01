#!/usr/bin/env python3
"""Test script for Claude/Anthropic integration.

This script tests the Claude integration by creating tasks with different
LLM providers and models.

Usage:
    python test_claude_integration.py
"""

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000/api/v1"

# Test configurations
TEST_CASES = [
    {
        "name": "OpenAI GPT-4 Research",
        "data": {
            "prompt": "Research the latest trends in AI agents",
            "task_type": "research",
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo-preview"
        }
    },
    {
        "name": "Claude Opus Research",
        "data": {
            "prompt": "Research the latest trends in AI agents",
            "task_type": "research",
            "llm_provider": "anthropic",
            "llm_model": "claude-3-opus-20240229"
        }
    },
    {
        "name": "Claude Sonnet Research",
        "data": {
            "prompt": "Research quantum computing applications",
            "task_type": "research",
            "llm_provider": "anthropic",
            "llm_model": "claude-3-sonnet-20240229"
        }
    },
    {
        "name": "Claude Haiku (Fast) Research",
        "data": {
            "prompt": "Summarize recent news about space exploration",
            "task_type": "research",
            "llm_provider": "anthropic",
            "llm_model": "claude-3-haiku-20240307"
        }
    },
]


async def test_claude_integration():
    """Test Claude integration across all agents."""
    
    print("🚀 Testing Claude/Anthropic Integration\n")
    print("=" * 60)
    
    # First, authenticate (assuming you have a mock auth or test user)
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Get auth token (you'll need to adapt this to your auth flow)
        # For now, we'll assume you have a test token or guest mode
        headers = {
            "Content-Type": "application/json",
            # "Authorization": "Bearer YOUR_TEST_TOKEN"
        }
        
        for test_case in TEST_CASES:
            print(f"\n📝 Test: {test_case['name']}")
            print(f"   Provider: {test_case['data']['llm_provider']}")
            print(f"   Model: {test_case['data']['llm_model']}")
            print(f"   Task Type: {test_case['data']['task_type']}")
            
            try:
                # Create task
                response = await client.post(
                    f"{BASE_URL}/tasks",
                    json=test_case['data'],
                    headers=headers
                )
                
                if response.status_code == 201:
                    task = response.json()
                    task_id = task['id']
                    print(f"   ✅ Task created: {task_id}")
                    print(f"   Status: {task['status']}")
                    print(f"   LLM: {task.get('llm_provider', 'N/A')}/{task.get('llm_model', 'N/A')}")
                else:
                    print(f"   ❌ Failed to create task: {response.status_code}")
                    print(f"   Response: {response.text}")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
            
            print(f"   {'-' * 50}")
    
    print("\n" + "=" * 60)
    print("✨ Test completed!")
    print("\n💡 Next steps:")
    print("   1. Check Celery worker logs for task execution")
    print("   2. Verify LangFuse dashboard for trace data")
    print("   3. Check database for llm_provider and llm_model fields")


async def test_api_schema():
    """Test that API accepts new parameters."""
    
    print("\n🔍 Testing API Schema\n")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        try:
            # Get OpenAPI schema
            response = await client.get(f"{BASE_URL}/../openapi.json")
            
            if response.status_code == 200:
                schema = response.json()
                task_create_schema = schema["components"]["schemas"].get("TaskCreate", {})
                properties = task_create_schema.get("properties", {})
                
                print("\n📋 TaskCreate Schema Properties:")
                for prop, details in properties.items():
                    print(f"   • {prop}: {details.get('type', 'unknown')}")
                    if 'default' in details:
                        print(f"     Default: {details['default']}")
                
                # Check for new fields
                if "llm_provider" in properties and "llm_model" in properties:
                    print("\n   ✅ LLM provider and model fields are present!")
                else:
                    print("\n   ❌ LLM fields are missing from schema")
            else:
                print(f"   ❌ Failed to get schema: {response.status_code}")
        
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" Claude/Anthropic Integration Test Suite")
    print("=" * 60)
    
    # Run schema test first
    asyncio.run(test_api_schema())
    
    # Then run integration tests
    asyncio.run(test_claude_integration())
    
    print("\n📚 Documentation:")
    print("   • Models documentation: docs/CLAUDE_INTEGRATION.md")
    print("   • API reference: http://localhost:8000/docs")
    print("   • LangFuse dashboard: https://cloud.langfuse.com")
    print("\n")
