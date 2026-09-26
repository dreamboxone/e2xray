#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CTL="$ROOT/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

mkdir -p "$TEST_ROOT/bin"
RULES="$TEST_ROOT/rules"
: > "$RULES"

cat > "$TEST_ROOT/bin/iptables" <<'FAKE_IPT'
#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_IPT_RULES"
exit 0
FAKE_IPT
chmod 755 "$TEST_ROOT/bin/iptables"

cat > "$TEST_ROOT/bin/ip" <<'FAKE_IP'
#!/bin/sh
# `rule del` must report "nothing left to delete" so the drain loops terminate.
case "$*" in
    "rule del"*) exit 2 ;;
esac
exit 0
FAKE_IP
chmod 755 "$TEST_ROOT/bin/ip"

export FAKE_IPT_RULES="$RULES" PATH="$TEST_ROOT/bin:$PATH"

LOG="$TEST_ROOT/e2xray.log"
BACKEND_ERROR="$TEST_ROOT/backend-error"
TPROXY_TABLE=102
TPROXY_MARK=0x2333
TPROXY_PRIORITY=1002
TPROXY_PORT=12345
TPROXY_CHAIN=E2XRAY_TP
TPROXY_MASK_CHAIN=E2XRAY_MASK
REDIRECT_CHAIN=E2XRAY_RD
DNS_CHAIN=E2XRAY_DNS
DNS_PORT=15353
SELF_MARK=0xff
SERVER_IPS=203.0.113.10

log() {
    echo "$*" >> "$LOG"
}

set_backend_error() {
    code="$1"
    shift
    printf '%s|%s\n' "$code" "$*" > "$BACKEND_ERROR"
}

clear_backend_error() {
    rm -f "$BACKEND_ERROR"
}

run_ip() {
    ip "$@"
}

# Load only the transparent-backend functions, without running any action.
sed -n '/^run_iptables()/,/^cleanup_network_backend()/p' "$CTL" |
    sed '$d' > "$TEST_ROOT/functions.sh"
. "$TEST_ROOT/functions.sh"

rule_line() {
    grep -n -- "$1" "$RULES" | head -n 1 | cut -d: -f1
}

assert_rule() {
    grep -q -- "$1" "$RULES" || {
        echo "Missing rule: $1" >&2
        exit 1
    }
}

# --- REDIRECT -------------------------------------------------------------
: > "$RULES"
setup_redirect

assert_rule "-t nat -A $REDIRECT_CHAIN -m mark --mark $SELF_MARK -j RETURN"
assert_rule "-t nat -A $DNS_CHAIN -m mark --mark $SELF_MARK -j RETURN"
assert_rule "-t nat -A $DNS_CHAIN -p udp --dport 53 -j REDIRECT --to-ports $DNS_PORT"
assert_rule "-t nat -A $DNS_CHAIN -p tcp --dport 53 -j REDIRECT --to-ports $DNS_PORT"
assert_rule "-t nat -A $REDIRECT_CHAIN -d 203.0.113.10/32 -j RETURN"
assert_rule "-t nat -A OUTPUT -p tcp -j $REDIRECT_CHAIN"

# DNS must be claimed before the catch-all TCP redirect, otherwise port 53
# is swallowed by the transparent chain and never reaches dns-in.
dns_attach="$(rule_line "-t nat -A OUTPUT -j $DNS_CHAIN")"
redirect_attach="$(rule_line "-t nat -A OUTPUT -p tcp -j $REDIRECT_CHAIN")"
[ "$dns_attach" -lt "$redirect_attach" ] || {
    echo "DNS chain must be attached to nat OUTPUT before the redirect chain." >&2
    exit 1
}

# The self-mark bypass must precede every capturing rule in its chain.
mark_bypass="$(rule_line "-t nat -A $REDIRECT_CHAIN -m mark --mark $SELF_MARK -j RETURN")"
capture="$(rule_line "-t nat -A $REDIRECT_CHAIN -p tcp -j REDIRECT")"
[ "$mark_bypass" -lt "$capture" ] || {
    echo "Self-mark bypass must precede the REDIRECT target." >&2
    exit 1
}

# --- TPROXY ---------------------------------------------------------------
: > "$RULES"
setup_tproxy

assert_rule "-t mangle -A $TPROXY_MASK_CHAIN -m mark --mark $SELF_MARK -j RETURN"
assert_rule "-t mangle -A $TPROXY_MASK_CHAIN -p udp --dport 53 -j RETURN"
assert_rule "-t mangle -A $TPROXY_MASK_CHAIN -p tcp --dport 53 -j RETURN"
assert_rule "-t mangle -A $TPROXY_MASK_CHAIN -j MARK --set-mark $TPROXY_MARK"
assert_rule "-t mangle -A PREROUTING -m mark --mark $TPROXY_MARK -j $TPROXY_CHAIN"
assert_rule "-t nat -A $DNS_CHAIN -p udp --dport 53 -j REDIRECT --to-ports $DNS_PORT"

dns_return="$(rule_line "-t mangle -A $TPROXY_MASK_CHAIN -p udp --dport 53 -j RETURN")"
set_mark="$(rule_line "-t mangle -A $TPROXY_MASK_CHAIN -j MARK --set-mark $TPROXY_MARK")"
[ "$dns_return" -lt "$set_mark" ] || {
    echo "Port 53 must return before the TPROXY mark is set." >&2
    exit 1
}

# --- cleanup --------------------------------------------------------------
: > "$RULES"
cleanup_redirect
assert_rule "-t nat -D OUTPUT -j $DNS_CHAIN"
assert_rule "-t nat -X $REDIRECT_CHAIN"

: > "$RULES"
cleanup_tproxy
assert_rule "-t nat -X $DNS_CHAIN"
assert_rule "-t mangle -X $TPROXY_CHAIN"

echo "Transparent backend tests passed."
