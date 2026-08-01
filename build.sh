#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CONTROL_FILE="$PROJECT_DIR/DEBIAN/control"

# New syntax: ./build.sh [deb|ipk] [arm64|mipsel] [output-directory]
# Compatibility syntax: ./build.sh [arm64|mipsel] [output-directory]
# A single non-architecture argument keeps the old ARM64 output-dir syntax.
case "${1:-}" in
    deb|ipk)
        PACKAGE_FORMAT="$1"
        TARGET_ARCH="${2:-arm64}"
        OUTPUT_DIR="${3:-$(dirname "$PROJECT_DIR")}"
        ;;
    arm64|mipsel)
        PACKAGE_FORMAT="deb"
        TARGET_ARCH="$1"
        OUTPUT_DIR="${2:-$(dirname "$PROJECT_DIR")}"
        ;;
    "")
        PACKAGE_FORMAT="deb"
        TARGET_ARCH="arm64"
        OUTPUT_DIR="$(dirname "$PROJECT_DIR")"
        ;;
    *)
        PACKAGE_FORMAT="deb"
        TARGET_ARCH="arm64"
        OUTPUT_DIR="$1"
        ;;
esac

case "$PACKAGE_FORMAT" in
    deb|ipk) ;;
    *)
        echo "Unsupported package format: $PACKAGE_FORMAT" >&2
        exit 1
        ;;
esac

case "$TARGET_ARCH" in
    arm64)
        CORE_REL="cores/arm64/xray"
        ;;
    mipsel)
        CORE_REL="cores/mipsel/xray"
        ;;
    *)
        echo "Unsupported architecture: $TARGET_ARCH" >&2
        exit 1
        ;;
esac

CORE_FILE="$PROJECT_DIR/$CORE_REL"
CHECKSUMS="$PROJECT_DIR/cores/SHA256SUMS"

for command_name in sha256sum tar gzip ar; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "$command_name is required to build the package." >&2
        exit 1
    }
done

if [ "$PACKAGE_FORMAT" = "deb" ]; then
    command -v dpkg-deb >/dev/null 2>&1 || {
        echo "dpkg-deb is required to build the Debian package." >&2
        exit 1
    }
fi

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
OUTPUT_DIR="$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)"

if [ "$PACKAGE_FORMAT" = "deb" ]; then
    PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${TARGET_ARCH}.deb"
    dpkg-deb --build --root-owner-group -Zgzip -z9 \
        "$STAGING" "$OUTPUT_DIR/$PACKAGE"
    echo "$OUTPUT_DIR/$PACKAGE"
    exit 0
fi

PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${TARGET_ARCH}.ipk"
IPK_WORK="$STAGING/.ipk"
CONTROL_ARCHIVE="$IPK_WORK/control.tar.gz"
DATA_ARCHIVE="$IPK_WORK/data.tar.gz"
PACKAGE_PATH="$OUTPUT_DIR/$PACKAGE"

mkdir -p "$IPK_WORK"
printf '2.0\n' > "$IPK_WORK/debian-binary"
mv "$STAGING/DEBIAN" "$STAGING/CONTROL"

(
    cd "$STAGING/CONTROL"
    tar --owner=0 --group=0 -cf - . | gzip -9n > "$CONTROL_ARCHIVE"
)
(
    cd "$STAGING"
    tar --owner=0 --group=0 \
        --exclude='./CONTROL' \
        --exclude='./.ipk' \
        -cf - . | gzip -9n > "$DATA_ARCHIVE"
)
(
    cd "$IPK_WORK"
    rm -f "$PACKAGE_PATH"
    ar r "$PACKAGE_PATH" debian-binary control.tar.gz data.tar.gz >/dev/null
)
echo "$PACKAGE_PATH"
