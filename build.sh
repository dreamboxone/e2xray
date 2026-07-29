#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_DIR="${1:-$(dirname "$PROJECT_DIR")}"
PACKAGE="enigma2-plugin-extensions-e2xray_0.3.2_arm64.deb"

command -v dpkg-deb >/dev/null 2>&1 || {
    echo "dpkg-deb is required to build the package." >&2
    exit 1
}

chmod 755 "$PROJECT_DIR/DEBIAN/postinst"
chmod 755 "$PROJECT_DIR/DEBIAN/prerm"
chmod 755 "$PROJECT_DIR/etc/init.d/e2xray"
chmod 755 "$PROJECT_DIR/usr/lib/e2xray/bin/xray"
chmod 755 "$PROJECT_DIR/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"

mkdir -p "$OUTPUT_DIR"
dpkg-deb --build --root-owner-group "$PROJECT_DIR" "$OUTPUT_DIR/$PACKAGE"
echo "$OUTPUT_DIR/$PACKAGE"
