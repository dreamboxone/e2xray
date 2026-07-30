#!/bin/sh
set -u

BASE="/usr/lib/enigma2/python/Plugins/Extensions/e2xray"
XRAY="/usr/lib/e2xray/bin/xray"
CONF="/etc/e2xray/config.json"
USERCONF="/root/config.txt"
PARSER="$BASE/proxy_config.py"
RUNTIME="/var/run/e2xray"
PARSED_USERCONF="$RUNTIME/user.conf"
PIDFILE="$RUNTIME/xray.pid"
STATE="$RUNTIME/state"
LOG="/tmp/e2xray.log"
RESOLV="/etc/resolv.conf"
RESOLV_BAK="$RUNTIME/resolv.conf.bak"
IFACE="e2xray0"
TUN_ADDR="10.255.0.1/30"
TABLE="101"
ARVAN="https://www.arvancloud.ir"
CLOUDFLARE="https://dash.cloudflare.com"
DNS1="8.8.8.8"
DNS2="1.1.1.1"

mkdir -p "$RUNTIME" /etc/e2xray

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
}

load_userconf() {
    PROTOCOL=""
    SERVER_ADDRESS=""
    SERVER_PORT=""
    DNS1="8.8.8.8"
    DNS2="1.1.1.1"

    [ -f "$USERCONF" ] || return 1
    [ -f "$PARSER" ] || return 1

    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    elif command -v python >/dev/null 2>&1; then
        PYTHON=python
    else
        return 1
    fi

    rm -f "$PARSED_USERCONF"
    "$PYTHON" "$PARSER" "$USERCONF" "$PARSED_USERCONF" "$CONF" >> "$LOG" 2>&1 ||
        return 1
    . "$PARSED_USERCONF"
}

http_check() {
    url="$1"
    if command -v wget >/dev/null 2>&1; then
        wget -q --spider --no-check-certificate -T 8 "$url" >/dev/null 2>&1
        [ $? -eq 0 ] && return 0
    fi
    if command -v curl >/dev/null 2>&1; then
        curl -k -L --max-time 8 -I "$url" >/dev/null 2>&1
        [ $? -eq 0 ] && return 0
    fi
    host="$(echo "$url" | sed 's#https://##;s#/.*##')"
    ping -c 1 -W 4 "$host" >/dev/null 2>&1
}

internet_status() {
    if ! http_check "$ARVAN"; then
        echo "E2XRAY_NET=OFFLINE"
        return 0
    fi
    if http_check "$CLOUDFLARE"; then
        echo "E2XRAY_NET=ONLINE"
        return 0
    fi
    echo "E2XRAY_NET=NATIONAL"
}

config_present() {
    [ -f "$USERCONF" ] || return 1
    load_userconf || return 1
    [ -n "${PROTOCOL:-}" ] || return 1
    [ -n "${SERVER_ADDRESS:-}" ] || return 1
    [ -n "${SERVER_PORT:-}" ] || return 1
    return 0
}

ping_config() {
    if ! config_present; then
        echo "E2XRAY_CONFIG_PING=NO_CONFIG"
        return 0
    fi
    if ping -c 1 -W 4 "$SERVER_ADDRESS" >/dev/null 2>&1; then
        echo "E2XRAY_CONFIG_PING=OK"
    else
        echo "E2XRAY_CONFIG_PING=FAILED"
    fi
}

find_default() {
    ip route show default 2>/dev/null | sed -n '1p'
}

default_dev() {
    find_default | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}'
}

default_gw() {
    find_default | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}'
}

resolve_server_ips() {
    host="$1"
    case "$host" in
        *[!0-9.]*)
            if command -v getent >/dev/null 2>&1; then
                getent ahostsv4 "$host" 2>/dev/null | awk '{print $1}' | sort -u
            elif command -v nslookup >/dev/null 2>&1; then
                nslookup "$host" 2>/dev/null | awk '/^Address[ 0-9]*: / {print $NF}' | grep -E '^[0-9]+\.' | sort -u
            else
                ping -c 1 -W 4 "$host" 2>/dev/null | sed -n '1s/.*(\([0-9.]*\)).*/\1/p'
            fi
            ;;
        *)
            echo "$host"
            ;;
    esac
}

write_config() {
    load_userconf || return 1
    [ -s "$CONF" ] || return 1
    echo "$PROTOCOL config written: $CONF"
}

save_state() {
    load_userconf || return 1
    route="$(find_default)"
    dev="$(default_dev)"
    gw="$(default_gw)"
    server_ips="$(resolve_server_ips "${SERVER_ADDRESS:-}" | tr '\n' ' ')"
    rp_all="$(cat /proc/sys/net/ipv4/conf/all/rp_filter 2>/dev/null || echo '')"
    rp_dev="$(cat "/proc/sys/net/ipv4/conf/$dev/rp_filter" 2>/dev/null || echo '')"
    {
        echo "DEFAULT_ROUTE='$route'"
        echo "DEFAULT_DEV='$dev'"
        echo "DEFAULT_GW='$gw'"
        echo "SERVER_IPS='$server_ips'"
        echo "RP_FILTER_ALL='$rp_all'"
        echo "RP_FILTER_DEV='$rp_dev'"
    } > "$STATE"
}

setup_dns() {
    [ -f "$RESOLV" ] && [ ! -f "$RESOLV_BAK" ] && cp "$RESOLV" "$RESOLV_BAK"
    {
        echo "nameserver $DNS1"
        echo "nameserver $DNS2"
    } > "$RESOLV"
}

restore_dns() {
    if [ -f "$RESOLV_BAK" ]; then
        cp "$RESOLV_BAK" "$RESOLV"
        rm -f "$RESOLV_BAK"
    fi
}

setup_routes() {
    . "$STATE"
    [ -w /proc/sys/net/ipv4/conf/all/rp_filter ] && echo 0 > /proc/sys/net/ipv4/conf/all/rp_filter
    [ -n "${DEFAULT_DEV:-}" ] && [ -w "/proc/sys/net/ipv4/conf/$DEFAULT_DEV/rp_filter" ] &&
        echo 0 > "/proc/sys/net/ipv4/conf/$DEFAULT_DEV/rp_filter"
    ip link set "$IFACE" up 2>/dev/null || true
    ip addr add "$TUN_ADDR" dev "$IFACE" 2>/dev/null || true
    ip route show table main 2>/dev/null | while IFS= read -r route; do
        case "$route" in
            default*) ;;
            *) ip route replace table "$TABLE" $route 2>/dev/null || true ;;
        esac
    done
    for server_ip in ${SERVER_IPS:-}; do
        if [ -n "${DEFAULT_GW:-}" ]; then
            ip route replace table "$TABLE" "$server_ip/32" via "$DEFAULT_GW" dev "$DEFAULT_DEV"
        else
            ip route replace table "$TABLE" "$server_ip/32" dev "$DEFAULT_DEV"
        fi
    done
    ip route replace default dev "$IFACE" table "$TABLE"
    ip rule add priority 1001 from all lookup "$TABLE" 2>/dev/null || true
    ip route flush cache 2>/dev/null || true
}

routes_ready() {
    ip rule show 2>/dev/null | grep -Eq 'lookup[[:space:]]+101|table[[:space:]]+101' &&
        ip route show table "$TABLE" 2>/dev/null | grep -q "^default .*dev $IFACE"
}

restore_routes() {
    if [ -f "$STATE" ]; then
        . "$STATE"
        [ -n "${RP_FILTER_ALL:-}" ] && [ -w /proc/sys/net/ipv4/conf/all/rp_filter ] &&
            echo "$RP_FILTER_ALL" > /proc/sys/net/ipv4/conf/all/rp_filter
        [ -n "${DEFAULT_DEV:-}" ] && [ -n "${RP_FILTER_DEV:-}" ] &&
            [ -w "/proc/sys/net/ipv4/conf/$DEFAULT_DEV/rp_filter" ] &&
            echo "$RP_FILTER_DEV" > "/proc/sys/net/ipv4/conf/$DEFAULT_DEV/rp_filter"
    fi
    while ip rule del priority 1001 from all lookup "$TABLE" 2>/dev/null; do :; done
    ip route flush table "$TABLE" 2>/dev/null || true
    ip addr del "$TUN_ADDR" dev "$IFACE" 2>/dev/null || true
    ip link set "$IFACE" down 2>/dev/null || true
    ip route flush cache 2>/dev/null || true
}

is_running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

start_xray() {
    if is_running; then
        echo "e2xray is already running."
        internet_status
        exit 0
    fi
    if ! config_present; then
        echo "E2XRAY_ERROR=NO_CONFIG"
        exit 1
    fi
    if [ ! -x "$XRAY" ]; then
        echo "Missing embedded Xray core: $XRAY"
        exit 1
    fi
    if [ ! -c /dev/net/tun ]; then
        echo "Missing /dev/net/tun"
        exit 1
    fi
    if [ -f "$PIDFILE" ] || [ -f "$RESOLV_BAK" ]; then
        restore_routes
        restore_dns
        rm -f "$PIDFILE"
    fi
    write_config >/dev/null || {
        echo "Could not write Xray configuration."
        exit 1
    }
    "$XRAY" run -test -c "$CONF" >> "$LOG" 2>&1 || {
        echo "Xray config test failed. See $LOG"
        exit 1
    }
    save_state
    . "$STATE"
    if [ -z "${DEFAULT_DEV:-}" ] || [ -z "${SERVER_IPS:-}" ]; then
        echo "Could not detect the original gateway or resolve the Xray server."
        exit 1
    fi
    if ! setup_dns; then
        restore_dns
        echo "Could not safely update DNS."
        exit 1
    fi
    log "Starting e2xray"
    "$XRAY" run -c "$CONF" >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    if ! is_running; then
        restore_dns
        echo "Xray failed to start. See $LOG"
        exit 1
    fi
    setup_routes
    if ! routes_ready; then
        restore_routes
        restore_dns
        kill "$(cat "$PIDFILE")" 2>/dev/null || true
        rm -f "$PIDFILE"
        echo "TUN routing setup failed. Original network settings were restored."
        exit 1
    fi
    echo "e2xray started."
    internet_status
}

stop_xray() {
    restore_routes
    restore_dns
    if is_running; then
        kill "$(cat "$PIDFILE")" 2>/dev/null || true
        sleep 1
        is_running && kill -9 "$(cat "$PIDFILE")" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
    log "Stopped e2xray"
    echo "e2xray stopped. Routes and DNS restored."
    internet_status
}

install_init() {
    chmod 755 "$BASE/e2xrayctl.sh" 2>/dev/null || true
    chmod 755 /etc/init.d/e2xray 2>/dev/null || true
    if command -v update-rc.d >/dev/null 2>&1; then
        update-rc.d e2xray defaults
    else
        ln -sf /etc/init.d/e2xray /etc/rc3.d/S99e2xray 2>/dev/null || true
        ln -sf /etc/init.d/e2xray /etc/rc5.d/S99e2xray 2>/dev/null || true
    fi
    echo "e2xray init enabled."
}

case "${1:-status}" in
    start) start_xray ;;
    stop) stop_xray ;;
    restart) stop_xray; start_xray ;;
    ping) ping_config ;;
    internet) internet_status ;;
    status) if is_running; then echo "Running"; else echo "Stopped"; fi ;;
    logs) tail -n 120 "$LOG" 2>/dev/null || echo "No log yet." ;;
    write-config) write_config ;;
    install-init) install_init ;;
    *) echo "Usage: $0 {start|stop|restart|ping|internet|status|logs|write-config|install-init}"; exit 1 ;;
esac
