"""Matrix onboarding tools — fetch challenge, solve with LLM, register."""
import os, json, aiohttp

CHALLENGE_URL = os.environ.get("CHALLENGE_URL", "https://a8629a1195ecb53afe1700cd3bafda1d18d9635d-8080.dstack-pha-prod7.phala.network")

async def fetch_challenge():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{CHALLENGE_URL}/challenge") as resp:
            return await resp.json()

async def submit_solution(challenge_id, code, username, password):
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{CHALLENGE_URL}/solve", json={
            "challenge_id": challenge_id,
            "code": code,
            "username": username,
            "password": password,
        }) as resp:
            return await resp.json()
