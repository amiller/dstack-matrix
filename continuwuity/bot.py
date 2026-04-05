import asyncio, sys, json
from nio import AsyncClient, RoomCreateResponse, RoomInviteResponse

async def main():
    homeserver = sys.argv[1]
    user_id = sys.argv[2]
    access_token = sys.argv[3]
    invite_target = sys.argv[4] if len(sys.argv) > 4 else "@socrates1024:matrix.org"
    message = sys.argv[5] if len(sys.argv) > 5 else "Hello from hermes-bot! This is a test invitation."

    client = AsyncClient(homeserver, user_id)
    client.access_token = access_token

    resp = await client.room_create(
        name="Hermes Bot Test",
        topic="Automated test room from hermes-bot",
        invite=[invite_target],
    )
    assert isinstance(resp, RoomCreateResponse), f"room creation failed: {resp}"
    print(f"Created room: {resp.room_id}")

    await client.room_send(
        room_id=resp.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": message},
    )
    print(f"Sent message, invited {invite_target}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
