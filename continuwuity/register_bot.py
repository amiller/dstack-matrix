import asyncio, json, sys, aiohttp

async def register(session, homeserver, username, password, token):
    async with session.post(f"{homeserver}/_matrix/client/v3/register", json={
        "username": username, "password": password,
    }) as resp:
        data = await resp.json()
        if "access_token" in data:
            return data["user_id"], data["access_token"]
        uiaa_session = data.get("session", "")

    async with session.post(f"{homeserver}/_matrix/client/v3/register", json={
        "username": username, "password": password,
        "auth": {"type": "m.login.registration_token", "token": token, "session": uiaa_session},
    }) as resp:
        data = await resp.json()
        assert "access_token" in data, f"registration failed: {data}"
        return data["user_id"], data["access_token"]

async def main():
    homeserver = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:6167"
    username = sys.argv[2] if len(sys.argv) > 2 else "hermes-bot"
    password = sys.argv[3] if len(sys.argv) > 3 else "botpass123"
    token = sys.argv[4] if len(sys.argv) > 4 else "hermes-bot-dev"

    async with aiohttp.ClientSession() as session:
        user_id, access_token = await register(session, homeserver, username, password, token)
        print(json.dumps({"user_id": user_id, "access_token": access_token}, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
