#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CTL="$ROOT/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

RESOLV="$TEST_ROOT/resolv.conf"
RESOLV_BAK="$TEST_ROOT/resolv.conf.bak"
LOG="$TEST_ROOT/e2xray.log"
DNS1="8.8.8.8"
DNS2="1.1.1.1"

log() {
    echo "$*" >> "$LOG"
}

sed -n '/^setup_dns()/,/^run_ip()/p' "$CTL" | sed '$d' > "$TEST_ROOT/functions.sh"
. "$TEST_ROOT/functions.sh"

printf 'nameserver 192.168.1.1\n' > "$RESOLV"
cp "$RESOLV" "$TEST_ROOT/original"
PROTOCOL=shadowsocks
setup_dns
cmp "$RESOLV" "$TEST_ROOT/original"
[ -f "$RESOLV_BAK" ]
grep -q 'preserving system resolver' "$LOG"
restore_dns
cmp "$RESOLV" "$TEST_ROOT/original"
[ ! -e "$RESOLV_BAK" ]

PROTOCOL=vless
setup_dns
cat > "$TEST_ROOT/expected" <<EOF
nameserver $DNS1
nameserver $DNS2
EOF
cmp "$RESOLV" "$TEST_ROOT/expected"
restore_dns
cmp "$RESOLV" "$TEST_ROOT/original"
[ ! -e "$RESOLV_BAK" ]

echo "DNS tests passed."
