#!/bin/sh
set -eu
cd "$(dirname "$0")/../dist"
status=0
for f in *.deb *.ipk; do
    printf '%-58s ' "$f"
    if openssl dgst -sha256 -verify e2xray-signing-public.pem \
        -signature "$f.sig" "$f" 2>/dev/null; then
        :
    else
        echo "SIGNATURE FAILED"
        status=1
    fi
done
echo "--- readable source or bytecode inside packages:"
leak=0
for f in *.deb; do
    if dpkg-deb --fsys-tarfile "$f" 2>/dev/null |
        tar -tf - 2>/dev/null |
        grep -E '\.pyc$|\.pyo$|__pycache__' >/dev/null; then
        echo "$f: BYTECODE PRESENT"
        leak=1
    fi
done
[ "$leak" -eq 0 ] && echo "none found"
exit "$status"
