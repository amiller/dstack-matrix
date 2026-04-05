import json, os, random, time, uuid
from aiohttp import web, ClientSession
from run_sandbox import run_js

CHALLENGES_DIR = os.environ.get("CHALLENGES_DIR", "challenges")
HOMESERVER = os.environ.get("HOMESERVER", "http://localhost:6167")
PUBLIC_HOMESERVER = os.environ.get("PUBLIC_HOMESERVER", HOMESERVER)
REGISTRATION_TOKEN = os.environ.get("REGISTRATION_TOKEN", "hermes-bot-dev")
DENO_PATH = os.environ.get("DENO_PATH", "deno")
RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", "3"))

challenges = {}
pending = {}  # challenge_id -> {challenge, issued_at, ip}
rate_limits = {}  # ip -> [timestamps]

def load_challenges():
    for f in os.listdir(CHALLENGES_DIR):
        if f.endswith(".json"):
            with open(os.path.join(CHALLENGES_DIR, f)) as fh:
                c = json.load(fh)
                challenges[c["id"]] = c

def check_rate_limit(ip, max_attempts=RATE_LIMIT_MAX, window=600):
    now = time.time()
    timestamps = [t for t in rate_limits.get(ip, []) if now - t < window]
    if len(timestamps) >= max_attempts:
        return False
    timestamps.append(now)
    rate_limits[ip] = timestamps
    return True

async def handle_challenge(request):
    ip = request.remote
    if not check_rate_limit(ip):
        return web.json_response({"error": "Rate limited. Try again later."}, status=429)
    challenge = random.choice(list(challenges.values()))
    challenge_id = str(uuid.uuid4())
    pending[challenge_id] = {"challenge": challenge, "issued_at": time.time(), "ip": ip}
    return web.json_response({
        "challenge_id": challenge_id,
        "prompt": challenge["prompt"],
        "function_name": challenge["function_name"],
    })

async def handle_solve(request):
    body = await request.json()
    challenge_id = body.get("challenge_id", "")
    code = body.get("code", "")
    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        return web.json_response({"error": "username and password required"}, status=400)
    if challenge_id not in pending:
        return web.json_response({"error": "Invalid or expired challenge"}, status=400)

    entry = pending.pop(challenge_id)
    if time.time() - entry["issued_at"] > 300:
        return web.json_response({"error": "Challenge expired (5 min limit)"}, status=400)

    challenge = entry["challenge"]
    full_code = code + "\n" + challenge["test_code"]
    passed, output = run_js(full_code)

    if not passed:
        return web.json_response({"passed": False, "output": output})

    result = await register_user(username, password)
    return web.json_response({"passed": True, "homeserver": PUBLIC_HOMESERVER, **result})

async def register_user(username, password):
    """Register via two-step UIAA using the static registration token."""
    async with ClientSession() as session:
        async with session.post(f"{HOMESERVER}/_matrix/client/v3/register", json={
            "username": username, "password": password,
        }) as resp:
            data = await resp.json()
            if "access_token" in data:
                return {"user_id": data["user_id"], "access_token": data["access_token"]}
            uiaa_session = data.get("session", "")

        async with session.post(f"{HOMESERVER}/_matrix/client/v3/register", json={
            "username": username, "password": password,
            "auth": {"type": "m.login.registration_token", "token": REGISTRATION_TOKEN, "session": uiaa_session},
        }) as resp:
            data = await resp.json()
            assert "access_token" in data, f"Registration failed: {data}"
            return {"user_id": data["user_id"], "access_token": data["access_token"]}

app = web.Application()
app.router.add_get("/challenge", handle_challenge)
app.router.add_post("/solve", handle_solve)

if __name__ == "__main__":
    os.environ["DENO_PATH"] = DENO_PATH
    load_challenges()
    print(f"Challenge server starting on :8080 ({len(challenges)} challenges loaded)")
    web.run_app(app, port=int(os.environ.get("PORT", 8080)))
