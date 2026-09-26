#!/bin/sh
set -u

BASE="/usr/lib/enigma2/python/Plugins/Extensions/e2xray"
XRAY="/usr/lib/e2xray/bin/xray"
CONF="/etc/e2xray/config.json"
if [ -d /root ]; then
    USERCONF="/root/config.txt"
else
    USERCONF="/home/root/config.txt"
fi
SELECTION="/etc/e2xray/selected"
PARSER="$BASE/proxy_config.py"
RUNTIME="${E2XRAY_RUNTIME:-/var/run/e2xray}"
PARSED_USERCONF="$RUNTIME/user.conf"
PIDFILE="$RUNTIME/xray.pid"
ACTIVE_PROFILE="$RUNTIME/active_profile"
TUN_WARNING="/etc/e2xray/tun-missing"
STATE="$RUNTIME/state"
ROUTE_ERROR="$RUNTIME/route-error"
POLICY_TABLE_OWNED="$RUNTIME/policy-table-owned"
POLICY_RULE_OWNED="$RUNTIME/policy-rule-owned"
SPLIT_ROUTES_OWNED="$RUNTIME/split-routes-owned"
LOG="/tmp/e2xray.log"
RESOLV="/etc/resolv.conf"
RESOLV_BAK="$RUNTIME/resolv.conf.bak"
IFACE="e2xray0"
TUN_ADDR="10.255.0.1/30"
# Must match proxy_config.TUN_GATEWAY6.
TUN_ADDR6="fdfe:e2e2::1/64"
IPV6_OWNED="$RUNTIME/ipv6-mode"
WATCHDOG_PID="$RUNTIME/watchdog.pid"
WATCHDOG_INTERVAL="${E2XRAY_WATCHDOG_INTERVAL:-10}"
# Metric of the fail-closed fallback. Must be worse than the tunnel route so it
# only takes effect once the tunnel route is gone.
CLOSED_METRIC="1000"
# Overridable so the IPv6 handling can be exercised off-box.
IPV6_PROC="${E2XRAY_IPV6_PROC:-/proc/sys/net/ipv6}"
TABLE="101"
INTERNET_PROBE_GOOGLE="https://www.google.com/generate_204"
INTERNET_PROBE_CLOUDFLARE="https://www.cloudflare.com/cdn-cgi/trace"
INTERNET_PROBE_APPLE="https://www.apple.com/library/test/success.html"
DNS1="8.8.8.8"
DNS2="1.1.1.1"
SYSCTL_IPV4="${E2XRAY_SYSCTL_IPV4:-/proc/sys/net/ipv4/conf}"
INTEGRITY_VERIFY="/usr/lib/e2xray/protection/integrity_verify.py"
# Plain-text version, written at build time so it stays readable even when the
# Python sources are obfuscated.
VERSION_FILE="/usr/lib/e2xray/version"
# Enigma2 exposes the receiver identity here. Overridable so the reporting can
# be exercised off-box.
STB_INFO="${E2XRAY_STB_INFO:-/proc/stb/info}"
CONTROL_LOCK="$RUNTIME/control.lock"
BACKEND_FILE="$RUNTIME/network-backend"
BACKEND_ERROR="$RUNTIME/backend-error"
TPROXY_TABLE="102"
TPROXY_MARK="0x2333"
TPROXY_PRIORITY="1002"
TPROXY_PORT="12345"
TPROXY_CHAIN="E2XRAY_TP"
TPROXY_MASK_CHAIN="E2XRAY_MASK"
REDIRECT_CHAIN="E2XRAY_RD"
DNS_CHAIN="E2XRAY_DNS"
# Must match proxy_config.DNS_PORT. Deliberately not 5353, which avahi-daemon
# already owns on most Enigma2 images.
DNS_PORT="15353"
# Matches proxy_config.SELF_MARK. Xray stamps its own sockets with it so the
# transparent chains can RETURN before capturing the proxy's own transport.
SELF_MARK="0xff"
# Card-sharing (OSCam/CCcam/mgcamd) bypass. Those daemons talk to their peers on
# arbitrary public addresses; once a transparent backend captures every outbound
# connection the card traffic is pushed through the proxy too, where it is
# normally blocked -- which is why encrypted channels stop opening. The
# endpoints are discovered automatically, so the user configures nothing.
CS_CHAIN="E2XRAY_CS"
BYPASS_TABLE="103"
BYPASS_MARK="0x2334"
BYPASS_PRIORITY="1000"
CS_MAX_IPS="32"
CS_MAX_PORTS="16"
# Xray marks every socket it opens with SELF_MARK. In TUN mode nothing used to
# act on that mark, so the core's own DNS lookups were routed into the tunnel
# they were needed to build. This rule lets them leave physically instead.
SELF_BYPASS_PRIORITY="999"
SOFTCAM_BYPASS_IPS=""
SOFTCAM_BYPASS_PORTS=""
SOFTCAM_UNSAFE_PORTS=""
NETWORK_BACKEND=""
PYTHON=""

# Enigma2 and non-login shells do not always export the administrative
# directories, and `ip`/`iptables` live there. Without this, capability probes
# report a tool as missing on receivers that actually have it.
case ":$PATH:" in
    *:/usr/sbin:*) ;;
    *) PATH="/usr/sbin:/sbin:$PATH" ;;
esac
export PATH

mkdir -p "$RUNTIME"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
}


release_control_lock() {
    rm -rf "$CONTROL_LOCK" 2>/dev/null || true
}

lock_owner_alive() {
    lock_pid="$1"
    [ -n "$lock_pid" ] || return 1
    kill -0 "$lock_pid" 2>/dev/null || return 1
    if [ -r "/proc/$lock_pid/cmdline" ]; then
        lock_cmd="$(tr '\000' ' ' < "/proc/$lock_pid/cmdline" 2>/dev/null || true)"
        case "$lock_cmd" in
            *e2xrayctl.sh*) return 0 ;;
            *) return 1 ;;
        esac
    fi
    return 0
}

acquire_control_lock() {
    if mkdir "$CONTROL_LOCK" 2>/dev/null; then
        echo "$$" > "$CONTROL_LOCK/pid"
        trap 'release_control_lock' EXIT
        trap 'exit 1' HUP INT TERM
        return 0
    fi

    lock_pid="$(cat "$CONTROL_LOCK/pid" 2>/dev/null || echo '')"
    case "$lock_pid" in
        ''|*[!0-9]*) lock_pid="" ;;
    esac
    if ! lock_owner_alive "$lock_pid"; then
        release_control_lock
        if mkdir "$CONTROL_LOCK" 2>/dev/null; then
            echo "$$" > "$CONTROL_LOCK/pid"
            trap 'release_control_lock' EXIT
            trap 'exit 1' HUP INT TERM
            return 0
        fi
    fi

    echo "E2XRAY_NOOP=BUSY"
    exit 0
}

last_log_line() {
    [ -f "$LOG" ] || return 0
    tail -n 30 "$LOG" 2>/dev/null |
        sed '/^[[:space:]]*$/d' |
        tail -n 1 |
        tr '\r\n' '  ' |
        cut -c 1-300
}

fail_start() {
    error_code="$1"
    shift
    error_detail="$*"
    log "Start failed [$error_code]: $error_detail"
    echo "E2XRAY_ERROR=$error_code"
    echo "E2XRAY_ERROR_DETAIL=$error_detail"
    exit 1
}

find_python() {
    [ -n "${PYTHON:-}" ] && return 0
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import errno, hashlib, io, json, os, re, shlex, socket, subprocess, sys, time' \
                >/dev/null 2>&1; then
            PYTHON="$candidate"
            return 0
        fi
    done
    return 1
}

rotate_log() {
    # /tmp is a RAM disk on most receivers, so the log must not grow forever.
    [ -f "$LOG" ] || return 0
    log_size="$(wc -c < "$LOG" 2>/dev/null || echo 0)"
    case "$log_size" in
        ''|*[!0-9]*) return 0 ;;
    esac
    [ "$log_size" -gt 262144 ] || return 0
    if tail -n 400 "$LOG" > "$LOG.rotate" 2>/dev/null; then
        mv "$LOG.rotate" "$LOG" 2>/dev/null || rm -f "$LOG.rotate"
    else
        rm -f "$LOG.rotate"
    fi
}

plugin_version() {
    # Protected builds ship an obfuscated __init__.py, so the version is also
    # written to a plain file at build time.
    if [ -r "$VERSION_FILE" ]; then
        version_value="$(head -n 1 "$VERSION_FILE" 2>/dev/null | tr -d '\r\n')"
        [ -n "$version_value" ] && { printf '%s\n' "$version_value"; return 0; }
    fi
    version_value="$(
        sed -n 's/^PLUGIN_VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' \
            "$BASE/__init__.py" 2>/dev/null | head -n 1
    )"
    printf '%s\n' "${version_value:-unknown}"
}

receiver_model() {
    model_parts=""
    for info in boxtype vumodel gbmodel azmodel hwmodel model boxname; do
        info_path="$STB_INFO/$info"
        [ -r "$info_path" ] || continue
        info_value="$(head -n 1 "$info_path" 2>/dev/null | tr -d '\r\n')"
        [ -n "$info_value" ] || continue
        model_parts="$model_parts $info=$info_value"
    done
    model_parts="$(printf '%s' "$model_parts" | sed 's/^[[:space:]]*//')"
    printf '%s\n' "${model_parts:-unknown}"
}

receiver_image() {
    # OE-Alliance derivatives describe themselves here; DreamOS does not.
    if [ -r /etc/image-version ]; then
        image_creator="$(sed -n 's/^creator=//p' /etc/image-version 2>/dev/null | head -n 1)"
        image_release="$(sed -n 's/^imageversion=//p' /etc/image-version 2>/dev/null | head -n 1)"
        [ -n "$image_release" ] ||
            image_release="$(sed -n 's/^version=//p' /etc/image-version 2>/dev/null | head -n 1)"
        if [ -n "$image_creator" ]; then
            printf '%s %s\n' "$image_creator" "$image_release" | sed 's/[[:space:]]*$//'
            return 0
        fi
    fi
    if [ -r /etc/os-release ]; then
        image_pretty="$(
            sed -n 's/^PRETTY_NAME=//p' /etc/os-release 2>/dev/null |
                head -n 1 | sed 's/^"//; s/"$//'
        )"
        [ -n "$image_pretty" ] && { printf '%s\n' "$image_pretty"; return 0; }
    fi
    if [ -r /etc/issue ]; then
        image_issue="$(
            head -n 1 /etc/issue 2>/dev/null |
                sed 's/\\[a-zA-Z]//g; s/[[:space:]][[:space:]]*/ /g; s/^ //; s/ $//'
        )"
        [ -n "$image_issue" ] && { printf '%s\n' "$image_issue"; return 0; }
    fi
    echo "unknown"
}

package_manager() {
    managers=""
    command -v opkg >/dev/null 2>&1 && managers="$managers opkg"
    command -v dpkg >/dev/null 2>&1 && managers="$managers dpkg"
    command -v apt >/dev/null 2>&1 && managers="$managers apt"
    managers="$(printf '%s' "$managers" | sed 's/^[[:space:]]*//')"
    printf '%s\n' "${managers:-unknown}"
}

log_environment() {
    # Written at the top of every start so any log a user sends carries the
    # context needed to reproduce the problem.
    log "[ENV] e2xray $(plugin_version)"
    log "[ENV] Receiver: $(receiver_model)"
    log "[ENV] Image: $(receiver_image)  Packages: $(package_manager)"
    log "[ENV] Arch: $(uname -m 2>/dev/null || echo unknown)  Kernel: $(uname -r 2>/dev/null || echo unknown)"
    if find_python; then
        log "[ENV] Python: $PYTHON $("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo unknown)"
    else
        log "[ENV] Python: none usable"
    fi
    if [ -x "$XRAY" ]; then
        log "[ENV] Core: $("$XRAY" version 2>/dev/null | head -n 1 || echo unknown)"
    else
        log "[ENV] Core: missing ($XRAY)"
    fi
}

verify_integrity() {
    [ -f "$INTEGRITY_VERIFY" ] || return 0
    if ! find_python; then
        fail_start "PYTHON_MISSING" "No compatible Python interpreter was found for the integrity check."
    fi
    if ! "$PYTHON" "$INTEGRITY_VERIFY" >> "$LOG" 2>&1; then
        fail_start "INTEGRITY_FAILED" "Protected e2xray files were modified or the package signature is invalid. Reinstall the original package."
    fi
}

load_userconf() {
    # $1/$2 override where the generated files go. Only `start` may write the
    # live core configuration: read-only callers such as `ping` must not, or
    # they rewrite the configuration out from under a start that is already in
    # progress and the tunnel ends up carrying a different profile than the one
    # the user selected.
    userconf_runtime="${1:-$PARSED_USERCONF}"
    userconf_target="${2:-$CONF}"

    PROFILE_ID=""
    PROFILE_NAME=""
    PROTOCOL=""
    SERVER_ADDRESS=""
    SERVER_PORT=""
    DNS1="8.8.8.8"
    DNS2="1.1.1.1"

    [ -f "$USERCONF" ] || return 1
    [ -f "$PARSER" ] || return 1

    if ! find_python; then
        log "No compatible Python interpreter was found."
        return 1
    fi

    rm -f "$userconf_runtime"
    "$PYTHON" "$PARSER" "$USERCONF" "$SELECTION" \
        "$userconf_runtime" "$userconf_target" >> "$LOG" 2>&1 ||
        return 1
    . "$userconf_runtime"
}

valid_receiver_ipv4() {
    ipaddr="$1"
    case "$ipaddr" in
        ''|0.0.0.0|127.*|169.254.*) return 1 ;;
        *[!0-9.]*) return 1 ;;
    esac
    return 0
}

interface_ipv4() {
    iface="$1"
    ipv4=""
    if command -v ip >/dev/null 2>&1; then
        ipv4="$(
            ip -4 addr show dev "$iface" 2>/dev/null |
                awk '$1 == "inet" { sub(/\/.*/, "", $2); print $2; exit }'
        )"
    fi
    if [ -z "$ipv4" ] && command -v ifconfig >/dev/null 2>&1; then
        ipv4="$(
            ifconfig "$iface" 2>/dev/null |
                sed -n 's/.*inet addr:\([0-9.][0-9.]*\).*/\1/p; s/.*inet \([0-9.][0-9.]*\).*/\1/p' |
                sed -n '1p'
        )"
    fi
    if valid_receiver_ipv4 "$ipv4"; then
        printf '%s\n' "$ipv4"
        return 0
    fi
    return 1
}

detect_receiver_network() {
    NETWORK_IFACE=""
    NETWORK_IPV4=""

    preferred="$(default_dev 2>/dev/null || true)"
    case "$preferred" in
        ''|lo|e2xray0) preferred="" ;;
    esac
    if [ -n "$preferred" ]; then
        candidate_ip="$(interface_ipv4 "$preferred" 2>/dev/null || true)"
        if [ -n "$candidate_ip" ]; then
            NETWORK_IFACE="$preferred"
            NETWORK_IPV4="$candidate_ip"
            return 0
        fi
    fi

    # Prefer common receiver LAN/WLAN interface names before considering any
    # other interface. This avoids treating e2xray's own virtual interface as
    # proof that the receiver is attached to a network.
    for iface_path in /sys/class/net/eth* /sys/class/net/en* /sys/class/net/wlan* \
        /sys/class/net/wl* /sys/class/net/ra* /sys/class/net/ath* \
        /sys/class/net/lan* /sys/class/net/br* /sys/class/net/bond*; do
        [ -e "$iface_path" ] || continue
        iface="${iface_path##*/}"
        [ "$iface" = "lo" ] && continue
        [ "$iface" = "e2xray0" ] && continue
        candidate_ip="$(interface_ipv4 "$iface" 2>/dev/null || true)"
        if [ -n "$candidate_ip" ]; then
            NETWORK_IFACE="$iface"
            NETWORK_IPV4="$candidate_ip"
            return 0
        fi
    done

    for iface_path in /sys/class/net/*; do
        [ -e "$iface_path" ] || continue
        iface="${iface_path##*/}"
        case "$iface" in
            lo|e2xray0) continue ;;
        esac
        candidate_ip="$(interface_ipv4 "$iface" 2>/dev/null || true)"
        if [ -n "$candidate_ip" ]; then
            NETWORK_IFACE="$iface"
            NETWORK_IPV4="$candidate_ip"
            return 0
        fi
    done
    return 1
}

network_status() {
    if detect_receiver_network; then
        log "[NETWORK] Interface: $NETWORK_IFACE"
        log "[NETWORK] IPv4: $NETWORK_IPV4"
        log "[NETWORK] Status: ONLINE"
        echo "E2XRAY_LAN=ONLINE"
        echo "E2XRAY_LAN_IFACE=$NETWORK_IFACE"
        echo "E2XRAY_LAN_IPV4=$NETWORK_IPV4"
        return 0
    fi
    log "[NETWORK] No usable IPv4 address was found on the receiver network interfaces."
    log "[NETWORK] Status: OFFLINE"
    echo "E2XRAY_LAN=OFFLINE"
    return 1
}

http_check() {
    url="$1"
    connect_timeout="${2:-2}"
    max_time="${3:-3}"
    if command -v curl >/dev/null 2>&1; then
        curl -k -f -L --connect-timeout "$connect_timeout" --max-time "$max_time" \
            -o /dev/null "$url" >/dev/null 2>&1
        return $?
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -q --no-check-certificate -T "$max_time" -O /dev/null "$url" \
            >/dev/null 2>&1
        return $?
    fi
    host="$(echo "$url" | sed 's#^[a-zA-Z]*://##;s#/.*##')"
    ping -c 1 -W "$connect_timeout" "$host" >/dev/null 2>&1
}

tunnel_carries_traffic() {
    # Verifies that the tunnel actually forwards traffic, not merely that the
    # core started. A dead or filtered server otherwise leaves the receiver with
    # a fully captured network and no way out, which is the single most damaging
    # failure a user can hit. Timeouts are deliberately generous: a slow tunnel
    # on an older receiver must not be mistaken for a broken one.
    attempts=1
    while [ "$attempts" -le 3 ]; do
        for probe_url in "$INTERNET_PROBE_GOOGLE" "$INTERNET_PROBE_CLOUDFLARE" \
            "$INTERNET_PROBE_APPLE"; do
            if http_check "$probe_url" 5 8; then
                log "[HEALTH] Tunnel verified on attempt $attempts."
                return 0
            fi
        done
        log "[HEALTH] Attempt $attempts: no probe answered through the tunnel."
        attempts=$((attempts + 1))
        [ "$attempts" -le 3 ] && sleep 2
    done
    return 1
}

internet_probe_round() {
    round="$1"

    if http_check "$INTERNET_PROBE_GOOGLE"; then
        log "[INTERNET] Round $round Google probe: OK"
        return 0
    fi
    log "[INTERNET] Round $round Google probe: FAILED"

    if http_check "$INTERNET_PROBE_CLOUDFLARE"; then
        log "[INTERNET] Round $round Cloudflare probe: OK"
        return 0
    fi
    log "[INTERNET] Round $round Cloudflare probe: FAILED"

    if http_check "$INTERNET_PROBE_APPLE"; then
        log "[INTERNET] Round $round Apple probe: OK"
        return 0
    fi
    log "[INTERNET] Round $round Apple probe: FAILED"
    return 1
}

internet_status() {
    if ! detect_receiver_network; then
        log "[INTERNET] Skipped probes because the receiver has no usable network IPv4 address."
        log "[INTERNET] Final status: OFFLINE"
        echo "E2XRAY_NET=OFFLINE"
        return 1
    fi

    log "[INTERNET] Checking connectivity via $NETWORK_IFACE ($NETWORK_IPV4)."
    if command -v ping >/dev/null 2>&1; then
        if ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
            log "[INTERNET] Raw IPv4 reachability probe: OK"
        else
            log "[INTERNET] Raw IPv4 reachability probe: FAILED or ICMP blocked"
        fi
    fi

    if internet_probe_round 1; then
        log "[INTERNET] Final status: ONLINE"
        echo "E2XRAY_NET=ONLINE"
        return 0
    fi

    log "[INTERNET] All round 1 probes failed; retrying after 2 seconds."
    sleep 2
    if internet_probe_round 2; then
        log "[INTERNET] Final status: ONLINE"
        echo "E2XRAY_NET=ONLINE"
        return 0
    fi

    log "[INTERNET] Final status: OFFLINE"
    echo "E2XRAY_NET=OFFLINE"
    return 1
}

config_present() {
    [ -f "$USERCONF" ] || return 1
    load_userconf "${1:-$PARSED_USERCONF}" "${2:-$CONF}" || return 1
    [ -n "${PROFILE_ID:-}" ] || return 1
    [ -n "${PROTOCOL:-}" ] || return 1
    [ -n "${SERVER_ADDRESS:-}" ] || return 1
    [ -n "${SERVER_PORT:-}" ] || return 1
    return 0
}

tun_usable() {
    [ -c /dev/net/tun ] && ( : < /dev/net/tun ) 2>/dev/null
}

ensure_tun() {
    if tun_usable; then
        rm -f "$TUN_WARNING"
        return 0
    fi

    log "TUN device is missing; attempting to load the kernel module."
    if command -v modprobe >/dev/null 2>&1; then
        modprobe tun >> "$LOG" 2>&1 || true
    fi

    if ! tun_usable && command -v insmod >/dev/null 2>&1; then
        kernel_release="$(uname -r 2>/dev/null || echo unknown)"
        for tun_module in \
            "/lib/modules/$kernel_release/kernel/drivers/net/tun.ko" \
            "/lib/modules/$kernel_release/tun.ko"; do
            if [ -f "$tun_module" ]; then
                insmod "$tun_module" >> "$LOG" 2>&1 || true
                break
            fi
        done
    fi

    if [ ! -e /dev/net/tun ]; then
        mkdir -p /dev/net >> "$LOG" 2>&1 || return 1
        if command -v mknod >/dev/null 2>&1; then
            mknod /dev/net/tun c 10 200 >> "$LOG" 2>&1 || true
        fi
    fi
    [ -c /dev/net/tun ] || return 1
    chmod 600 /dev/net/tun 2>/dev/null || true
    if tun_usable; then
        rm -f "$TUN_WARNING"
        return 0
    fi
    return 1
}

ensure_tun_action() {
    if ensure_tun; then
        echo "E2XRAY_TUN=READY"
        return 0
    fi
    : > "$TUN_WARNING"
    echo "E2XRAY_TUN=MISSING"
    return 1
}

ping_config() {
    # Deliberately writes to private scratch files. Ping is not serialised
    # against start (it must stay responsive), so touching $CONF here would
    # swap the core configuration mid-start.
    if ! config_present "$RUNTIME/ping-user.conf" "$RUNTIME/ping-config.json"; then
        echo "E2XRAY_CONFIG_PING=NO_CONFIG"
        return 0
    fi
    rm -f "$RUNTIME/ping-config.json" "$RUNTIME/ping-user.conf"
    if [ ! -x "$XRAY" ]; then
        echo "E2XRAY_CONFIG_PING=FAILED"
        return 0
    fi

    # Real delay, not tcping: a temporary Xray instance carries an actual HTTP
    # request through the selected profile and the round trip is timed. A plain
    # TCP connect to the edge server proves nothing about the tunnel itself.
    probe_output="$("$PYTHON" "$PARSER" --realping "$XRAY" "$USERCONF" \
        "$SELECTION" "$RUNTIME" 2>>"$LOG")"
    latency="$(printf '%s\n' "$probe_output" |
        sed -n 's/^REAL_DELAY_MS=\([0-9][0-9]*\)$/\1/p' |
        sed -n '1p')"

    if [ -n "$latency" ]; then
        log "Real delay for $PROFILE_NAME: ${latency}ms"
        echo "E2XRAY_CONFIG_PING=OK"
        echo "E2XRAY_CONFIG_PING_ID=$PROFILE_ID"
        echo "E2XRAY_CONFIG_PING_MS=$latency"
    else
        log "Real delay test failed for $PROFILE_NAME"
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
        *:*)
            # An IPv6 literal resolves to itself. Falling through to the
            # hostname branch returned nothing, so a v6 server parsed fine and
            # then failed to start with "could not resolve the proxy server".
            printf '%s\n' "$host"
            return 0
            ;;
    esac
    case "$host" in
        *[!0-9.]*)
            resolved_ips=""
            if command -v getent >/dev/null 2>&1; then
                resolved_ips="$(
                    getent ahostsv4 "$host" 2>/dev/null |
                        awk '$1 ~ /^[0-9]+\./ {print $1}' |
                        sort -u
                )"
                if [ -z "$resolved_ips" ]; then
                    resolved_ips="$(
                        getent hosts "$host" 2>/dev/null |
                            awk '$1 ~ /^[0-9]+\./ {print $1}' |
                            sort -u
                    )"
                fi
                # A server published only as AAAA is perfectly valid.
                resolved_v6="$(
                    getent ahostsv6 "$host" 2>/dev/null |
                        awk '$1 ~ /:/ {print $1}' |
                        sort -u
                )"
                if [ -n "$resolved_v6" ]; then
                    resolved_ips="$(printf '%s\n%s\n' "$resolved_ips" "$resolved_v6" |
                        sed '/^[[:space:]]*$/d')"
                fi
            fi
            if [ -z "$resolved_ips" ] && command -v nslookup >/dev/null 2>&1; then
                resolved_ips="$(
                    nslookup "$host" 2>/dev/null |
                        awk '/^Address[ 0-9]*: / && $NF ~ /^[0-9]+\./ {print $NF}' |
                        sort -u
                )"
            fi
            if [ -z "$resolved_ips" ] && command -v ping >/dev/null 2>&1; then
                resolved_ips="$(
                    ping -c 1 -W 4 "$host" 2>/dev/null |
                        sed -n '1s/.*(\([0-9.]*\)).*/\1/p'
                )"
            fi
            printf '%s\n' "$resolved_ips"
            ;;
        *)
            echo "$host"
            ;;
    esac
}

limit_list() {
    # Keeps the iptables/route footprint bounded on receivers with a very long
    # peer list. Unquoted on purpose: the input is a space-separated list.
    printf '%s\n' $1 2>/dev/null | sed -n "1,${2}p" | tr '\n' ' ' |
        sed 's/[[:space:]]*$//'
}

discover_softcam_bypass() {
    SOFTCAM_BYPASS_IPS=""
    SOFTCAM_BYPASS_PORTS=""
    SOFTCAM_UNSAFE_PORTS=""

    [ -f "$PARSER" ] || return 0
    find_python || return 0

    # Runs before the tunnel is armed, so name resolution still uses the
    # receiver's own resolver and the live softcam sockets are still intact.
    softcam_output="$("$PYTHON" "$PARSER" --softcam-bypass 2>>"$LOG" || true)"
    softcam_assignments="$(
        printf '%s\n' "$softcam_output" |
            sed -n "s/^\(SOFTCAM_[A-Z_]*='[^']*'\)$/\1/p"
    )"
    [ -n "$softcam_assignments" ] || return 0
    eval "$softcam_assignments"

    SOFTCAM_BYPASS_IPS="$(limit_list "${SOFTCAM_BYPASS_IPS:-}" "$CS_MAX_IPS")"
    SOFTCAM_BYPASS_PORTS="$(limit_list "${SOFTCAM_BYPASS_PORTS:-}" "$CS_MAX_PORTS")"

    if [ -n "$SOFTCAM_BYPASS_IPS" ] || [ -n "$SOFTCAM_BYPASS_PORTS" ]; then
        log "[SOFTCAM] Card-sharing bypass: IPs [${SOFTCAM_BYPASS_IPS:-none}] ports [${SOFTCAM_BYPASS_PORTS:-none}]"
    else
        log "[SOFTCAM] No card-sharing daemon or peer configuration was found."
    fi
    if [ -n "${SOFTCAM_UNSAFE_PORTS:-}" ]; then
        log "[SOFTCAM] Peer ports carrying ordinary traffic are bypassed by address only, not by port: $SOFTCAM_UNSAFE_PORTS"
    fi
    return 0
}

bypass_ip_argument() {
    printf '%s\n' "${SOFTCAM_BYPASS_IPS:-}" | tr ' ' ','  | sed 's/,*$//'
}

server_ip_argument() {
    # Both families, IPv4 first. A server published only as AAAA would
    # otherwise reach the pinning step with nothing to pin.
    printf '%s %s\n' "${SERVER_IPS:-}" "${SERVER_IPS6:-}" |
        sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/[[:space:]][[:space:]]*/,/g'
}

write_config() {
    load_userconf || return 1
    [ -s "$CONF" ] || return 1
    echo "$PROTOCOL config written: $CONF"
}

sinkhole_ip() {
    # A filtered domain does not fail to resolve, it resolves to the censor's
    # block page. Iranian ISPs use 10.10.34.0/24 for this. Building a tunnel to
    # such an address can never work, so it is reported as filtering instead of
    # being silently routed into a black hole.
    case "$1" in
        10.10.34.*) return 0 ;;
        0.0.0.0|0.*) return 0 ;;
        127.*) return 0 ;;
    esac
    return 1
}

save_state() {
    route="$(find_default)"
    dev="$(default_dev)"
    gw="$(default_gw)"
    resolved_ips="$(resolve_server_ips "${SERVER_ADDRESS:-}" | tr '\n' ' ')"
    server_ips=""
    server_ips6=""
    filtered_ips=""
    for resolved_ip in $resolved_ips; do
        case "$resolved_ip" in
            *:*) server_ips6="$server_ips6 $resolved_ip"; continue ;;
        esac
        if sinkhole_ip "$resolved_ip"; then
            filtered_ips="$filtered_ips $resolved_ip"
        else
            server_ips="$server_ips $resolved_ip"
        fi
    done
    server_ips="$(printf '%s' "$server_ips" | sed 's/^[[:space:]]*//')"
    server_ips6="$(printf '%s' "$server_ips6" | sed 's/^[[:space:]]*//')"
    filtered_ips="$(printf '%s' "$filtered_ips" | sed 's/^[[:space:]]*//')"
    [ -n "$filtered_ips" ] &&
        log "[DNS] $SERVER_ADDRESS resolves to the filtering sinkhole:$filtered_ips"
    rp_all="$(cat "$SYSCTL_IPV4/all/rp_filter" 2>/dev/null || echo '')"
    rp_dev="$(cat "$SYSCTL_IPV4/$dev/rp_filter" 2>/dev/null || echo '')"
    {
        echo "DEFAULT_ROUTE='$route'"
        echo "DEFAULT_DEV='$dev'"
        echo "DEFAULT_GW='$gw'"
        echo "DEFAULT_IPV4='$(interface_ipv4 "$dev" 2>/dev/null || true)'"
        echo "SERVER_IPS='$server_ips'"
        echo "SERVER_IPS6='$server_ips6'"
        echo "SERVER_IPS_FILTERED='$filtered_ips'"
        echo "RP_FILTER_ALL='$rp_all'"
        echo "RP_FILTER_DEV='$rp_dev'"
    } > "$STATE"
}

setup_dns() {
    [ -f "$RESOLV" ] && [ ! -f "$RESOLV_BAK" ] && cp "$RESOLV" "$RESOLV_BAK"

    # Some Shadowsocks servers disable native UDP. In that case replacing the
    # receiver DNS with public UDP resolvers makes name resolution fail even
    # though the TCP proxy itself is healthy. Preserve the receiver's existing
    # resolver for Shadowsocks; proxy_config.py also sends UDP/53 direct.
    if [ "${PROTOCOL:-}" = "shadowsocks" ] || [ "${NETWORK_BACKEND:-tun}" != "tun" ]; then
        if [ "${PROTOCOL:-}" = "shadowsocks" ]; then
            log "DNS mode: port 53 is captured and carried over TCP through the tunnel."
        else
            log "DNS mode: preserving system resolver for transparent backend ${NETWORK_BACKEND:-unknown}."
        fi
        return 0
    fi

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

run_ip() {
    log "Running: ip $*"
    ip_output="$(ip "$@" 2>&1)"
    ip_status=$?
    if [ -n "$ip_output" ]; then
        printf '%s\n' "$ip_output" >> "$LOG"
    fi
    if [ "$ip_status" -ne 0 ]; then
        log "Command failed ($ip_status): ip $*"
        printf '%s\n' "ip $*: ${ip_output:-exit status $ip_status}" > "$ROUTE_ERROR"
    fi
    return "$ip_status"
}

record_route_mode() {
    # STATE is freshly written for every start. If policy routing fails and we
    # fall back, the last ROUTE_MODE assignment intentionally wins when sourced.
    printf "ROUTE_MODE='%s'\n" "$1" >> "$STATE"
}

set_backend_error() {
    error_code="$1"
    shift
    error_detail="$*"
    printf '%s|%s\n' "$error_code" "$error_detail" > "$BACKEND_ERROR"
    log "Backend error [$error_code]: $error_detail"
}

clear_backend_error() {
    rm -f "$BACKEND_ERROR"
}

prepare_tun_interface() {
    if ! run_ip link set "$IFACE" up; then
        set_backend_error "TUN_LINK_FAILED" "Could not bring $IFACE up."
        return 1
    fi
    if ! run_ip addr add "$TUN_ADDR" dev "$IFACE"; then
        if ! ip addr show dev "$IFACE" 2>/dev/null |
            grep -q "inet[[:space:]][[:space:]]*${TUN_ADDR%/*}/"; then
            set_backend_error "TUN_ADDRESS_FAILED" "Could not assign $TUN_ADDR to $IFACE."
            return 1
        fi
    fi
}

add_server_routes() {
    route_table="$1"
    route_action="$2"
    for server_ip in ${SERVER_IPS:-}; do
        route_ok=0
        if [ -n "${DEFAULT_GW:-}" ]; then
            run_ip route "$route_action" $route_table "$server_ip/32" \
                via "$DEFAULT_GW" dev "$DEFAULT_DEV" || route_ok=1
        else
            run_ip route "$route_action" $route_table "$server_ip/32" \
                dev "$DEFAULT_DEV" || route_ok=1
        fi
        if [ "$route_ok" -ne 0 ]; then
            # "add" fails outright when an equivalent route already exists -
            # left by an administrator, or by an earlier start that never got to
            # clean up. The bypass is in place either way, so abandoning the
            # whole backend over it is wrong. Ownership is simply not claimed,
            # so a route we did not create is never deleted on stop.
            if [ "$route_action" = add ] &&
                ip route show $route_table 2>/dev/null |
                    grep -q "^$server_ip[ /]"; then
                log "[ROUTE] $server_ip/32 is already routed explicitly; leaving that route as it is."
                continue
            fi
            return 1
        fi
        if [ "$route_action" = add ]; then
            printf '%s\n' "$server_ip/32" >> "$SPLIT_ROUTES_OWNED" || return 1
        fi
    done
    return 0
}

server_route_detail() {
    # The failing command and the kernel's own words, so the on-screen message
    # says what actually went wrong instead of only that something did.
    detail=""
    [ -s "$ROUTE_ERROR" ] &&
        detail="$(tr '\r\n' '  ' < "$ROUTE_ERROR" 2>/dev/null | cut -c 1-300)"
    printf '%s\n' "${detail:-$1}"
}

add_bypass_routes() {
    # TUN hijacks the default route, so card-sharing peers need an explicit
    # host route back out through the physical interface. A failure here is not
    # fatal: the tunnel still works, only the card traffic would be captured.
    route_table="$1"
    route_action="$2"
    for cs_ip in ${SOFTCAM_BYPASS_IPS:-}; do
        if [ -n "${DEFAULT_GW:-}" ]; then
            run_ip route "$route_action" $route_table "$cs_ip/32" \
                via "$DEFAULT_GW" dev "$DEFAULT_DEV" || continue
        else
            run_ip route "$route_action" $route_table "$cs_ip/32" \
                dev "$DEFAULT_DEV" || continue
        fi
        if [ "$route_action" = add ]; then
            printf '%s\n' "$cs_ip/32" >> "$SPLIT_ROUTES_OWNED" || true
        fi
    done
    return 0
}

delete_bypass_rule() {
    rule_priority="$1"
    rule_mark="$2"
    attempts=0
    while [ "$attempts" -lt 16 ] &&
        ip rule del priority "$rule_priority" fwmark "$rule_mark" \
            lookup "$BYPASS_TABLE" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
    done
}

cleanup_bypass_mark() {
    if command -v iptables >/dev/null 2>&1; then
        iptables -t mangle -D OUTPUT -j "$CS_CHAIN" >/dev/null 2>&1 || true
        iptables -t mangle -F "$CS_CHAIN" >/dev/null 2>&1 || true
        iptables -t mangle -X "$CS_CHAIN" >/dev/null 2>&1 || true
    fi
    if command -v ip >/dev/null 2>&1; then
        delete_bypass_rule "$BYPASS_PRIORITY" "$BYPASS_MARK"
        delete_bypass_rule "$SELF_BYPASS_PRIORITY" "$SELF_MARK"
        ip route flush table "$BYPASS_TABLE" >/dev/null 2>&1 || true
        ip route flush cache >/dev/null 2>&1 || true
    fi
}

ensure_bypass_table() {
    # A private table whose only route is the receiver's real default. Anything
    # policy-routed here leaves through the physical interface instead of the
    # TUN device.
    command -v ip >/dev/null 2>&1 || return 1
    ip rule show >/dev/null 2>&1 || return 1
    if [ -n "${DEFAULT_GW:-}" ]; then
        run_ip route replace table "$BYPASS_TABLE" default \
            via "$DEFAULT_GW" dev "$DEFAULT_DEV" || return 1
    else
        run_ip route replace table "$BYPASS_TABLE" default \
            dev "$DEFAULT_DEV" || return 1
    fi
    return 0
}

setup_self_mark_bypass() {
    # Without this the core's own sockets are captured by its own tunnel. The
    # proxy transport survived only because of the explicit /32 server route;
    # every other socket, in particular the DNS lookups needed to resolve a
    # hostname-based server, was swallowed and timed out forever.
    ensure_bypass_table || {
        log "[ROUTE] No policy routing: Xray's own traffic cannot be separated from the tunnel."
        return 1
    }
    if ip rule show 2>/dev/null |
        grep -q "^[[:space:]]*${SELF_BYPASS_PRIORITY}:"; then
        log "[ROUTE] Policy priority $SELF_BYPASS_PRIORITY is already in use."
        return 1
    fi
    run_ip rule add priority "$SELF_BYPASS_PRIORITY" fwmark "$SELF_MARK" \
        lookup "$BYPASS_TABLE" || return 1
    log "[ROUTE] Xray's own sockets now leave via $DEFAULT_DEV, not the tunnel."
    return 0
}

setup_bypass_mark() {
    # Port-based card-sharing bypass for the TUN backend. Host routes already
    # cover the peers whose address is known; this catches a reader that
    # reconnects to a different address on the same port. Entirely optional:
    # images without mangle or ip rule simply keep the host routes.
    [ -n "${SOFTCAM_BYPASS_PORTS:-}" ] || return 0
    command -v iptables >/dev/null 2>&1 || return 1
    command -v ip >/dev/null 2>&1 || return 1
    iptables -t mangle -L >/dev/null 2>&1 || return 1
    ip rule show >/dev/null 2>&1 || return 1
    if ip rule show 2>/dev/null | grep -q "^[[:space:]]*${BYPASS_PRIORITY}:"; then
        log "[SOFTCAM] Policy priority $BYPASS_PRIORITY is already in use; port bypass skipped."
        return 1
    fi

    ensure_bypass_table || return 1
    run_ip rule add priority "$BYPASS_PRIORITY" fwmark "$BYPASS_MARK" \
        lookup "$BYPASS_TABLE" || { delete_bypass_rule "$BYPASS_PRIORITY" "$BYPASS_MARK"; return 1; }
    run_iptables -t mangle -N "$CS_CHAIN" || { cleanup_bypass_mark; return 1; }
    for cs_port in ${SOFTCAM_BYPASS_PORTS:-}; do
        run_iptables -t mangle -A "$CS_CHAIN" -p tcp --dport "$cs_port" \
            -j MARK --set-mark "$BYPASS_MARK" || true
        run_iptables -t mangle -A "$CS_CHAIN" -p udp --dport "$cs_port" \
            -j MARK --set-mark "$BYPASS_MARK" || true
    done
    for cs_ip in ${SOFTCAM_BYPASS_IPS:-}; do
        run_iptables -t mangle -A "$CS_CHAIN" -d "$cs_ip/32" \
            -j MARK --set-mark "$BYPASS_MARK" || true
    done
    # Position 1: the mark must be set before any other e2xray mangle chain
    # gets the chance to claim the packet.
    run_iptables -t mangle -I OUTPUT 1 -j "$CS_CHAIN" ||
        { cleanup_bypass_mark; return 1; }
    ip route flush cache >/dev/null 2>&1 || true
    log "[SOFTCAM] Port-based card-sharing bypass active via table $BYPASS_TABLE."
    return 0
}

cleanup_policy_routes() {
    cleanup_force="${1:-}"

    if [ -f "$POLICY_RULE_OWNED" ] || [ "$cleanup_force" = force ]; then
        # The final delete normally fails after the last matching rule is gone.
        # This is expected during cleanup, so keep it out of the user log.
        # The attempt cap matters: an `ip` applet that returns success for an
        # unsupported subcommand would otherwise hang Stop forever and leave
        # the receiver without networking.
        attempts=0
        while [ "$attempts" -lt 16 ] &&
            ip rule del priority 1001 from all lookup "$TABLE" >/dev/null 2>&1; do
            attempts=$((attempts + 1))
        done
    fi

    if [ -f "$POLICY_TABLE_OWNED" ] || [ "$cleanup_force" = force ]; then
        ip route flush table "$TABLE" >/dev/null 2>&1 || true
    fi

    rm -f "$POLICY_RULE_OWNED" "$POLICY_TABLE_OWNED"
    ip route flush cache >/dev/null 2>&1 || true
}

seal_route_table() {
    # Fail closed. The tunnel's default route lives on e2xray0, so when the
    # core dies the interface and its route disappear together, the lookup in
    # table $TABLE finds nothing, and the kernel simply falls through to the
    # main table - silently sending everything out in the clear while the user
    # still believes the tunnel is up. A higher-metric unreachable route keeps
    # the table authoritative no matter what happens to the interface.
    if run_ip route replace unreachable default metric "$CLOSED_METRIC" \
        table "$TABLE"; then
        return 0
    fi
    log "[ROUTE] This image cannot install an unreachable route; if the core dies traffic would leave unprotected."
    return 1
}

seal_split_routes() {
    seal_ok=0
    run_ip route replace unreachable 0.0.0.0/1 metric "$CLOSED_METRIC" ||
        seal_ok=1
    run_ip route replace unreachable 128.0.0.0/1 metric "$CLOSED_METRIC" ||
        seal_ok=1
    if [ "$seal_ok" -ne 0 ]; then
        log "[ROUTE] This image cannot install unreachable routes; if the core dies traffic would leave unprotected."
        return 1
    fi
    return 0
}

unseal_split_routes() {
    command -v ip >/dev/null 2>&1 || return 0
    ip route del unreachable 0.0.0.0/1 metric "$CLOSED_METRIC" >/dev/null 2>&1 || true
    ip route del unreachable 128.0.0.0/1 metric "$CLOSED_METRIC" >/dev/null 2>&1 || true
}

watchdog_stop() {
    [ -f "$WATCHDOG_PID" ] || return 0
    wd_pid="$(cat "$WATCHDOG_PID" 2>/dev/null || echo '')"
    rm -f "$WATCHDOG_PID"
    case "$wd_pid" in
        ''|*[!0-9]*) return 0 ;;
    esac
    [ "$wd_pid" -gt 1 ] 2>/dev/null || return 0
    kill "$wd_pid" 2>/dev/null || true
    return 0
}

state_value() {
    [ -f "$STATE" ] || return 1
    sed -n "s/^$1='\(.*\)'\$/\1/p" "$STATE" 2>/dev/null | head -n 1
}

watchdog_network_changed() {
    # Every bypass the tunnel depends on - the private table's default, the
    # proxy server's host routes, the card-sharing routes - was written against
    # the gateway that existed at start. A new DHCP lease or a move to another
    # Wi-Fi leaves all of them pointing at an address that is no longer there,
    # so the transport black-holes silently while the UI still says Running.
    [ -f "$STATE" ] || return 1
    saved_dev="$(state_value DEFAULT_DEV || true)"
    [ -n "$saved_dev" ] || return 1
    current_dev="$(default_dev)"
    # No default route at all is a flap, not a change; the next tick re-checks.
    [ -n "$current_dev" ] || return 1
    [ "$current_dev" = "$saved_dev" ] || return 0
    [ "$(default_gw)" = "$(state_value DEFAULT_GW || true)" ] || return 0
    saved_ipv4="$(state_value DEFAULT_IPV4 || true)"
    if [ -n "$saved_ipv4" ]; then
        current_ipv4="$(interface_ipv4 "$current_dev" 2>/dev/null || true)"
        [ -n "$current_ipv4" ] || return 1
        [ "$current_ipv4" = "$saved_ipv4" ] || return 0
    fi
    return 1
}

watchdog_start() {
    watchdog_stop
    (
        # Detached supervisor. Routing now fails closed, so a core that dies
        # unnoticed would leave the receiver with no internet at all. Notice it
        # and tear the capture down properly instead, which restores normal
        # networking and leaves an explanation in the log.
        # The inherited EXIT trap must go first, or this subshell would release
        # the parent's control lock when it finishes.
        trap - EXIT HUP INT TERM
        network_changed=0
        while : ; do
            sleep "$WATCHDOG_INTERVAL"
            [ -f "$WATCHDOG_PID" ] || exit 0
            runtime_state_present || exit 0
            if ! is_running; then
                log "[WATCHDOG] The Xray core is no longer running; restoring normal networking."
                rm -f "$WATCHDOG_PID"
                "$0" stop >/dev/null 2>&1 || true
                exit 0
            fi
            if watchdog_network_changed; then
                # Confirmed over two consecutive checks, so a brief flap during
                # a DHCP renewal does not trigger a needless rebuild.
                network_changed=$((network_changed + 1))
            else
                network_changed=0
            fi
            if [ "$network_changed" -ge 2 ]; then
                log "[WATCHDOG] The receiver's network changed; rebuilding the tunnel for the new gateway."
                rm -f "$WATCHDOG_PID"
                "$0" restart >/dev/null 2>&1 || true
                exit 0
            fi
        done
    # A background child that inherits eConsoleAppContainer's stdout/stderr
    # keeps its pipes open forever. Enigma2 then never emits appClosed, so the
    # successful Start notification and profile tick are not shown until the
    # screen is reopened. Fully detach all three standard descriptors.
    ) </dev/null >/dev/null 2>&1 &
    echo $! > "$WATCHDOG_PID"
    log "[WATCHDOG] Supervising the core every ${WATCHDOG_INTERVAL}s."
}

setup_policy_routes() {
    # BusyBox often provides `ip route` but is built without `ip rule`.
    # Probe both capabilities instead of assuming that any `ip` is iproute2.
    if ! ip rule show >/dev/null 2>&1; then
        set_backend_error "IP_RULE_FAILED" "This image does not support ip rule."
        return 1
    fi
    if ! ip route show table "$TABLE" >/dev/null 2>&1; then
        set_backend_error "ROUTE_TABLE_FAILED" "Routing table $TABLE is unavailable."
        return 1
    fi

    if ip rule show 2>/dev/null | grep -q '^[[:space:]]*1001:'; then
        set_backend_error "IP_RULE_FAILED" "Policy rule priority 1001 is already in use."
        return 1
    fi
    if ip route show table "$TABLE" 2>/dev/null | grep -q .; then
        set_backend_error "ROUTE_TABLE_FAILED" "Policy route table $TABLE is already in use."
        return 1
    fi

    record_route_mode policy
    : > "$POLICY_TABLE_OWNED"
    if ! ip route show table main 2>/dev/null | while IFS= read -r route; do
        case "$route" in
            default*) ;;
            *)
                ip route replace table "$TABLE" $route >> "$LOG" 2>&1 || exit 1
                ;;
        esac
    done; then
        set_backend_error "ROUTE_TABLE_FAILED" "Could not copy main routes into table $TABLE."
        return 1
    fi
    if ! add_server_routes "table $TABLE" replace; then
        set_backend_error "SERVER_BYPASS_ROUTE_FAILED" \
            "$(server_route_detail "Could not install proxy-server bypass route in table $TABLE.")"
        return 1
    fi
    add_bypass_routes "table $TABLE" replace
    if ! run_ip route replace table "$TABLE" default dev "$IFACE"; then
        set_backend_error "ROUTE_TABLE_FAILED" "Could not install TUN default route in table $TABLE."
        return 1
    fi
    seal_route_table || true
    if ! run_ip rule add priority 1001 from all lookup "$TABLE"; then
        set_backend_error "IP_RULE_FAILED" "Could not install policy rule for table $TABLE."
        return 1
    fi
    : > "$POLICY_RULE_OWNED"
    ip route flush cache >> "$LOG" 2>&1 || true
    policy_routes_ready
}

policy_routes_ready() {
    ip rule show 2>/dev/null |
        grep -Eq 'lookup[[:space:]]+101|table[[:space:]]+101' &&
        ip route show table "$TABLE" 2>/dev/null |
            grep -q "^default .*dev $IFACE"
}

setup_split_routes() {
    # Portable fallback for receivers whose BusyBox/kernel has no policy
    # routing. Two /1 routes override the original default while the explicit
    # proxy-server /32 route prevents the Xray transport from entering TUN.
    record_route_mode split
    rm -f "$SPLIT_ROUTES_OWNED"
    # Use add rather than replace so an existing administrator-managed /32
    # route is never overwritten and then lost during rollback.
    if ! add_server_routes "" add; then
        set_backend_error "SERVER_BYPASS_ROUTE_FAILED" \
            "$(server_route_detail "Could not install proxy-server bypass route.")"
        return 1
    fi
    add_bypass_routes "" add
    if ! run_ip route add 0.0.0.0/1 dev "$IFACE"; then
        set_backend_error "ROUTE_TABLE_FAILED" "Could not install first split-default TUN route."
        return 1
    fi
    printf '%s\n' "0.0.0.0/1" >> "$SPLIT_ROUTES_OWNED" || return 1
    if ! run_ip route add 128.0.0.0/1 dev "$IFACE"; then
        set_backend_error "ROUTE_TABLE_FAILED" "Could not install second split-default TUN route."
        return 1
    fi
    printf '%s\n' "128.0.0.0/1" >> "$SPLIT_ROUTES_OWNED" || return 1
    seal_split_routes || true
    ip route flush cache >> "$LOG" 2>&1 || true
    split_routes_ready
}

split_routes_ready() {
    ip route show 2>/dev/null |
        grep -q "^0\.0\.0\.0/1 .*dev $IFACE" &&
        ip route show 2>/dev/null |
            grep -q "^128\.0\.0\.0/1 .*dev $IFACE"
}

setup_routes() {
    . "$STATE"
    rm -f "$ROUTE_ERROR" "$POLICY_TABLE_OWNED" "$POLICY_RULE_OWNED" \
        "$SPLIT_ROUTES_OWNED"
    [ -w "$SYSCTL_IPV4/all/rp_filter" ] && echo 0 > "$SYSCTL_IPV4/all/rp_filter"
    [ -n "${DEFAULT_DEV:-}" ] && [ -w "$SYSCTL_IPV4/$DEFAULT_DEV/rp_filter" ] &&
        echo 0 > "$SYSCTL_IPV4/$DEFAULT_DEV/rp_filter"
    prepare_tun_interface || return 1
    # Installed before the tunnel claims the default route, so there is no
    # window in which the core's own sockets can be captured.
    setup_self_mark_bypass || true

    if setup_policy_routes; then
        rm -f "$ROUTE_ERROR"
        log "TUN routing mode: policy table $TABLE"
        return 0
    fi

    log "Policy routing is unavailable or failed; trying split-default fallback."
    cleanup_policy_routes
    if setup_split_routes; then
        rm -f "$ROUTE_ERROR"
        log "TUN routing mode: split default routes"
        return 0
    fi
    log "Split-default TUN routing also failed."
    return 1
}

routes_ready() {
    . "$STATE"
    case "${ROUTE_MODE:-policy}" in
        policy) policy_routes_ready ;;
        split) split_routes_ready ;;
        *) return 1 ;;
    esac
}

restore_routes() {
    route_mode="policy"
    legacy_state=0
    if [ -f "$STATE" ]; then
        grep -q '^ROUTE_MODE=' "$STATE" 2>/dev/null || legacy_state=1
        . "$STATE"
        route_mode="${ROUTE_MODE:-policy}"
        [ -n "${RP_FILTER_ALL:-}" ] && [ -w "$SYSCTL_IPV4/all/rp_filter" ] &&
            echo "$RP_FILTER_ALL" > "$SYSCTL_IPV4/all/rp_filter"
        [ -n "${DEFAULT_DEV:-}" ] && [ -n "${RP_FILTER_DEV:-}" ] &&
            [ -w "$SYSCTL_IPV4/$DEFAULT_DEV/rp_filter" ] &&
            echo "$RP_FILTER_DEV" > "$SYSCTL_IPV4/$DEFAULT_DEV/rp_filter"
    fi
    case "$route_mode" in
        split)
            if [ -f "$SPLIT_ROUTES_OWNED" ]; then
                while IFS= read -r owned_route; do
                    [ -n "$owned_route" ] || continue
                    ip route del "$owned_route" >/dev/null 2>&1 || true
                done < "$SPLIT_ROUTES_OWNED"
            fi
            ;;
        *)
            if [ "$legacy_state" -eq 1 ]; then
                cleanup_policy_routes force
            else
                cleanup_policy_routes
            fi
            ;;
    esac
    rm -f "$SPLIT_ROUTES_OWNED"
    unseal_split_routes
    ip addr del "$TUN_ADDR" dev "$IFACE" 2>/dev/null || true
    ip link set "$IFACE" down 2>/dev/null || true
    ip route flush cache 2>/dev/null || true
}

ipv6_stack_present() {
    [ -d "$IPV6_PROC" ] || return 1
    command -v ip >/dev/null 2>&1 || return 1
    ip -6 route show >/dev/null 2>&1 || return 1
    return 0
}

ipv6_in_use() {
    # Only meaningful when the receiver actually has a routable v6 address and
    # a default route; otherwise there is nothing to capture or to block.
    ipv6_stack_present || return 1
    ip -6 addr show scope global 2>/dev/null | grep -q 'inet6' || return 1
    ip -6 route show default 2>/dev/null | grep -q . || return 1
    return 0
}

ipv6_default_gw() {
    ip -6 route show default 2>/dev/null |
        awk '{for(i=1;i<=NF;i++) if($i=="via") {print $(i+1); exit}}'
}

capture_ipv6_tun() {
    # Point IPv6 at the tunnel exactly the way IPv4 is pointed at it.
    ip -6 rule show >/dev/null 2>&1 || return 1
    run_ip -6 addr add "$TUN_ADDR6" dev "$IFACE" || {
        ip -6 addr show dev "$IFACE" 2>/dev/null |
            grep -q "${TUN_ADDR6%/*}" || return 1
    }
    ipv6_gw="$(ipv6_default_gw)"
    if [ -n "$ipv6_gw" ]; then
        run_ip -6 route replace table "$BYPASS_TABLE" default \
            via "$ipv6_gw" dev "$DEFAULT_DEV" || return 1
    else
        run_ip -6 route replace table "$BYPASS_TABLE" default \
            dev "$DEFAULT_DEV" || return 1
    fi
    # Same precedence as IPv4: the core's own sockets first, then everything
    # else into the tunnel.
    run_ip -6 rule add priority "$SELF_BYPASS_PRIORITY" fwmark "$SELF_MARK" \
        lookup "$BYPASS_TABLE" || return 1
    for server_ip6 in ${SERVER_IPS6:-}; do
        if [ -n "$ipv6_gw" ]; then
            run_ip -6 route replace table "$TABLE" "$server_ip6/128" \
                via "$ipv6_gw" dev "$DEFAULT_DEV" || true
        else
            run_ip -6 route replace table "$TABLE" "$server_ip6/128" \
                dev "$DEFAULT_DEV" || true
        fi
    done
    run_ip -6 route replace table "$TABLE" default dev "$IFACE" || return 1
    run_ip -6 route replace unreachable default metric "$CLOSED_METRIC" \
        table "$TABLE" || true
    run_ip -6 rule add priority 1001 from all lookup "$TABLE" || return 1
    printf 'capture\n' > "$IPV6_OWNED"
    log "[IPV6] IPv6 is captured by the tunnel."
    return 0
}

block_ipv6() {
    # Used when IPv6 cannot be captured. Leaving it up would send every
    # AAAA-capable destination straight out of the receiver, past the tunnel.
    ipv6_stack_present || return 1
    # The core's own sockets must still get out, or a server reachable only
    # over IPv6 would be blocked by the very rule meant to protect the user.
    if ip -6 rule show >/dev/null 2>&1; then
        ipv6_gw="$(ipv6_default_gw)"
        if [ -n "$ipv6_gw" ]; then
            run_ip -6 route replace table "$BYPASS_TABLE" default \
                via "$ipv6_gw" dev "$DEFAULT_DEV" || true
        else
            run_ip -6 route replace table "$BYPASS_TABLE" default \
                dev "$DEFAULT_DEV" || true
        fi
        run_ip -6 rule add priority "$SELF_BYPASS_PRIORITY" fwmark "$SELF_MARK" \
            lookup "$BYPASS_TABLE" || true
    fi
    run_ip -6 route add blackhole default metric 1 || return 1
    printf 'block\n' > "$IPV6_OWNED"
    log "[IPV6] IPv6 could not be captured on this backend and is blocked while the tunnel runs."
    return 0
}

setup_ipv6() {
    ipv6_backend="$1"
    rm -f "$IPV6_OWNED"
    if ! ipv6_in_use; then
        return 0
    fi
    if [ "$ipv6_backend" = "tun" ] && capture_ipv6_tun; then
        return 0
    fi
    # A half-installed capture must not be left behind.
    [ "$ipv6_backend" = "tun" ] && cleanup_ipv6_capture
    block_ipv6 || log "[IPV6] WARNING: IPv6 is active and could be leaving outside the tunnel."
    return 0
}

cleanup_ipv6_capture() {
    ipv6_stack_present || return 0
    attempts=0
    while [ "$attempts" -lt 16 ] &&
        ip -6 rule del priority 1001 from all lookup "$TABLE" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
    done
    attempts=0
    while [ "$attempts" -lt 16 ] &&
        ip -6 rule del priority "$SELF_BYPASS_PRIORITY" fwmark "$SELF_MARK" \
            lookup "$BYPASS_TABLE" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
    done
    ip -6 route flush table "$TABLE" >/dev/null 2>&1 || true
    ip -6 route flush table "$BYPASS_TABLE" >/dev/null 2>&1 || true
    ip -6 addr del "$TUN_ADDR6" dev "$IFACE" >/dev/null 2>&1 || true
}

cleanup_ipv6() {
    ipv6_stack_present || return 0
    # Always attempt both, regardless of the recorded mode: a crash between
    # writing the marker and installing the rules must still clean up.
    ip -6 route del blackhole default metric 1 >/dev/null 2>&1 || true
    cleanup_ipv6_capture
    ip -6 route flush cache >/dev/null 2>&1 || true
    rm -f "$IPV6_OWNED"
}

run_iptables() {
    log "Running: iptables $*"
    ipt_output="$(iptables "$@" 2>&1)"
    ipt_status=$?
    [ -n "$ipt_output" ] && printf '%s\n' "$ipt_output" >> "$LOG"
    if [ "$ipt_status" -ne 0 ]; then
        log "Command failed ($ipt_status): iptables $*"
    fi
    return "$ipt_status"
}

iptables_base_usable() {
    command -v iptables >/dev/null 2>&1 || return 1
    iptables -t nat -L >/dev/null 2>&1 || return 1
}

tproxy_capable() {
    command -v ip >/dev/null 2>&1 || return 1
    command -v iptables >/dev/null 2>&1 || return 1
    ip rule show >/dev/null 2>&1 || return 1
    ip route show table "$TPROXY_TABLE" >/dev/null 2>&1 || return 1
    iptables -t mangle -L >/dev/null 2>&1 || return 1

    # BusyBox `ip` frequently omits the `local` route type, and without it
    # locally generated packets can never be looped back into PREROUTING where
    # TPROXY lives.
    ip route add local 0.0.0.0/0 dev lo table "$TPROXY_TABLE" >/dev/null 2>&1 || return 1
    ip route flush table "$TPROXY_TABLE" >/dev/null 2>&1 || true

    probe="E2X_TP_PROBE_$$"
    iptables -t mangle -N "$probe" >/dev/null 2>&1 || return 1
    if iptables -t mangle -A "$probe" -p tcp -j TPROXY \
        --on-port "$TPROXY_PORT" --tproxy-mark "$TPROXY_MARK/$TPROXY_MARK" \
        >/dev/null 2>&1; then
        capable=0
    else
        capable=1
    fi
    iptables -t mangle -F "$probe" >/dev/null 2>&1 || true
    iptables -t mangle -X "$probe" >/dev/null 2>&1 || true
    return "$capable"
}

redirect_capable() {
    iptables_base_usable || return 1
    probe="E2X_RD_PROBE_$$"
    iptables -t nat -N "$probe" >/dev/null 2>&1 || return 1
    if iptables -t nat -A "$probe" -p tcp -j REDIRECT --to-ports "$TPROXY_PORT" \
        >/dev/null 2>&1; then
        capable=0
    else
        capable=1
    fi
    iptables -t nat -F "$probe" >/dev/null 2>&1 || true
    iptables -t nat -X "$probe" >/dev/null 2>&1 || true
    return "$capable"
}

add_transparent_bypass_rules() {
    table="$1"
    chain="$2"
    # Xray's own sockets carry SELF_MARK. Without this first rule the proxy
    # transport is captured by the very chain that is supposed to feed it and
    # every connection loops back into Xray.
    run_iptables -t "$table" -A "$chain" -m mark --mark "$SELF_MARK" -j RETURN ||
        return 1
    for network in \
        0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 \
        169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/3; do
        run_iptables -t "$table" -A "$chain" -d "$network" -j RETURN || return 1
    done
    for server_ip in ${SERVER_IPS:-}; do
        run_iptables -t "$table" -A "$chain" -d "$server_ip/32" -j RETURN || return 1
    done
    add_cardsharing_bypass_rules "$table" "$chain"
}

add_cardsharing_bypass_rules() {
    table="$1"
    chain="$2"
    # Card-sharing peers leave before anything else can capture them. Both the
    # discovered peer addresses and their ports are matched: the address covers
    # a reader that moves to another port, the port covers a peer whose address
    # changed since discovery.
    for cs_ip in ${SOFTCAM_BYPASS_IPS:-}; do
        run_iptables -t "$table" -A "$chain" -d "$cs_ip/32" -j RETURN || return 1
    done
    for cs_port in ${SOFTCAM_BYPASS_PORTS:-}; do
        run_iptables -t "$table" -A "$chain" -p tcp --dport "$cs_port" -j RETURN ||
            return 1
        # camd35 and some CCcam peers are UDP. The nat chain only ever sees TCP,
        # so a missing UDP match there is not an error.
        run_iptables -t "$table" -A "$chain" -p udp --dport "$cs_port" -j RETURN ||
            true
    done
    return 0
}

cleanup_dns_redirect() {
    command -v iptables >/dev/null 2>&1 || return 0
    iptables -t nat -D OUTPUT -j "$DNS_CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -F "$DNS_CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -X "$DNS_CHAIN" >/dev/null 2>&1 || true
}

setup_dns_redirect() {
    # Transparent backends leave the receiver's resolver in place, so plain
    # UDP/53 would still be answered by the ISP. Sending port 53 to Xray's
    # dedicated dns-in inbound is what makes name resolution follow the tunnel.
    cleanup_dns_redirect
    iptables_base_usable || {
        log "DNS redirection unavailable: iptables NAT support is missing."
        return 1
    }
    run_iptables -t nat -N "$DNS_CHAIN" || return 1
    run_iptables -t nat -A "$DNS_CHAIN" -m mark --mark "$SELF_MARK" -j RETURN ||
        { cleanup_dns_redirect; return 1; }
    run_iptables -t nat -A "$DNS_CHAIN" -p udp --dport 53 \
        -j REDIRECT --to-ports "$DNS_PORT" || { cleanup_dns_redirect; return 1; }
    run_iptables -t nat -A "$DNS_CHAIN" -p tcp --dport 53 \
        -j REDIRECT --to-ports "$DNS_PORT" || { cleanup_dns_redirect; return 1; }
    run_iptables -t nat -A OUTPUT -j "$DNS_CHAIN" ||
        { cleanup_dns_redirect; return 1; }
    log "DNS redirection ready: TCP/UDP port 53 now resolves through Xray."
    return 0
}

cleanup_tproxy() {
    cleanup_dns_redirect
    command -v iptables >/dev/null 2>&1 || return 0
    iptables -t mangle -D OUTPUT -p tcp -j "$TPROXY_MASK_CHAIN" >/dev/null 2>&1 || true
    iptables -t mangle -D OUTPUT -p udp -j "$TPROXY_MASK_CHAIN" >/dev/null 2>&1 || true
    iptables -t mangle -D PREROUTING -m mark --mark "$TPROXY_MARK" -j "$TPROXY_CHAIN" >/dev/null 2>&1 || true
    iptables -t mangle -F "$TPROXY_MASK_CHAIN" >/dev/null 2>&1 || true
    iptables -t mangle -X "$TPROXY_MASK_CHAIN" >/dev/null 2>&1 || true
    iptables -t mangle -F "$TPROXY_CHAIN" >/dev/null 2>&1 || true
    iptables -t mangle -X "$TPROXY_CHAIN" >/dev/null 2>&1 || true
    if command -v ip >/dev/null 2>&1; then
        attempts=0
        while [ "$attempts" -lt 16 ] &&
            ip rule del priority "$TPROXY_PRIORITY" fwmark "$TPROXY_MARK" \
                lookup "$TPROXY_TABLE" >/dev/null 2>&1; do
            attempts=$((attempts + 1))
        done
        ip route flush table "$TPROXY_TABLE" >/dev/null 2>&1 || true
        ip route flush cache >/dev/null 2>&1 || true
    fi
}

setup_tproxy() {
    clear_backend_error
    cleanup_tproxy
    tproxy_capable || {
        set_backend_error "TPROXY_SETUP_FAILED" "TPROXY target, policy routing, or required iptables support is unavailable."
        return 1
    }
    if ! run_ip rule add priority "$TPROXY_PRIORITY" fwmark "$TPROXY_MARK" lookup "$TPROXY_TABLE"; then
        set_backend_error "IP_RULE_FAILED" "Could not install TPROXY fwmark policy rule."
        cleanup_tproxy
        return 1
    fi
    if ! run_ip route add local 0.0.0.0/0 dev lo table "$TPROXY_TABLE"; then
        set_backend_error "ROUTE_TABLE_FAILED" "Could not install local TPROXY route in table $TPROXY_TABLE."
        cleanup_tproxy
        return 1
    fi
    run_iptables -t mangle -N "$TPROXY_CHAIN" || { cleanup_tproxy; set_backend_error "TPROXY_SETUP_FAILED" "Could not create TPROXY chain."; return 1; }
    run_iptables -t mangle -N "$TPROXY_MASK_CHAIN" || { cleanup_tproxy; set_backend_error "TPROXY_SETUP_FAILED" "Could not create TPROXY mark chain."; return 1; }
    add_transparent_bypass_rules mangle "$TPROXY_MASK_CHAIN" || { cleanup_tproxy; set_backend_error "TPROXY_SETUP_FAILED" "Could not install TPROXY bypass rules."; return 1; }
    # Port 53 is handled by the NAT DNS chain instead. Marking it here would
    # send the same query through both the TPROXY and the REDIRECT path.
    run_iptables -t mangle -A "$TPROXY_MASK_CHAIN" -p udp --dport 53 -j RETURN || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A "$TPROXY_MASK_CHAIN" -p tcp --dport 53 -j RETURN || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A "$TPROXY_MASK_CHAIN" -j MARK --set-mark "$TPROXY_MARK" || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A "$TPROXY_CHAIN" -m mark --mark "$TPROXY_MARK" -p tcp -j TPROXY --on-port "$TPROXY_PORT" --tproxy-mark "$TPROXY_MARK/$TPROXY_MARK" || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A "$TPROXY_CHAIN" -m mark --mark "$TPROXY_MARK" -p udp -j TPROXY --on-port "$TPROXY_PORT" --tproxy-mark "$TPROXY_MARK/$TPROXY_MARK" || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A PREROUTING -m mark --mark "$TPROXY_MARK" -j "$TPROXY_CHAIN" || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A OUTPUT -p tcp -j "$TPROXY_MASK_CHAIN" || { cleanup_tproxy; return 1; }
    run_iptables -t mangle -A OUTPUT -p udp -j "$TPROXY_MASK_CHAIN" || { cleanup_tproxy; return 1; }
    if ! setup_dns_redirect; then
        log "TPROXY is active but DNS still uses the receiver's resolver."
    fi
    log "Transparent backend ready: TPROXY (TCP+UDP)."
    return 0
}

cleanup_redirect() {
    cleanup_dns_redirect
    command -v iptables >/dev/null 2>&1 || return 0
    iptables -t nat -D OUTPUT -p tcp -j "$REDIRECT_CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -F "$REDIRECT_CHAIN" >/dev/null 2>&1 || true
    iptables -t nat -X "$REDIRECT_CHAIN" >/dev/null 2>&1 || true
}

setup_redirect() {
    clear_backend_error
    cleanup_redirect
    redirect_capable || {
        set_backend_error "REDIRECT_SETUP_FAILED" "iptables NAT/REDIRECT support is unavailable."
        return 1
    }
    # Attach the DNS chain first so port 53 is claimed before the catch-all
    # TCP redirect sees it.
    if ! setup_dns_redirect; then
        cleanup_redirect
        set_backend_error "REDIRECT_SETUP_FAILED" "Could not redirect DNS through Xray."
        return 1
    fi
    run_iptables -t nat -N "$REDIRECT_CHAIN" || { cleanup_redirect; set_backend_error "REDIRECT_SETUP_FAILED" "Could not create REDIRECT chain."; return 1; }
    add_transparent_bypass_rules nat "$REDIRECT_CHAIN" || { cleanup_redirect; set_backend_error "REDIRECT_SETUP_FAILED" "Could not install REDIRECT bypass rules."; return 1; }
    run_iptables -t nat -A "$REDIRECT_CHAIN" -p tcp -j REDIRECT --to-ports "$TPROXY_PORT" || { cleanup_redirect; set_backend_error "REDIRECT_SETUP_FAILED" "Could not install TCP REDIRECT target."; return 1; }
    run_iptables -t nat -A OUTPUT -p tcp -j "$REDIRECT_CHAIN" || { cleanup_redirect; set_backend_error "REDIRECT_SETUP_FAILED" "Could not attach TCP REDIRECT to OUTPUT."; return 1; }
    log "Transparent backend ready: REDIRECT (TCP only; UDP remains direct)."
    return 0
}

cleanup_network_backend() {
    # Deliberately not named "backend": POSIX sh has no locals, and this runs
    # from inside `for backend in $backend_list` in start_xray. Reusing the name
    # would overwrite the caller's loop variable.
    cleanup_backend="${NETWORK_BACKEND:-}"
    [ -n "$cleanup_backend" ] ||
        cleanup_backend="$(cat "$BACKEND_FILE" 2>/dev/null || echo '')"
    cleanup_ipv6
    cleanup_bypass_mark
    case "$cleanup_backend" in
        tun) cleanup_dns_redirect; restore_routes ;;
        tproxy) cleanup_tproxy ;;
        redirect) cleanup_redirect ;;
        *)
            restore_routes
            cleanup_tproxy
            cleanup_redirect
            ;;
    esac
}

record_backend() {
    NETWORK_BACKEND="$1"
    printf '%s\n' "$NETWORK_BACKEND" > "$BACKEND_FILE"
    printf "NETWORK_BACKEND='%s'\n" "$NETWORK_BACKEND" >> "$STATE"
    log "Network backend selected: $(echo "$NETWORK_BACKEND" | tr '[:lower:]' '[:upper:]')"
}

configure_backend() {
    backend="$1"
    if ! "$PYTHON" "$PARSER" --set-backend "$CONF" "$backend" "$DEFAULT_DEV" \
        "$(bypass_ip_argument)" "$(server_ip_argument)" >> "$LOG" 2>&1; then
        set_backend_error "BACKEND_CONFIG_FAILED" "Could not configure Xray for backend $backend."
        return 1
    fi
    if ! "$XRAY" run -test -c "$CONF" >> "$LOG" 2>&1; then
        config_detail="$(last_log_line)"
        [ -n "$config_detail" ] || config_detail="Xray rejected backend $backend configuration."
        set_backend_error "CONFIG_INVALID" "$config_detail"
        return 1
    fi
}

stop_core_quiet() {
    if is_running; then
        pid="$(cat "$PIDFILE" 2>/dev/null || echo '')"
        [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
        sleep 1
        if is_running; then
            pid="$(cat "$PIDFILE" 2>/dev/null || echo '')"
            [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
        fi
    fi
    rm -f "$PIDFILE"
}

start_core_for_backend() {
    backend="$1"
    NETWORK_BACKEND="$backend"
    clear_backend_error
    configure_backend "$backend" || return 1
    setup_dns || {
        set_backend_error "DNS_WRITE_FAILED" "Could not safely update $RESOLV."
        return 1
    }
    log "Starting e2xray via $DEFAULT_DEV using backend $(echo "$backend" | tr '[:lower:]' '[:upper:]')"
    "$XRAY" run -c "$CONF" >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"

    case "$backend" in
        tun)
            if ! wait_for_tun; then
                core_detail="$(last_log_line)"
                [ -n "$core_detail" ] || core_detail="Xray did not create $IFACE within 30 seconds."
                set_backend_error "TUN_CREATE_FAILED" "$core_detail"
                stop_core_quiet
                restore_dns
                return 1
            fi
            if ! setup_routes || ! routes_ready || ! is_running; then
                if [ ! -s "$BACKEND_ERROR" ]; then
                    if [ -s "$ROUTE_ERROR" ]; then
                        route_detail="$(tr '\r\n' '  ' < "$ROUTE_ERROR" | cut -c 1-300)"
                        set_backend_error "ROUTE_TABLE_FAILED" "$route_detail"
                    elif ! is_running; then
                        set_backend_error "TUN_CREATE_FAILED" "Xray exited while TUN routing was being installed."
                    else
                        set_backend_error "ROUTE_TABLE_FAILED" "No supported TUN routing mode could be installed."
                    fi
                fi
                restore_routes
                restore_dns
                stop_core_quiet
                return 1
            fi
            setup_bypass_mark || true
            if [ "${PROTOCOL:-}" = "shadowsocks" ]; then
                # The core carries these lookups over TCP, so they must be
                # captured here rather than left to the receiver's resolver.
                if ! setup_dns_redirect; then
                    log "[DNS] WARNING: port 53 could not be captured; Shadowsocks lookups will use the receiver's resolver in the clear."
                fi
            fi
            setup_ipv6 tun
            ;;
        tproxy)
            sleep 1
            if ! is_running; then
                core_detail="$(last_log_line)"
                [ -n "$core_detail" ] || core_detail="Xray exited before TPROXY rules were installed."
                set_backend_error "TPROXY_SETUP_FAILED" "$core_detail"
                restore_dns
                return 1
            fi
            if ! setup_tproxy; then
                restore_dns
                stop_core_quiet
                return 1
            fi
            setup_ipv6 tproxy
            ;;
        redirect)
            sleep 1
            if ! is_running; then
                core_detail="$(last_log_line)"
                [ -n "$core_detail" ] || core_detail="Xray exited before REDIRECT rules were installed."
                set_backend_error "REDIRECT_SETUP_FAILED" "$core_detail"
                restore_dns
                return 1
            fi
            if ! setup_redirect; then
                restore_dns
                stop_core_quiet
                return 1
            fi
            setup_ipv6 redirect
            ;;
    esac
    record_backend "$backend"

    # The core is up and the network is captured. Prove that traffic actually
    # reaches the internet before handing control back, otherwise the receiver
    # is left fully tunnelled through a server that answers nothing.
    if ! tunnel_carries_traffic; then
        set_backend_error "TUNNEL_DEAD" \
            "The tunnel started but no traffic reached the internet through it. The configuration server is not answering."
        return 1
    fi
    return 0
}

is_running() {
    [ -f "$PIDFILE" ] || return 1
    pid="$(cat "$PIDFILE" 2>/dev/null || echo '')"
    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$pid" -gt 1 ] 2>/dev/null || return 1
    kill -0 "$pid" 2>/dev/null || return 1

    if [ -r "/proc/$pid/cmdline" ]; then
        cmdline="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$cmdline" in
            *"/usr/lib/e2xray/bin/xray"*) return 0 ;;
        esac
    fi

    if command -v readlink >/dev/null 2>&1; then
        exe="$(readlink "/proc/$pid/exe" 2>/dev/null || echo '')"
        case "$exe" in
            /usr/lib/e2xray/bin/xray*) return 0 ;;
        esac
    fi
    return 1
}

runtime_state_present() {
    [ -f "$PIDFILE" ] ||
        [ -f "$ACTIVE_PROFILE" ] ||
        [ -f "$RESOLV_BAK" ] ||
        [ -f "$STATE" ] ||
        [ -f "$POLICY_TABLE_OWNED" ] ||
        [ -f "$POLICY_RULE_OWNED" ] ||
        [ -f "$SPLIT_ROUTES_OWNED" ] ||
        [ -f "$BACKEND_FILE" ] ||
        [ -f "$IPV6_OWNED" ]
}

wait_for_tun() {
    attempts=0
    # Cold-starting the 34 MB Go binary can take well over five seconds on
    # older ARMv7 receivers, especially immediately after package install.
    while [ "$attempts" -lt 30 ]; do
        is_running || return 1
        [ -e "/sys/class/net/$IFACE" ] && return 0
        sleep 1
        attempts=$((attempts + 1))
    done
    is_running && [ -e "/sys/class/net/$IFACE" ]
}

start_xray() {
    if is_running; then
        echo "E2XRAY_NOOP=ALREADY_RUNNING"
        return 0
    fi
    rotate_log
    log_environment
    verify_integrity
    # A freshly installed plugin has profiles in config.txt but no selection.
    # Adopt the first one instead of refusing to start.
    if [ -f "$USERCONF" ] && [ -f "$PARSER" ] && find_python; then
        "$PYTHON" "$PARSER" --ensure-selection "$USERCONF" "$SELECTION" \
            >> "$LOG" 2>&1 || true
    fi
    if ! config_present; then
        parser_detail="$(last_log_line)"
        [ -n "$parser_detail" ] || parser_detail="No valid selected configuration was found."
        fail_start "NO_CONFIG" "$parser_detail"
    fi
    if [ ! -x "$XRAY" ]; then
        fail_start "CORE_MISSING" "Missing embedded Xray core: $XRAY"
    fi
    if ! command -v ip >/dev/null 2>&1; then
        log "ip command is missing; TUN/TPROXY policy routing may be unavailable."
    fi

    if runtime_state_present; then
        watchdog_stop
        cleanup_network_backend
        restore_dns
        rm -f "$PIDFILE" "$ACTIVE_PROFILE" "$ROUTE_ERROR" "$STATE" \
            "$POLICY_TABLE_OWNED" "$POLICY_RULE_OWNED" "$SPLIT_ROUTES_OWNED" \
            "$BACKEND_FILE" "$BACKEND_ERROR"
    fi

    save_state
    . "$STATE"
    if [ -z "${DEFAULT_DEV:-}" ]; then
        fail_start "ROUTE_MISSING" "Could not detect the receiver's default network interface."
    fi
    if [ -z "${SERVER_IPS:-}" ] && [ -z "${SERVER_IPS6:-}" ]; then
        if [ -n "${SERVER_IPS_FILTERED:-}" ]; then
            fail_start "SERVER_FILTERED" \
                "$SERVER_ADDRESS resolves only to the ISP filtering sinkhole (${SERVER_IPS_FILTERED}). This configuration's domain is blocked on this connection."
        fi
        fail_start "DNS_FAILED" "Could not resolve the proxy server: $SERVER_ADDRESS"
    fi

    # Must happen while the receiver still routes normally: peer host names are
    # resolved with the untouched resolver and the softcam's live sockets are
    # still readable.
    discover_softcam_bypass

    backend_list=""
    if ensure_tun; then
        backend_list="tun"
        log "Backend probe: TUN is available."
    else
        kernel_release="$(uname -r 2>/dev/null || echo unknown)"
        : > "$TUN_WARNING"
        log "Backend probe: TUN unavailable on kernel $kernel_release; trying transparent fallbacks."
    fi
    if tproxy_capable; then
        backend_list="$backend_list tproxy"
        log "Backend probe: TPROXY is available."
    else
        log "Backend probe: TPROXY unavailable."
    fi
    if redirect_capable; then
        backend_list="$backend_list redirect"
        log "Backend probe: TCP REDIRECT is available."
    else
        log "Backend probe: TCP REDIRECT unavailable."
    fi

    backend_list="$(echo "$backend_list" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ -z "$backend_list" ]; then
        # Naming the missing component matters: on several Vu+/OE-Alliance
        # images neither the TUN driver nor iptables is present at all, and a
        # generic message sends users hunting for a configuration problem that
        # does not exist.
        missing=""
        tun_usable || missing="kernel-module-tun (/dev/net/tun is missing)"
        if ! command -v iptables >/dev/null 2>&1; then
            [ -n "$missing" ] && missing="$missing and "
            missing="${missing}iptables (the command is not installed)"
        fi
        [ -n "$missing" ] || missing="a usable TUN, TPROXY or REDIRECT facility"
        fail_start "NO_NETWORK_BACKEND" "This receiver's image provides no way to capture traffic. Missing: $missing. Run '$0 deps install' over SSH to fix it."
    fi

    last_code="NO_NETWORK_BACKEND"
    last_detail="No backend could be started."
    for backend in $backend_list; do
        log "Attempting network backend: $(echo "$backend" | tr '[:lower:]' '[:upper:]')"
        if start_core_for_backend "$backend"; then
            printf '%s\n' "$PROFILE_ID" > "$ACTIVE_PROFILE"
            chmod 600 "$ACTIVE_PROFILE" 2>/dev/null || true
            rm -f "$BACKEND_ERROR" "$ROUTE_ERROR"
            watchdog_start
            echo "E2XRAY_ACTION=STARTED"
            echo "E2XRAY_BACKEND=$(echo "$backend" | tr '[:lower:]' '[:upper:]')"
            return 0
        fi
        if [ -s "$BACKEND_ERROR" ]; then
            last_line="$(cat "$BACKEND_ERROR" 2>/dev/null || echo '')"
            last_code="${last_line%%|*}"
            last_detail="${last_line#*|}"
        fi
        log "Backend $(echo "$backend" | tr '[:lower:]' '[:upper:]') failed [$last_code]: $last_detail"
        cleanup_network_backend
        restore_dns
        stop_core_quiet
        rm -f "$BACKEND_FILE"
        NETWORK_BACKEND=""
        if [ "$last_code" = "TUNNEL_DEAD" ]; then
            # The capture layer worked - packets reached the core and the core
            # could not get them out. That is the server's fault, and every
            # remaining backend would fail identically after another minute of
            # the receiver being tunnelled into a black hole.
            log "Capture worked but the server answered nothing; skipping the remaining backends."
            break
        fi
    done

    rm -f "$PIDFILE" "$ACTIVE_PROFILE" "$BACKEND_FILE"
    fail_start "$last_code" "$last_detail"
}

stop_xray() {
    watchdog_stop
    running=0
    is_running && running=1

    if [ "$running" -eq 0 ] && ! runtime_state_present; then
        echo "E2XRAY_NOOP=ALREADY_STOPPED"
        return 0
    fi

    cleanup_network_backend
    restore_dns
    if [ "$running" -eq 1 ]; then
        pid="$(cat "$PIDFILE" 2>/dev/null || echo '')"
        [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
        sleep 1
        if is_running; then
            pid="$(cat "$PIDFILE" 2>/dev/null || echo '')"
            [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
        fi
    fi
    rm -f "$PIDFILE" "$ACTIVE_PROFILE" "$ROUTE_ERROR" "$STATE" \
        "$POLICY_TABLE_OWNED" "$POLICY_RULE_OWNED" "$SPLIT_ROUTES_OWNED" \
        "$BACKEND_FILE" "$BACKEND_ERROR" "$IPV6_OWNED"
    log "Stopped e2xray"
    echo "E2XRAY_ACTION=STOPPED"
}

report_dependencies() {
    deps_mode="${1:-report}"
    missing=""

    echo "kernel: $(uname -r 2>/dev/null || echo unknown)   arch: $(uname -m 2>/dev/null || echo unknown)"
    echo

    if tun_usable; then
        echo "TUN ......... present"
    else
        echo "TUN ......... MISSING"
        missing="tun"
    fi

    if command -v iptables >/dev/null 2>&1; then
        echo "iptables .... present ($(command -v iptables))"
        iptables -t nat -L >/dev/null 2>&1 &&
            echo "  NAT ....... works (REDIRECT backend available)" ||
            echo "  NAT ....... NOT working"
        iptables -t mangle -L >/dev/null 2>&1 &&
            echo "  mangle .... works (TPROXY backend possible)" ||
            echo "  mangle .... NOT working"
    else
        echo "iptables .... MISSING"
        missing="$missing iptables"
    fi

    command -v ip >/dev/null 2>&1 &&
        echo "ip .......... present" ||
        echo "ip .......... MISSING"

    echo
    if [ -z "$missing" ]; then
        echo "Nothing is missing. e2xray can capture traffic on this receiver."
        return 0
    fi

    if ! command -v opkg >/dev/null 2>&1; then
        echo "This image does not use opkg; install the missing parts manually."
        return 1
    fi

    echo "Searching this image's feed for the exact package names..."
    opkg update >/dev/null 2>&1 ||
        echo "(opkg update failed; using the cached package list)"

    wanted=""
    case " $missing " in
        *" tun "*)
            # The package is normally versioned, e.g. kernel-module-tun-4.1.20-1.9,
            # so the bare name cannot be assumed to exist.
            tun_pkg="$(opkg list 2>/dev/null |
                awk '$1 ~ /^kernel-module-tun/ {print $1; exit}')"
            if [ -n "$tun_pkg" ]; then
                echo "  $tun_pkg"
                wanted="$wanted $tun_pkg"
            else
                echo "  (no kernel-module-tun package in this feed)"
            fi
            ;;
    esac
    case " $missing " in
        *" iptables "*)
            for pkg_name in iptables iptables-modules iptables-module-xt-tproxy \
                iptables-module-xt-socket iproute2; do
                if opkg list 2>/dev/null |
                    awk -v n="$pkg_name" '$1 == n {found = 1} END {exit !found}'; then
                    echo "  $pkg_name"
                    wanted="$wanted $pkg_name"
                fi
            done
            ;;
    esac

    wanted="$(echo "$wanted" | sed 's/^[[:space:]]*//')"
    if [ -z "$wanted" ]; then
        echo
        echo "This feed offers none of them."
        return 1
    fi

    if [ "$deps_mode" != install ]; then
        echo
        echo "Install them one at a time:"
        for pkg_name in $wanted; do
            echo "  opkg install $pkg_name"
        done
        echo
        echo "Or let this command do it: $0 deps install"
        return 0
    fi

    echo
    # One package per call on purpose. A single opkg invocation listing several
    # names aborts entirely when one of them is absent from the feed, which
    # would also block the packages that are available.
    deps_failed=""
    for pkg_name in $wanted; do
        if opkg install "$pkg_name"; then
            echo "installed: $pkg_name"
        else
            echo "failed: $pkg_name"
            deps_failed="$deps_failed $pkg_name"
        fi
    done

    echo
    if [ -n "$deps_failed" ]; then
        echo "Could not install:$deps_failed"
        echo "If opkg reported a lock error, run this from SSH rather than the"
        echo "on-screen file manager."
    fi
    if ! tun_usable && [ -n "$(echo "$wanted" | grep kernel-module-tun || true)" ]; then
        echo "Reboot now: the TUN module is only picked up on a fresh boot."
    fi
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
    start) acquire_control_lock; start_xray ;;
    stop) acquire_control_lock; stop_xray ;;
    restart) acquire_control_lock; stop_xray; start_xray ;;
    ping) ping_config ;;
    internet) internet_status ;;
    network) network_status ;;
    status) if is_running; then echo "Running"; else echo "Stopped"; fi ;;
    logs) tail -n 120 "$LOG" 2>/dev/null || echo "No log yet." ;;
    write-config) write_config ;;
    install-init) install_init ;;
    deps) report_dependencies "${2:-report}" ;;
    ensure-tun) ensure_tun_action ;;
    env)
        # Support aid: the same environment block that every start writes to
        # the log, printed on demand.
        log_environment
        tail -n 8 "$LOG" 2>/dev/null | sed -n 's/.*\[ENV\] //p'
        ;;
    select-first)
        find_python &&
            "$PYTHON" "$PARSER" --ensure-selection "$USERCONF" "$SELECTION"
        ;;
    softcam)
        # Support aid: shows exactly which card-sharing peers e2xray will keep
        # outside the tunnel, without starting anything.
        discover_softcam_bypass
        echo "Card-sharing IPs   : ${SOFTCAM_BYPASS_IPS:-none detected}"
        echo "Card-sharing ports : ${SOFTCAM_BYPASS_PORTS:-none detected}"
        ;;
    *) echo "Usage: $0 {start|stop|restart|ping|internet|network|status|logs|write-config|install-init|ensure-tun|softcam|env|select-first|deps [install]}"; exit 1 ;;
esac
