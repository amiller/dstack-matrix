"""Relay hermes notebook entries to a Matrix room.

Polls /api/entries, posts new ones to a Matrix room.
AI-only entries get a vague summary from keywords/topicHints.
Tracks last seen entry ID to avoid duplicates.
"""
import asyncio, json, os, time, random
import aiohttp
from nio import AsyncClient, AsyncClientConfig, RoomCreateResponse, RoomSendResponse

NOTEBOOK_URL = os.environ.get("NOTEBOOK_URL", "https://hermes.teleport.computer")
HOMESERVER = os.environ.get("HOMESERVER", "http://localhost:6167")
BOT_USER_ID = os.environ.get("BOT_USER_ID")
BOT_ACCESS_TOKEN = os.environ.get("BOT_ACCESS_TOKEN")
BOT_DEVICE_ID = os.environ.get("BOT_DEVICE_ID", "relay")
ROOM_ID = os.environ.get("NOTEBOOK_ROOM_ID", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
STATE_FILE = os.environ.get("STATE_FILE", "/data/relay_state.json")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_seen_id": None, "room_id": None}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

async def make_client():
    config = AsyncClientConfig(encryption_enabled=False)
    client = AsyncClient(HOMESERVER, BOT_USER_ID, config=config)
    client.restore_login(BOT_USER_ID, BOT_DEVICE_ID, BOT_ACCESS_TOKEN)
    return client

async def ensure_room(client, state):
    if state.get("room_id"):
        return state["room_id"]
    if ROOM_ID:
        state["room_id"] = ROOM_ID
        save_state(state)
        return ROOM_ID
    resp = await client.room_create(
        name="hermes-notebook",
        topic="Live feed from the hermes shared notebook",
    )
    assert isinstance(resp, RoomCreateResponse), f"room create failed: {resp}"
    state["room_id"] = resp.room_id
    save_state(state)
    print(f"Created room: {resp.room_id}")
    return resp.room_id

async def fetch_entries(session, since_id=None):
    params = {"limit": 20}
    async with session.get(f"{NOTEBOOK_URL}/api/entries", params=params) as resp:
        data = await resp.json(content_type=None)
        return data.get("entries", [])

def vague_summary(entry):
    """Turn keywords/topicHints into a vague one-liner for AI-only entries."""
    hints = entry.get("topicHints", [])
    keywords = entry.get("keywords", [])
    if hints:
        topics = ", ".join(hints)
        return f"posted about: {topics}"
    # Pick 3-5 interesting keywords (skip boring ones)
    boring = {"the", "a", "an", "is", "are", "was", "were", "got", "new", "two", "via"}
    interesting = [k for k in keywords if k not in boring and len(k) > 3][:5]
    if interesting:
        return f"posted about: {', '.join(interesting)}"
    return "posted something"

def format_entry(entry):
    handle = entry.get("handle", "")
    pseudonym = entry.get("pseudonym", "unknown")
    content = entry.get("content", "").strip()
    client = entry.get("client", "")
    model = entry.get("model", "")
    author = handle or pseudonym
    tag = f" via {model}" if model else ""

    if entry.get("aiOnly") and not content:
        summary = vague_summary(entry)
        return f"**{author}**{tag}: _{summary}_"

    return f"**{author}**{tag}:\n{content}"

async def relay_loop():
    state = load_state()
    client = await make_client()
    room_id = await ensure_room(client, state)
    print(f"Relaying to room {room_id}, polling every {POLL_INTERVAL}s")

    async with aiohttp.ClientSession() as session:
        while True:
            entries = await fetch_entries(session, state.get("last_seen_id"))
            # Reverse so oldest first
            new_entries = []
            for entry in reversed(entries):
                if state.get("last_seen_id") and entry["id"] <= state["last_seen_id"]:
                    continue
                new_entries.append(entry)

            for entry in new_entries:
                msg = format_entry(entry)
                resp = await client.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": msg, "format": "org.matrix.custom.html",
                             "formatted_body": msg.replace("\n", "<br>")},
                )
                if isinstance(resp, RoomSendResponse):
                    print(f"Relayed: {entry['id']}")
                state["last_seen_id"] = entry["id"]
                save_state(state)

            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(relay_loop())
