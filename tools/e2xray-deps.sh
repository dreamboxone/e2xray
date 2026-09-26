#!/bin/sh
# Reports which traffic-capture facility a receiver is missing and finds the
# exact package names in that image's own feed. Package names are tied to the
# running kernel version, so they cannot be guessed from another receiver.
#
# Usage:  sh e2xray-deps.sh          report only
#         sh e2xray-deps.sh install  report, then install what is missing
PATH="/usr/sbin:/sbin:$PATH"
export PATH

MODE="${1:-report}"
missing=""

echo "kernel: $(uname -r)   arch: $(uname -m)"
echo

if [ -c /dev/net/tun ]; then
    echo "TUN ......... present"
else
    echo "TUN ......... MISSING"
    missing="tun"
fi

if command -v iptables >/dev/null 2>&1; then
    echo "iptables .... present ($(command -v iptables))"
    if iptables -t nat -L >/dev/null 2>&1; then
        echo "  NAT ....... works (REDIRECT backend available)"
    else
        echo "  NAT ....... NOT working"
    fi
    if iptables -t mangle -L >/dev/null 2>&1; then
        echo "  mangle .... works (TPROXY backend possible)"
    else
        echo "  mangle .... NOT working"
    fi
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
    exit 0
fi

command -v opkg >/dev/null 2>&1 || {
    echo "This image does not use opkg; install the missing parts manually."
    exit 1
}

echo "Searching this image's feed for the exact package names..."
opkg update >/dev/null 2>&1 || echo "(opkg update failed; using the cached list)"

wanted=""
case " $missing " in
    *" tun "*)
        # The real package is usually versioned, e.g. kernel-module-tun-4.1.20-1.9.
        tun_pkg="$(opkg list 2>/dev/null | awk '$1 ~ /^kernel-module-tun/ {print $1; exit}')"
        if [ -n "$tun_pkg" ]; then
            echo "  TUN module .... $tun_pkg"
            wanted="$wanted $tun_pkg"
        else
            echo "  TUN module .... not offered by this feed"
        fi
        ;;
esac
case " $missing " in
    *" iptables "*)
        for name in iptables iptables-modules iptables-module-xt-tproxy \
            iptables-module-xt-socket iproute2; do
            if opkg list 2>/dev/null | awk -v n="$name" '$1 == n {found=1} END {exit !found}'; then
                echo "  $name"
                wanted="$wanted $name"
            fi
        done
        ;;
esac

wanted="$(echo "$wanted" | sed 's/^ *//')"
[ -n "$wanted" ] || { echo; echo "This feed offers none of them."; exit 1; }

echo
echo "Install command for this receiver:"
echo "  opkg install $wanted"

if [ "$MODE" = install ]; then
    echo
    # The on-screen file manager holds this lock while it runs opkg itself.
    if ! opkg install $wanted; then
        echo
        echo "Install failed. If it reported a lock error, run this from SSH"
        echo "instead of the on-screen file manager."
        exit 1
    fi
    echo
    echo "Done. Reboot now: the TUN module is only picked up on a fresh boot."
fi
