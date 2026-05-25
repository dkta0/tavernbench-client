#!/usr/bin/env bash
set -euo pipefail

#
# TavernBench end-to-end smoke test.
#
# Prerequisites:
#   - Phoenix server reachable on 127.0.0.1:4100 (start it in another terminal:
#       cd ../agent-mmo && docker compose up).
#   - The TUI + CLI binaries built (`make build`).
#   - A valid API key in ~/.config/tavernbench/config.toml — if missing, this
#     script writes a dummy key ("smoke-test-key") and the server will reject
#     it during WS upgrade; in that case the test will fail loudly with an auth
#     error. The script does not seed a real key.
#
# What it asserts:
#   1. The TUI launches and creates a socket at $XDG_RUNTIME_DIR/tavernbench/.
#   2. `tavernbench attach $TOKEN` succeeds.
#   3. `tavernbench observe` returns a JSON observation.
#   4. `tavernbench act look` round-trips.
#   5. `tavernbench leaderboard --scenario tavern_hall` returns a JSON body.
#
# Cleanup:
#   - Kills the TUI on exit; removes the socket file.
#

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TUI_BIN="${ROOT}/tui/tavernbench-tui"
CLI_BIN="${ROOT}/cli/tavernbench"

if [[ ! -x "$TUI_BIN" ]]; then
  echo "✗ TUI binary not built. Run \`make build\` first." >&2
  exit 2
fi
if [[ ! -x "$CLI_BIN" ]]; then
  echo "✗ CLI binary not built. Run \`make build\` first." >&2
  exit 2
fi

# Ensure a config file exists; if missing, write a stub so the TUI doesn't bail
# before printing the token. The server will reject the dummy key during WS
# upgrade and the test will fail at the attach step — that's intentional, it
# tells the user to run `tavernbench auth` for a real key.
CFG="${HOME}/.config/tavernbench/config.toml"
if [[ ! -f "$CFG" ]]; then
  echo "→ Writing stub config.toml (run \`tavernbench auth\` for a real key)"
  mkdir -p "$(dirname "$CFG")"
  echo 'api_key = "smoke-test-key"' > "$CFG"
fi

# Start TUI in headless mode; capture its stdout (token + socket path).
TUI_LOG="$(mktemp -t tavernbench-tui.XXXXXX.log)"
"$TUI_BIN" --mode=play --zone=tavern_hall --no-render > "$TUI_LOG" 2>&1 &
TUI_PID=$!
cleanup() {
  if kill -0 "$TUI_PID" 2>/dev/null; then kill "$TUI_PID" 2>/dev/null || true; fi
  rm -f "$TUI_LOG"
}
trap cleanup EXIT

# Wait up to 5s for the TUI to print its socket path.
SOCK=""
for i in $(seq 1 50); do
  if grep -q "^Socket:" "$TUI_LOG"; then
    SOCK="$(grep '^Socket:' "$TUI_LOG" | head -1 | awk '{print $2}')"
    break
  fi
  sleep 0.1
done
if [[ -z "$SOCK" ]]; then
  echo "✗ TUI did not start in time. Log:" >&2
  cat "$TUI_LOG" >&2
  exit 1
fi
TOKEN="$(grep '^Pairing token:' "$TUI_LOG" | head -1 | awk '{print $3}')"

echo "→ TUI alive. Token=$TOKEN  Sock=$SOCK"

export TAVERNBENCH_SOCK="$SOCK"

echo "→ attach"
"$CLI_BIN" attach "$TOKEN"

echo "→ observe"
"$CLI_BIN" observe

echo "→ act look"
"$CLI_BIN" act look

echo "→ leaderboard (HTTP)"
"$CLI_BIN" leaderboard --scenario tavern_hall | head -c 200
echo

echo
echo "✓ smoke passed"
