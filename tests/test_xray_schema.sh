#!/bin/sh
# Validate every configuration this plugin can generate against a real Xray core.
#
#   sh tests/test_xray_schema.sh [path-to-xray]
#
# Reading the code cannot tell you whether a field name is one the core accepts.
# This asks the core itself: each generated configuration is run through
# `xray run -test`, which parses and builds it exactly as a real start would.
#
# Any x86_64 Linux Xray of the SAME version the plugin ships is fine; the schema
# is what is being tested, not the traffic.
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PARSER="$ROOT/usr/lib/enigma2/python/Plugins/Extensions/e2xray/proxy_config.py"

XRAY="${1:-}"
if [ -z "$XRAY" ]; then
    for candidate in "$ROOT/xray" ./xray /usr/lib/e2xray/bin/xray; do
        [ -x "$candidate" ] && { XRAY="$candidate"; break; }
    done
fi
[ -n "$XRAY" ] && [ -x "$XRAY" ] || {
    echo "No Xray binary found. Pass one: sh tests/test_xray_schema.sh /path/to/xray" >&2
    exit 2
}

PYTHON=""
for candidate in python3 python; do
    command -v "$candidate" >/dev/null 2>&1 && { PYTHON="$candidate"; break; }
done
[ -n "$PYTHON" ] || { echo "python is required" >&2; exit 2; }

echo "Core: $("$XRAY" version 2>/dev/null | head -n 1)"
# Creating a TUN device needs CAP_NET_ADMIN, so as an ordinary user the TUN
# rows fail on permissions rather than on anything in the configuration. Those
# are reported as SKIPPED, not as failures.
if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
    echo "Note: not running as root, so TUN inbounds cannot be instantiated."
    echo "      Re-run with sudo to cover them: sudo sh tests/test_xray_schema.sh"
fi
echo

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Every protocol, every transport, every security mode the parser can emit.
cat > "$WORK/links.txt" <<'LINKS'
vless-ws-tls|vless://11111111-1111-4111-8111-111111111111@a.example:443?encryption=none&security=tls&type=ws&host=h.example&path=%2Fp&sni=s.example&fp=chrome&alpn=h2%2Chttp%2F1.1#vless-ws-tls
vless-ws-pinned|vless://11111111-1111-4111-8111-111111111111@a.example:443?encryption=none&security=tls&type=ws&path=%2F&pinnedPeerCertSha256=2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881#vless-ws-pinned
vless-grpc-reality|vless://11111111-1111-4111-8111-111111111111@a.example:443?encryption=none&security=reality&type=grpc&serviceName=svc&pbk=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8&sid=abcd&spx=%2F&fp=chrome&sni=s.example#vless-grpc-reality
vless-xhttp|vless://11111111-1111-4111-8111-111111111111@a.example:443?encryption=none&security=tls&type=xhttp&path=%2F&mode=auto&host=h.example&extra=%7B%22xPaddingBytes%22%3A%22100-1000%22%7D#vless-xhttp
vless-raw-none|vless://11111111-1111-4111-8111-111111111111@a.example:443?encryption=none&type=tcp#vless-raw-none
vless-flow|vless://11111111-1111-4111-8111-111111111111@a.example:443?encryption=none&security=reality&type=tcp&pbk=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8&sid=ab&flow=xtls-rprx-vision&sni=s.example#vless-flow
vless-ipv6|vless://11111111-1111-4111-8111-111111111111@[2001:db8::1]:443?encryption=none&security=tls&type=ws&path=%2F&sni=s.example#vless-ipv6
trojan-tls|trojan://password@a.example:443?security=tls&type=tcp&sni=s.example#trojan-tls
trojan-ws|trojan://password@a.example:443?security=tls&type=ws&path=%2Fp&sni=s.example#trojan-ws
shadowsocks|ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ@203.0.113.4:8388#shadowsocks
LINKS

# VMess is base64 JSON, so it is built rather than written out by hand.
"$PYTHON" - "$WORK" <<'PY'
import base64, json, sys
work = sys.argv[1]
cases = [
    ("vmess-ws-tls", {"v":"2","add":"a.example","port":"443",
                      "id":"22222222-2222-4222-8222-222222222222","scy":"auto",
                      "net":"ws","type":"none","host":"h.example","path":"/p",
                      "tls":"tls","sni":"s.example","fp":"chrome","ps":"vmess-ws"}),
    ("vmess-tcp", {"v":"2","add":"a.example","port":"443",
                   "id":"22222222-2222-4222-8222-222222222222","scy":"auto",
                   "net":"tcp","type":"none","ps":"vmess-tcp"}),
]
with open(work + "/links.txt", "a") as out:
    for name, payload in cases:
        link = "vmess://" + base64.b64encode(
            json.dumps(payload).encode()).decode()
        out.write("%s|%s\n" % (name, link))
PY

pass_count=0
fail_count=0
skip_count=0
failures=""

while IFS='|' read -r name link; do
    [ -n "$name" ] || continue
    printf '%s\n' "$link" > "$WORK/config.txt"
    rm -f "$WORK/selected"
    "$PYTHON" "$PARSER" --ensure-selection "$WORK/config.txt" "$WORK/selected" \
        >/dev/null 2>&1
    if ! "$PYTHON" "$PARSER" "$WORK/config.txt" "$WORK/selected" \
        "$WORK/user.conf" "$WORK/xray.json" >"$WORK/parse.err" 2>&1; then
        fail_count=$((fail_count + 1))
        failures="$failures\n  $name (parse): $(head -n 2 "$WORK/parse.err")"
        printf '  %-22s %-9s PARSE FAILED\n' "$name" "-"
        continue
    fi
    for backend in tun tproxy redirect; do
        cp "$WORK/xray.json" "$WORK/test.json"
        # Same arguments the control script passes on a real start: interface,
        # card-sharing bypass addresses, and the resolved server address.
        "$PYTHON" "$PARSER" --set-backend "$WORK/test.json" "$backend" eth0 \
            "185.10.20.30" "203.0.113.9" >/dev/null 2>&1
        if "$XRAY" run -test -c "$WORK/test.json" >"$WORK/out" 2>&1; then
            pass_count=$((pass_count + 1))
            printf '  %-22s %-9s OK\n' "$name" "$backend"
        else
            # Informational and deprecation lines are noise; the real cause is
            # whatever survives after they are removed.
            detail="$(sed -e '/\[Info\]/d' -e '/\[Warning\]/d' -e '/^Xray /d' \
                -e '/^A unified/d' -e '/^[[:space:]]*$/d' "$WORK/out" |
                head -n 2 | tr '\n' ' ')"
            case "$detail" in
                *"operation not permitted"*|*"permission denied"*)
                    skip_count=$((skip_count + 1))
                    printf '  %-22s %-9s SKIPPED (needs root)\n' "$name" "$backend"
                    ;;
                *)
                    fail_count=$((fail_count + 1))
                    [ -n "$detail" ] || detail="(core exited non-zero with no message)"
                    failures="$failures\n  $name / $backend: $detail"
                    printf '  %-22s %-9s FAILED\n' "$name" "$backend"
                    ;;
            esac
        fi
    done
done < "$WORK/links.txt"

echo
echo "=============================================="
echo "passed: $pass_count   failed: $fail_count   skipped: $skip_count"
if [ "$fail_count" -ne 0 ]; then
    printf 'failures:%b\n' "$failures"
    exit 1
fi
if [ "$skip_count" -ne 0 ]; then
    echo "Every configuration the core could instantiate was accepted."
    echo "Re-run with sudo to cover the TUN rows as well."
else
    echo "Every generated configuration is accepted by the core."
fi
