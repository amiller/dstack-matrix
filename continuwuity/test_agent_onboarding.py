"""End-to-end test: an LLM agent solves the reverse CAPTCHA and registers on Matrix.

Requires: ANTHROPIC_API_KEY or (GLM_API_KEY + GLM_BASE_URL) env vars.
"""
import asyncio, os, json, aiohttp, re

CHALLENGE_URL = os.environ.get("CHALLENGE_URL", "https://a8629a1195ecb53afe1700cd3bafda1d18d9635d-8080.dstack-pha-prod7.phala.network")

async def call_llm(prompt):
    """Call an LLM to generate code. Supports Anthropic or OpenAI-compatible APIs."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.anthropic.com/v1/messages", headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }) as resp:
                data = await resp.json()
                return data["content"][0]["text"]

    api_key = os.environ.get("GLM_API_KEY")
    base_url = os.environ.get("GLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
    if api_key:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base_url}/chat/completions", headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }, json={
                "model": os.environ.get("HERMES_MODEL", "glm-4.7"),
                "messages": [{"role": "user", "content": prompt}],
            }) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    raise RuntimeError("Set ANTHROPIC_API_KEY or GLM_API_KEY")

def extract_code(response, function_name):
    """Extract JS function from LLM response (handles markdown code blocks)."""
    # Try to find code block
    match = re.search(r'```(?:javascript|js)?\s*\n(.*?)```', response, re.DOTALL)
    code = match.group(1).strip() if match else response.strip()
    # Verify it contains the function
    if function_name not in code:
        raise ValueError(f"Response doesn't contain {function_name}: {code[:200]}")
    return code

async def main():
    print("=== Reverse CAPTCHA Agent Onboarding Test ===\n")

    # Step 1: Fetch challenge
    print("1. Fetching challenge...")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{CHALLENGE_URL}/challenge") as resp:
            challenge = await resp.json()
    print(f"   Challenge: {challenge['function_name']}")
    print(f"   Prompt: {challenge['prompt'][:100]}...\n")

    # Step 2: Ask LLM to solve it
    print("2. Asking LLM to write solution...")
    llm_prompt = f"""Write a JavaScript function that solves this challenge. Return ONLY the function, no explanation.

{challenge['prompt']}

Write the function as plain JavaScript (no imports, no exports). The function must be named `{challenge['function_name']}`.
"""
    response = await call_llm(llm_prompt)
    code = extract_code(response, challenge['function_name'])
    print(f"   Generated code:\n   {code[:200]}...\n")

    # Step 3: Submit solution
    print("3. Submitting solution...")
    username = f"agent-{os.urandom(4).hex()}"
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{CHALLENGE_URL}/solve", json={
            "challenge_id": challenge["challenge_id"],
            "code": code,
            "username": username,
            "password": "agentpass123",
        }) as resp:
            result = await resp.json()

    if result.get("passed"):
        print(f"   PASSED! Registered as {result['user_id']}")
        print(f"   Homeserver: {result['homeserver']}")
        print(f"   Access token: {result['access_token'][:20]}...")
        print("\n=== Agent successfully onboarded via reverse CAPTCHA! ===")
    else:
        print(f"   FAILED: {result.get('output', result)[:300]}")

        # Retry with error context
        print("\n4. Retrying with error context...")
        retry_prompt = f"""Your previous JavaScript solution failed. Here's the error:

{result.get('output', '')}

Fix the function. The original challenge was:
{challenge['prompt']}

Return ONLY the corrected function named `{challenge['function_name']}`, no explanation.
"""
        response = await call_llm(retry_prompt)
        code = extract_code(response, challenge['function_name'])
        print(f"   Retry code:\n   {code[:200]}...\n")

        # Need a new challenge (old one was consumed)
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{CHALLENGE_URL}/challenge") as resp:
                challenge2 = await resp.json()
            # Re-solve with the new challenge (may be different problem)
            response2 = await call_llm(f"Write a JavaScript function that solves this. Return ONLY the function, no explanation.\n\n{challenge2['prompt']}\n\nFunction must be named `{challenge2['function_name']}`.")
            code2 = extract_code(response2, challenge2['function_name'])
            async with s.post(f"{CHALLENGE_URL}/solve", json={
                "challenge_id": challenge2["challenge_id"],
                "code": code2,
                "username": username,
                "password": "agentpass123",
            }) as resp:
                result2 = await resp.json()

        if result2.get("passed"):
            print(f"   PASSED on retry! Registered as {result2['user_id']}")
            print("\n=== Agent successfully onboarded via reverse CAPTCHA! ===")
        else:
            print(f"   FAILED again: {result2.get('output', result2)[:300]}")
            raise AssertionError("Agent failed to solve challenge")

if __name__ == "__main__":
    asyncio.run(main())
