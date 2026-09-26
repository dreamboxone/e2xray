#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CTL="$PROJECT_DIR/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

export E2XRAY_RUNTIME="$TEST_ROOT/run"
mkdir -p "$E2XRAY_RUNTIME"
export BACKEND_ERROR="$E2XRAY_RUNTIME/backend-error"

mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/sysctl/all" "$TEST_ROOT/sysctl/eth0"
printf '1\n' > "$TEST_ROOT/sysctl/all/rp_filter"
printf '1\n' > "$TEST_ROOT/sysctl/eth0/rp_filter"

cat > "$TEST_ROOT/bin/ip" <<'FAKE_IP'
#!/bin/sh
set -u
printf '%s\n' "$*" >> "$FAKE_IP_ROOT/commands"

case "$*" in
    "rule show")
        [ "$FAKE_POLICY" = 1 ] || { echo "ip: invalid argument 'rule'" >&2; exit 1; }
        [ -f "$FAKE_IP_ROOT/rule" ] && echo "1001: from all lookup 101"
        ;;
    "rule add priority 1001 from all lookup 101")
        [ "$FAKE_POLICY" = 1 ] || exit 1
        : > "$FAKE_IP_ROOT/rule"
        ;;
    "rule del priority 1001 from all lookup 101")
        if [ -f "$FAKE_IP_ROOT/rule" ]; then
            rm -f "$FAKE_IP_ROOT/rule"
        else
            exit 1
        fi
        ;;
    "route show table main")
        echo "192.168.1.0/24 dev eth0"
        echo "default via 192.168.1.1 dev eth0"
        ;;
    "route show table 101")
        [ "$FAKE_POLICY" = 1 ] || exit 1
        [ -f "$FAKE_IP_ROOT/table-default" ] && echo "default dev e2xray0"
        ;;
    "route replace table 101 default dev e2xray0")
        : > "$FAKE_IP_ROOT/table-default"
        ;;
    "route flush table 101")
        rm -f "$FAKE_IP_ROOT/table-default"
        ;;
    "route add 0.0.0.0/1 dev e2xray0")
        if [ -f "$FAKE_IP_ROOT/split-low" ]; then
            echo "RTNETLINK answers: File exists" >&2
            exit 2
        fi
        : > "$FAKE_IP_ROOT/split-low"
        ;;
    "route add 128.0.0.0/1 dev e2xray0")
        : > "$FAKE_IP_ROOT/split-high"
        ;;
    "route del 0.0.0.0/1")
        rm -f "$FAKE_IP_ROOT/split-low"
        ;;
    "route del 128.0.0.0/1")
        rm -f "$FAKE_IP_ROOT/split-high"
        ;;
    "route show")
        [ -f "$FAKE_IP_ROOT/split-low" ] && echo "0.0.0.0/1 dev e2xray0"
        [ -f "$FAKE_IP_ROOT/split-high" ] && echo "128.0.0.0/1 dev e2xray0"
        ;;
    "rule del "*) exit 1 ;;
    *) ;;
esac
exit 0
FAKE_IP
chmod 755 "$TEST_ROOT/bin/ip"

IFACE=e2xray0
TUN_ADDR=10.255.0.1/30
TABLE=101
BYPASS_TABLE=103
BYPASS_PRIORITY=1000
BYPASS_MARK=0x2334
SELF_BYPASS_PRIORITY=999
SELF_MARK=0xff
CLOSED_METRIC=1000
STATE="$TEST_ROOT/state"
ROUTE_ERROR="$TEST_ROOT/route-error"
BACKEND_ERROR="$TEST_ROOT/backend-error"
POLICY_TABLE_OWNED="$TEST_ROOT/policy-table-owned"
POLICY_RULE_OWNED="$TEST_ROOT/policy-rule-owned"
SPLIT_ROUTES_OWNED="$TEST_ROOT/split-routes-owned"
LOG="$TEST_ROOT/e2xray.log"
SYSCTL_IPV4="$TEST_ROOT/sysctl"
DEFAULT_DEV=eth0
DEFAULT_GW=192.168.1.1
SERVER_IPS=203.0.113.10
RP_FILTER_ALL=1
RP_FILTER_DEV=1
export FAKE_IP_ROOT="$TEST_ROOT" PATH="$TEST_ROOT/bin:$PATH"

log() {
    echo "$*" >> "$LOG"
}

# Load only the routing functions, without executing the controller action.
sed -n '/^run_ip()/,/^is_running()/p' "$CTL" | sed '$d' > "$TEST_ROOT/functions.sh"
. "$TEST_ROOT/functions.sh"

write_state() {
    cat > "$STATE" <<EOF
DEFAULT_DEV='$DEFAULT_DEV'
DEFAULT_GW='$DEFAULT_GW'
SERVER_IPS='$SERVER_IPS'
RP_FILTER_ALL='$RP_FILTER_ALL'
RP_FILTER_DEV='$RP_FILTER_DEV'
EOF
}

write_state
export FAKE_POLICY=1
setup_routes
routes_ready
. "$STATE"
[ "$ROUTE_MODE" = policy ]
restore_routes
[ ! -e "$TEST_ROOT/rule" ]
[ ! -e "$TEST_ROOT/table-default" ]

# An administrator-owned priority 1001 rule must force fallback and survive
# both setup and cleanup.
write_state
: > "$TEST_ROOT/rule"
export FAKE_POLICY=1
setup_routes
. "$STATE"
[ "$ROUTE_MODE" = split ]
restore_routes
[ -e "$TEST_ROOT/rule" ]
rm -f "$TEST_ROOT/rule"

write_state
export FAKE_POLICY=0
setup_routes
routes_ready
. "$STATE"
[ "$ROUTE_MODE" = split ]
[ -e "$TEST_ROOT/split-low" ]
[ -e "$TEST_ROOT/split-high" ]
restore_routes
[ ! -e "$TEST_ROOT/split-low" ]
[ ! -e "$TEST_ROOT/split-high" ]

# If a split route already belongs to the receiver, setup must fail without
# claiming or deleting that existing route during rollback.
write_state
: > "$TEST_ROOT/split-low"
if setup_routes; then
    echo "Expected split-route collision to fail." >&2
    exit 1
fi
restore_routes
[ -e "$TEST_ROOT/split-low" ]
rm -f "$TEST_ROOT/split-low"

grep -q 'Policy routing is unavailable or failed' "$LOG"
grep -q 'TUN routing mode: split default routes' "$LOG"
echo "Routing tests passed."
