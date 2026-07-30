#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CONTROL_FILE="$PROJECT_DIR/DEBIAN/control"

# New syntax: ./build.sh [arm64|mipsel] [output-directory]
# A single non-architecture argument keeps the old ARM64 output-dir syntax.
case "${1:-}" in
    arm64|mipsel)
        TARGET_ARCH="$1"
        OUTPUT_DIR="${2:-$(dirname "$PROJECT_DIR")}"
        ;;
    "")
        TARGET_ARCH="arm64"
        OUTPUT_DIR="$(dirname "$PROJECT_DIR")"
        ;;
    *)
        TARGET_ARCH="arm64"
        OUTPUT_DIR="$1"
        ;;
esac

case "$TARGET_ARCH" in
    arm64)
        CORE_REL="cores/arm64/xray"
        ;;
    mipsel)
        CORE_REL="cores/mipsel/xray"
        ;;
esac

CORE_FILE="$PROJECT_DIR/$CORE_REL"
CHECKSUMS="$PROJECT_DIR/cores/SHA256SUMS"

for command_name in dpkg-deb sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "$command_name is required to build the package." >&2
        exit 1
    }
done

control_value() {
    sed -n "s/^$1:[[:space:]]*//p" "$CONTROL_FILE" | head -n 1
}

PACKAGE_NAME="$(control_value Package)"
PACKAGE_VERSION="$(control_value Version)"

if [ -z "$PACKAGE_NAME" ] || [ -z "$PACKAGE_VERSION" ]; then
    echo "Package and Version are required in DEBIAN/control." >&2
    exit 1
fi

[ -s "$CORE_FILE" ] || {
    echo "The $TARGET_ARCH Xray core is missing: $CORE_REL" >&2
    exit 1
}

EXPECTED_HASH="$(
    awk -v path="$CORE_REL" '$2 == path { print $1 }' "$CHECKSUMS"
)"
ACTUAL_HASH="$(sha256sum "$CORE_FILE" | awk '{ print $1 }')"
if [ -z "$EXPECTED_HASH" ] || [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
    echo "Xray core checksum mismatch for $TARGET_ARCH." >&2
    exit 1
fi

PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${TARGET_ARCH}.deb"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

for directory in DEBIAN etc root usr; do
    cp -a "$PROJECT_DIR/$directory" "$STAGING/"
done

sed -i \
    "s/^Architecture:[[:space:]].*/Architecture: $TARGET_ARCH/" \
    "$STAGING/DEBIAN/control"

mkdir -p "$STAGING/usr/lib/e2xray/bin"
cp "$CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray"

chmod 755 "$STAGING/DEBIAN/postinst"
chmod 755 "$STAGING/DEBIAN/prerm"
chmod 755 "$STAGING/DEBIAN/postrm"
chmod 755 "$STAGING/etc/init.d/e2xray"
chmod 755 "$STAGING/usr/lib/e2xray/bin/xray"
chmod 755 "$STAGING/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"

mkdir -p "$OUTPUT_DIR"
dpkg-deb --build --root-owner-group -Zgzip -z9 \
    "$STAGING" "$OUTPUT_DIR/$PACKAGE"
echo "$OUTPUT_DIR/$PACKAGE"
