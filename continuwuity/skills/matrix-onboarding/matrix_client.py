#!/usr/bin/env python3
"""Thin nio-based Matrix client for hermes agents.

Usage:
  matrix_client.py sync                      # get new messages since last sync
  matrix_client.py send ROOM_ID "message"    # send a text message
  matrix_client.py rooms                     # list joined rooms
  matrix_client.py create "Room Name" [@user:server ...]  # create room, optionally invite
  matrix_client.py invite ROOM_ID @user:server  # invite user to room
  matrix_client.py status                    # show login status + device info

State stored in ~/.hermes/matrix/ (keys, sync token, device ID).
Credentials from ~/.hermes/matrix_credentials.json.
"""
import asyncio, json, os, sys

from nio import (
    AsyncClient, AsyncClientConfig, RoomCreateResponse,
    RoomSendResponse, JoinedRoomsResponse, RoomInviteResponse,
    JoinResponse, SyncResponse, LoginResponse,
)

STORE_DIR = os.path.join(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")), "matrix")
CREDS_FILE = os.path.join(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")), "matrix_credentials.json")
SYNC_TOKEN_FILE = os.path.join(STORE_DIR, "sync_token")


def load_creds():
    with open(CREDS_FILE) as f:
        return json.load(f)


def save_sync_token(token):
    with open(SYNC_TOKEN_FILE, "w") as f:
        f.write(token)


def load_sync_token():
    if os.path.exists(SYNC_TOKEN_FILE):
        with open(SYNC_TOKEN_FILE) as f:
            return f.read().strip()
    return None


async def make_client():
    os.makedirs(STORE_DIR, exist_ok=True)
    creds = load_creds()
    config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=False)
    client = AsyncClient(creds["homeserver"], creds["user_id"], config=config)
    client.restore_login(creds["user_id"], creds.get("device_id", ""), creds["access_token"])
    return client


async def cmd_sync():
    client = await make_client()
    since = load_sync_token()
    resp = await client.sync(timeout=5000, since=since, full_state=False)
    assert isinstance(resp, SyncResponse), f"sync failed: {resp}"
    save_sync_token(resp.next_batch)

    messages = []
    for room_id, room in resp.rooms.join.items():
        for event in room.timeline.events:
            if hasattr(event, "body"):
                messages.append({
                    "room_id": room_id,
                    "sender": event.sender,
                    "body": event.body,
                    "timestamp": event.server_timestamp,
                })
    print(json.dumps(messages, indent=2))
    await client.close()


async def cmd_send(room_id, body):
    client = await make_client()
    resp = await client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": body},
    )
    assert isinstance(resp, RoomSendResponse), f"send failed: {resp}"
    print(json.dumps({"event_id": resp.event_id}))
    await client.close()


async def cmd_rooms():
    client = await make_client()
    resp = await client.joined_rooms()
    assert isinstance(resp, JoinedRoomsResponse), f"rooms failed: {resp}"
    print(json.dumps({"rooms": resp.rooms}, indent=2))
    await client.close()


async def cmd_create(name, invites):
    client = await make_client()
    resp = await client.room_create(name=name)
    assert isinstance(resp, RoomCreateResponse), f"create failed: {resp}"
    for user_id in (invites or []):
        await client.room_invite(resp.room_id, user_id)
    print(json.dumps({"room_id": resp.room_id}))
    await client.close()


async def cmd_invite(room_id, user_id):
    client = await make_client()
    resp = await client.room_invite(room_id, user_id)
    assert isinstance(resp, RoomInviteResponse), f"invite failed: {resp}"
    print(json.dumps({"invited": user_id, "room_id": room_id}))
    await client.close()


async def cmd_join(room_id):
    client = await make_client()
    resp = await client.join(room_id)
    assert isinstance(resp, JoinResponse), f"join failed: {resp}"
    print(json.dumps({"joined": resp.room_id}))
    await client.close()


async def cmd_status():
    client = await make_client()
    sync_token = load_sync_token()
    print(json.dumps({
        "user_id": client.user_id,
        "homeserver": client.homeserver.geturl() if hasattr(client.homeserver, 'geturl') else str(client.homeserver),
        "device_id": client.device_id,
        "sync_token": sync_token[:20] + "..." if sync_token else None,
        "store_dir": STORE_DIR,
    }, indent=2))
    await client.close()


COMMANDS = {
    "sync": lambda args: cmd_sync(),
    "send": lambda args: cmd_send(args[0], args[1]),
    "rooms": lambda args: cmd_rooms(),
    "create": lambda args: cmd_create(args[0], args[1:]),
    "invite": lambda args: cmd_invite(args[0], args[1]),
    "join": lambda args: cmd_join(args[0]),
    "status": lambda args: cmd_status(),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    asyncio.run(COMMANDS[sys.argv[1]](sys.argv[2:]))
