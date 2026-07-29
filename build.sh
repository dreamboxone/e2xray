#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_DIR="${1:-$(dirname "$PROJECT_DIR")}"
CONTROL_FILE="$PROJECT_DIR/DEBIAN/control"

command -v dpkg-deb >/dev/null 2>&1 || {
    echo "dpkg-deb is required to build the package." >&2
    exit 1
}

control_value() {
    sed -n "s/^$1:[[:space:]]*//p" "$CONTROL_FILE" | head -n 1
}

PACKAGE_NAME="$(control_value Package)"
PACKAGE_VERSION="$(control_value Version)"
PACKAGE_ARCH="$(control_value Architecture)"

if [ -z "$PACKAGE_NAME" ] || [ -z "$PACKAGE_VERSION" ] || [ -z "$PACKAGE_ARCH" ]; then
    echo "Package, Version, and Architecture are required in DEBIAN/control." >&2
    exit 1
fi

PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_ARCH}.deb"

chmod 755 "$PROJECT_DIR/DEBIAN/postinst"
chmod 755 "$PROJECT_DIR/DEBIAN/prerm"
chmod 755 "$PROJECT_DIR/etc/init.d/e2xray"
chmod 755 "$PROJECT_DIR/usr/lib/e2xray/bin/xray"
chmod 755 "$PROJECT_DIR/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"

mkdir -p "$OUTPUT_DIR"
dpkg-deb --build --root-owner-group "$PROJECT_DIR" "$OUTPUT_DIR/$PACKAGE"
echo "$OUTPUT_DIR/$PACKAGE"
