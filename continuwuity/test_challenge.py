"""Test the reverse CAPTCHA challenge server against live Continuwuity."""
import asyncio, aiohttp, pytest, os

CHALLENGE_URL = os.environ.get("CHALLENGE_URL", "http://localhost:8080")
HOMESERVER = os.environ.get("HOMESERVER", "http://localhost:6167")

SOLUTIONS = {
    "topWords": """function topWords(text, n) {
  const counts = {};
  text.toLowerCase().split(/\\s+/).filter(Boolean).forEach(w => counts[w] = (counts[w] || 0) + 1);
  return Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, n).map(e => e[0]);
}""",
    "flatten": """function flatten(arr) {
  const result = [];
  for (const item of arr) {
    if (Array.isArray(item)) result.push(...flatten(item));
    else result.push(item);
  }
  return result;
}""",
    "romanToInt": """function romanToInt(s) {
  const vals = {I:1, V:5, X:10, L:50, C:100, D:500, M:1000};
  let result = 0;
  for (let i = 0; i < s.length; i++) {
    if (i + 1 < s.length && vals[s[i]] < vals[s[i+1]]) result -= vals[s[i]];
    else result += vals[s[i]];
  }
  return result;
}""",
    "groupAnagrams": """function groupAnagrams(words) {
  const map = {};
  for (const w of words) {
    const key = w.split('').sort().join('');
    (map[key] = map[key] || []).push(w);
  }
  return Object.values(map).map(g => g.sort()).sort((a, b) => a[0].localeCompare(b[0]));
}""",
    "balancedParens": """function balancedParens(s) {
  const stack = [], pairs = {')':'(', ']':'[', '}':'{'};
  for (const c of s) {
    if ('([{'.includes(c)) stack.push(c);
    else if (')]}'.includes(c)) { if (stack.pop() !== pairs[c]) return false; }
  }
  return stack.length === 0;
}""",
}

async def get_challenge(session):
    async with session.get(f"{CHALLENGE_URL}/challenge") as resp:
        assert resp.status == 200
        return await resp.json()

async def solve(session, challenge_id, code, username, password="testpass123"):
    async with session.post(f"{CHALLENGE_URL}/solve", json={
        "challenge_id": challenge_id, "code": code,
        "username": username, "password": password,
    }) as resp:
        return resp.status, await resp.json()

def test_get_challenge():
    async def _():
        async with aiohttp.ClientSession() as s:
            data = await get_challenge(s)
            assert "challenge_id" in data
            assert "prompt" in data
            assert data["function_name"] in SOLUTIONS
    asyncio.run(_())

def test_solve_correct():
    async def _():
        async with aiohttp.ClientSession() as s:
            challenge = await get_challenge(s)
            code = SOLUTIONS[challenge["function_name"]]
            username = f"test-agent-{os.urandom(4).hex()}"
            status, result = await solve(s, challenge["challenge_id"], code, username)
            assert result["passed"] is True, f"Should pass: {result}"
            assert "user_id" in result
            assert "access_token" in result
            print(f"Registered: {result['user_id']}")
    asyncio.run(_())

def test_solve_wrong_code():
    async def _():
        async with aiohttp.ClientSession() as s:
            challenge = await get_challenge(s)
            bad_code = f"function {challenge['function_name']}() {{ return null; }}"
            status, result = await solve(s, challenge["challenge_id"], bad_code, "should-not-register")
            assert result["passed"] is False
            assert "user_id" not in result
    asyncio.run(_())

def test_expired_challenge():
    async def _():
        async with aiohttp.ClientSession() as s:
            status, result = await solve(s, "nonexistent", "whatever", "x")
            assert status == 400
    asyncio.run(_())

def test_missing_credentials():
    async def _():
        async with aiohttp.ClientSession() as s:
            challenge = await get_challenge(s)
            async with s.post(f"{CHALLENGE_URL}/solve", json={
                "challenge_id": challenge["challenge_id"], "code": "x",
            }) as resp:
                assert resp.status == 400
    asyncio.run(_())
