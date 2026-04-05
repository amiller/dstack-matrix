#!/bin/bash
HS="https://e8a1d263d8104b67a36adf94995786766096a3d2-8008.dstack-pha-prod7.phala.network"
ROOM="!QsqBmHStTzHjrSmzWg:dstack-matrix"

if [ -z "$MATRIX_TOKEN" ]; then
  read -p "Username: " USER
  read -sp "Password: " PASS; echo
  MATRIX_TOKEN=$(curl -s -X POST "$HS/_matrix/client/v3/login" \
    -H 'Content-Type: application/json' \
    -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"$USER\"},\"password\":\"$PASS\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  export MATRIX_TOKEN
  echo "Logged in. Token exported as MATRIX_TOKEN"
fi

case "${1:-}" in
  send)
    shift
    MSG="$*"
    TXN=$(date +%s%N)
    curl -s -X PUT "$HS/_matrix/client/v3/rooms/$ROOM/send/m.room.message/$TXN" \
      -H "Authorization: Bearer $MATRIX_TOKEN" \
      -H 'Content-Type: application/json' \
      -d "{\"msgtype\":\"m.text\",\"body\":\"$MSG\"}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Sent:', d.get('event_id','error'))"
    ;;
  read)
    curl -s "$HS/_matrix/client/v3/rooms/$ROOM/messages?dir=b&limit=${2:-10}" \
      -H "Authorization: Bearer $MATRIX_TOKEN" \
      | python3 -c "
import sys,json
data=json.load(sys.stdin)
for e in reversed(data.get('chunk',[])):
    c=e.get('content',{})
    if c.get('msgtype')=='m.text':
        print(f'{e[\"sender\"]}: {c[\"body\"]}')
"
    ;;
  *)
    echo "Usage: $0 {send <message>|read [count]}"
    echo "Set MATRIX_TOKEN env var to skip login"
    ;;
esac
