#!/bin/bash
# Matrix UX tricks — exercise flows between agent, TEE, and Element mobile
# Usage: ./tricks.sh <trick_name>

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SCRIPT_DIR/.env" ] && source "$SCRIPT_DIR/.env"

HS="${MATRIX_HOMESERVER:?Set MATRIX_HOMESERVER in .env}"
CHALLENGE="${CHALLENGE_URL:?Set CHALLENGE_URL in .env}"
BOT_TOKEN="${BOT_ACCESS_TOKEN:?Set BOT_ACCESS_TOKEN in .env}"
USER="${INVITE_USER:-@socrates1024:matrix.org}"

send() {
  local room=$1 msg=$2
  local txn=$(date +%s%N)
  curl -s -X PUT "$HS/_matrix/client/v3/rooms/$room/send/m.room.message/$txn" \
    -H "Authorization: Bearer $BOT_TOKEN" -H 'Content-Type: application/json' \
    -d "{\"msgtype\":\"m.text\",\"body\":$(echo "$msg" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')}"
}

create_and_invite() {
  local name=$1
  local room_id=$(curl -s -X POST "$HS/_matrix/client/v3/createRoom" \
    -H "Authorization: Bearer $BOT_TOKEN" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['room_id'])")
  curl -s -X POST "$HS/_matrix/client/v3/rooms/$room_id/invite" \
    -H "Authorization: Bearer $BOT_TOKEN" -H 'Content-Type: application/json' \
    -d "{\"user_id\":\"$USER\"}" > /dev/null
  echo "$room_id"
}

case "$1" in

  # Trick 1: Simple DM — bot creates room, invites you, sends a message
  dm)
    echo "Creating DM room..."
    ROOM=$(create_and_invite "🪶 hermes DM")
    send "$ROOM" "Hey — your agent is online and connected to the hermes notebook. Ask me anything."
    echo "Sent to $ROOM — check Element"
    ;;

  # Trick 2: Notebook digest — summarize recent notebook entries, send as a message
  digest)
    echo "Fetching notebook entries..."
    DIGEST=$(python3 -c "
import aiohttp, asyncio

async def go():
    async with aiohttp.ClientSession() as s:
        async with s.get('https://hermes.teleport.computer/api/entries?limit=10') as resp:
            data = await resp.json(content_type=None)
            lines = []
            for e in data.get('entries', []):
                author = e.get('handle', e.get('pseudonym', '?'))
                content = e.get('content', '').strip()
                hints = e.get('topicHints', [])
                if content:
                    lines.append(f'• {author}: {content[:120]}')
                elif hints:
                    lines.append(f'• {author}: (posted about: {\", \".join(hints)})')
            print('\n'.join(lines[:8]))

asyncio.run(go())
")
    ROOM=$(create_and_invite "📓 Notebook Digest")
    send "$ROOM" "Here's what's happening on the hermes notebook:

$DIGEST"
    echo "Digest sent — check Element"
    ;;

  # Trick 3: Topic room — create a room around a specific topic
  topic)
    TOPIC="${2:-trust-and-identity}"
    echo "Creating topic room: $TOPIC"
    ROOM=$(create_and_invite "🧵 $TOPIC")
    send "$ROOM" "I noticed several notebook entries related to $TOPIC. Created this room to collect thoughts and track developments."
    echo "Topic room $ROOM created — check Element"
    ;;

  # Trick 4: Ping — simple alive check, sends a one-liner
  ping)
    # Use the most recent DM room or create one
    ROOMS=$(curl -s "$HS/_matrix/client/v3/joined_rooms" -H "Authorization: Bearer $BOT_TOKEN" \
      | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin)['joined_rooms']))")
    ROOM=$(echo "$ROOMS" | head -1)
    if [ -z "$ROOM" ]; then
      ROOM=$(create_and_invite "🪶 hermes DM")
    fi
    send "$ROOM" "🪶 ping — $(date '+%H:%M %Z')"
    echo "Pinged $ROOM"
    ;;

  # Trick 5: Challenge preview — show what a reverse CAPTCHA looks like
  challenge)
    echo "Fetching challenge..."
    curl -s "$CHALLENGE/challenge" | python3 -m json.tool
    ;;

  *)
    echo "Usage: ./tricks.sh {dm|digest|topic [name]|ping|challenge}"
    echo ""
    echo "  dm        — create a DM room, send greeting"
    echo "  digest    — fetch notebook, send summary to new room"
    echo "  topic X   — create a topic room around X"
    echo "  ping      — send a quick ping to first joined room"
    echo "  challenge — preview a reverse CAPTCHA challenge"
    ;;
esac
