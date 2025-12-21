#!/usr/bin/env bash
set -euo pipefail

# Usage: ./utils/diamond/verify_contract.sh <contracts.txt> <chainId>
# contracts.txt format: "<Name> <Address>" per line. Lines with "null" are skipped.

if [ $# -lt 2 ]; then
  echo "Usage: $0 <contracts.txt> <chainId>"
  exit 1
fi

INPUT_FILE="$1"
CHAIN_ID="$2"

# --- load .env ---
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi
: "${ETHERSCAN_API_KEY:?Missing ETHERSCAN_API_KEY in environment or .env}"

# --- deps check ---
for cmd in curl jq forge awk; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Error: $cmd not found"; exit 1; }
done

# --- fetch chainlist (robustly) ---
CHAINLIST_URL="https://api.etherscan.io/v2/chainlist"
RAW="$(curl -fsSL --retry 3 --retry-delay 1 "$CHAINLIST_URL" || true)"

# If response is empty or not JSON, bail to default
if [[ -z "${RAW}" ]] || ! jq -e . >/dev/null 2>&1 <<<"$RAW"; then
  RAW="{}"
fi

# Some responses may not have .chains; make everything optional & safe.
VERIFIER_BASE="$(
  jq -r --arg id "$CHAIN_ID" '
    # Prefer arrays when present; otherwise empty array to avoid null iteration.
    ( .chains // [] )
    | map(select((.chainId|tostring)==($id|tostring)))
    | .[0] // {}
    | (
        .apiURLv2 // .apiV2 // .apiURL // .apiUrl // .verifierURL // .verifierUrl // .api // (.apis[0]?.url)
      )
  ' <<<"$RAW" 2>/dev/null || true
)"

# Fallbacks:
# 1) If unresolved/null/empty, use the canonical v2 base (works for all supported chains when --chain-id is passed)
if [[ -z "${VERIFIER_BASE:-}" || "${VERIFIER_BASE}" == "null" ]]; then
  VERIFIER_BASE="https://api.etherscan.io/v2/api"
fi
# 2) Strip query params just in case (forge will add chainId itself)
VERIFIER_BASE="${VERIFIER_BASE%%\?*}"

echo "Using verifier base URL: $VERIFIER_BASE"
echo "Using chain id: $CHAIN_ID"

# --- verify loop ---
# Skips: empty lines, comments, and lines where Name == "null"
while IFS= read -r LINE; do
  # trim whitespace
  LINE="${LINE#"${LINE%%[![:space:]]*}"}"
  LINE="${LINE%"${LINE##*[![:space:]]}"}"
  [[ -z "$LINE" ]] && continue
  [[ "${LINE:0:1}" == "#" ]] && continue

  # split into two fields: name and address (space-separated)
  NAME=$(awk '{print $1}' <<<"$LINE")
  ADDR=$(awk '{print $2}' <<<"$LINE")

  if [[ -z "${NAME:-}" || -z "${ADDR:-}" ]]; then
    echo "Skipping malformed line: '$LINE'"
    continue
  fi
  [[ "$NAME" == "null" ]] && continue

  echo "Verifying $NAME at $ADDR"
  forge verify-contract "$ADDR" "$NAME" \
    --verifier etherscan \
    --verifier-url "$VERIFIER_BASE" \
    --chain-id "$CHAIN_ID" \
    --etherscan-api-key "$ETHERSCAN_API_KEY" \
    --watch \
  || { echo "❗ Verification failed for $NAME $ADDR (continuing)"; continue; }
done < "$INPUT_FILE"

echo "✅ Done."
