#!/bin/sh
set -eu

# Model eConsoleAppContainer: it waits for EOF on the command's output pipe.
# A background watchdog must not inherit that pipe, or appClosed never fires.
pid_file="$(mktemp)"
trap 'if [ -s "$pid_file" ]; then kill "$(cat "$pid_file")" 2>/dev/null || true; fi; rm -f "$pid_file"' EXIT

started="$(date +%s)"
result="$({
    (sleep 30) </dev/null >/dev/null 2>&1 &
    echo $! > "$pid_file"
    echo "E2XRAY_ACTION=STARTED"
})"
elapsed="$(($(date +%s) - started))"

[ "$result" = "E2XRAY_ACTION=STARTED" ]
[ "$elapsed" -lt 3 ]

grep -F ') </dev/null >/dev/null 2>&1 &' \
    "$(dirname "$0")/../usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh" \
    >/dev/null

echo "Watchdog detach test passed."
