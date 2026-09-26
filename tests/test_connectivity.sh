#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
CTL="$ROOT/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"
TMP="${TMPDIR:-/tmp}/e2xray-connectivity-test.$$"

export E2XRAY_RUNTIME="$TMP/run"
mkdir -p "$E2XRAY_RUNTIME"
FAKE="$TMP/bin"
mkdir -p "$FAKE"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

cat > "$FAKE/ip" <<'SH'
#!/bin/sh
case "${E2XRAY_TEST_NETWORK:-online}:$*" in
  online:"route show default") echo "default via 192.168.1.1 dev eth0" ;;
  online:"-4 addr show dev eth0") printf "2: eth0: <UP> mtu 1500\n    inet 192.168.1.50/24 brd 192.168.1.255 scope global eth0\n" ;;
  offline:"route show default") echo "default via 192.168.1.1 dev eth0" ;;
  offline:"-4 addr show dev "*) exit 0 ;;
  *) exit 0 ;;
esac
SH
chmod +x "$FAKE/ip"

cat > "$FAKE/ifconfig" <<'SH'
#!/bin/sh
exit 1
SH
chmod +x "$FAKE/ifconfig"

cat > "$FAKE/ping" <<'SH'
#!/bin/sh
exit 1
SH
chmod +x "$FAKE/ping"

cat > "$FAKE/sleep" <<'SH'
#!/bin/sh
exit 0
SH
chmod +x "$FAKE/sleep"

cat > "$FAKE/curl" <<'SH'
#!/bin/sh
last=""
for arg in "$@"; do last="$arg"; done
case "${E2XRAY_TEST_INTERNET:-partial}:$last" in
  partial:*google.com*) exit 1 ;;
  partial:*cloudflare.com*) exit 0 ;;
  partial:*) exit 1 ;;
  offline:*) exit 1 ;;
  online:*) exit 0 ;;
esac
SH
chmod +x "$FAKE/curl"

PATH="$FAKE:/usr/bin:/bin"
export PATH

out="$(E2XRAY_TEST_NETWORK=online "$CTL" network)"
printf '%s\n' "$out" | grep -q '^E2XRAY_LAN=ONLINE$'
printf '%s\n' "$out" | grep -q '^E2XRAY_LAN_IFACE=eth0$'
printf '%s\n' "$out" | grep -q '^E2XRAY_LAN_IPV4=192.168.1.50$'

set +e
out="$(E2XRAY_TEST_NETWORK=offline "$CTL" network)"
rc=$?
set -e
[ "$rc" -ne 0 ]
printf '%s\n' "$out" | grep -q '^E2XRAY_LAN=OFFLINE$'

out="$(E2XRAY_TEST_NETWORK=online E2XRAY_TEST_INTERNET=partial "$CTL" internet)"
printf '%s\n' "$out" | grep -q '^E2XRAY_NET=ONLINE$'

set +e
out="$(E2XRAY_TEST_NETWORK=online E2XRAY_TEST_INTERNET=offline "$CTL" internet)"
rc=$?
set -e
[ "$rc" -ne 0 ]
printf '%s\n' "$out" | grep -q '^E2XRAY_NET=OFFLINE$'

set +e
out="$(E2XRAY_TEST_NETWORK=offline E2XRAY_TEST_INTERNET=online "$CTL" internet)"
rc=$?
set -e
[ "$rc" -ne 0 ]
printf '%s\n' "$out" | grep -q '^E2XRAY_NET=OFFLINE$'

echo "Connectivity tests passed."
