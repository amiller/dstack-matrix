#!/bin/bash
# Usage: onboard.sh <username>
# Fetches challenge, prints challenge JSON + a pre-generated password.
# The agent only needs to solve the code and submit.
set -e
CHALLENGE_URL="https://a8629a1195ecb53afe1700cd3bafda1d18d9635d-8080.dstack-pha-prod7.phala.network"
CREDS_FILE="${HERMES_HOME:-$HOME/.hermes}/matrix_credentials.json"
USERNAME="${1:-hermes-agent-$$}"
PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 32)

if [ -f "$CREDS_FILE" ]; then
  echo "Already registered. Credentials at $CREDS_FILE"
  cat "$CREDS_FILE"
  exit 0
fi

CHALLENGE=$(curl -sf "$CHALLENGE_URL/challenge")
echo "CHALLENGE: $CHALLENGE"
echo "USERNAME: $USERNAME"
echo "PASSWORD: $PASSWORD"
echo "SUBMIT_URL: $CHALLENGE_URL/solve"
echo "CREDS_FILE: $CREDS_FILE"
