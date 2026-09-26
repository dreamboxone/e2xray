#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CONTROL_FILE="$PROJECT_DIR/DEBIAN/control"
VERSION_SOURCE="$PROJECT_DIR/usr/lib/enigma2/python/Plugins/Extensions/e2xray/__init__.py"

# New syntax: ./build.sh [deb|ipk] ARCHITECTURE [output-directory]
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
    mips-universal)
        if [ "$PACKAGE_FORMAT" != "ipk" ]; then
            echo "The universal MIPS target is supported only as an IPK package." >&2
            exit 1
        fi
        CORE_REL="cores/mipsel/xray"
        ;;
    deb-universal)
        if [ "$PACKAGE_FORMAT" != "deb" ]; then
            echo "The universal DEB target must use the deb package format." >&2
            exit 1
        fi
        CORE_REL="cores/arm64/xray"
        ;;
    armv7ahf-vfp-neon|armv7ahf-neon|cortexa15hf-neon-vfpv4)
        if [ "$PACKAGE_FORMAT" != "ipk" ]; then
            echo "ARMv7 targets are supported only as IPK packages." >&2
            exit 1
        fi
        CORE_REL="cores/armv7/xray"
        ;;
    armv7-universal)
        if [ "$PACKAGE_FORMAT" != "ipk" ]; then
            echo "The universal ARMv7 target is supported only as an IPK package." >&2
            exit 1
        fi
        CORE_REL="cores/armv7/xray"
        ;;
    *)
        echo "Unsupported architecture: $TARGET_ARCH" >&2
        exit 1
        ;;
esac

CORE_FILE="$PROJECT_DIR/$CORE_REL"
CHECKSUMS="$PROJECT_DIR/cores/SHA256SUMS"
MIPS64_CORE_REL="cores/mips64le/xray"
ARMV7_CORE_REL="cores/armv7/xray"

for command_name in sha256sum tar gzip; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "$command_name is required to build the package." >&2
        exit 1
    }
done

if command -v ar >/dev/null 2>&1; then
    AR_MODE="native"
elif command -v python3 >/dev/null 2>&1 &&
    python3 -c 'import sys' >/dev/null 2>&1 &&
    [ -f "$PROJECT_DIR/tools/ar_archive.py" ]; then
    AR_MODE="python"
    AR_PYTHON="python3"
elif command -v python >/dev/null 2>&1 &&
    python -c 'import sys' >/dev/null 2>&1 &&
    [ -f "$PROJECT_DIR/tools/ar_archive.py" ]; then
    AR_MODE="python"
    AR_PYTHON="python"
else
    echo "ar or python3 is required to build an IPK package." >&2
    exit 1
fi

if command -v dpkg-deb >/dev/null 2>&1; then
    DPKG_DEB_MODE="native"
else
    DPKG_DEB_MODE="portable"
fi

control_value() {
    sed -n "s/^$1:[[:space:]]*//p" "$CONTROL_FILE" | head -n 1
}

PACKAGE_NAME="$(control_value Package)"
PACKAGE_VERSION="$(sed -n 's/^PLUGIN_VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$VERSION_SOURCE" | head -n 1)"

if [ -z "$PACKAGE_NAME" ] || [ -z "$PACKAGE_VERSION" ]; then
    echo "Package name and PLUGIN_VERSION are required." >&2
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

if [ "$TARGET_ARCH" = "mips-universal" ] ||
    [ "$TARGET_ARCH" = "deb-universal" ]; then
    MIPS64_CORE_FILE="$PROJECT_DIR/$MIPS64_CORE_REL"
    [ -s "$MIPS64_CORE_FILE" ] || {
        echo "The MIPS64 little-endian Xray core is missing: $MIPS64_CORE_REL" >&2
        exit 1
    }
    MIPS64_EXPECTED_HASH="$(
        awk -v path="$MIPS64_CORE_REL" '$2 == path { print $1 }' "$CHECKSUMS"
    )"
    MIPS64_ACTUAL_HASH="$(sha256sum "$MIPS64_CORE_FILE" | awk '{ print $1 }')"
    if [ -z "$MIPS64_EXPECTED_HASH" ] ||
        [ "$MIPS64_ACTUAL_HASH" != "$MIPS64_EXPECTED_HASH" ]; then
        echo "Xray core checksum mismatch for MIPS64 little-endian." >&2
        exit 1
    fi
fi

if [ "$TARGET_ARCH" = "deb-universal" ]; then
    ARMV7_CORE_FILE="$PROJECT_DIR/$ARMV7_CORE_REL"
    [ -s "$ARMV7_CORE_FILE" ] || {
        echo "The ARMv7 Xray core is missing: $ARMV7_CORE_REL" >&2
        exit 1
    }
    ARMV7_EXPECTED_HASH="$(
        awk -v path="$ARMV7_CORE_REL" '$2 == path { print $1 }' "$CHECKSUMS"
    )"
    ARMV7_ACTUAL_HASH="$(sha256sum "$ARMV7_CORE_FILE" | awk '{ print $1 }')"
    if [ -z "$ARMV7_EXPECTED_HASH" ] ||
        [ "$ARMV7_ACTUAL_HASH" != "$ARMV7_EXPECTED_HASH" ]; then
        echo "Xray core checksum mismatch for ARMv7." >&2
        exit 1
    fi

    MIPS32_CORE_FILE="$PROJECT_DIR/cores/mipsel/xray"
    MIPS32_EXPECTED_HASH="$(
        awk '$2 == "cores/mipsel/xray" { print $1 }' "$CHECKSUMS"
    )"
    MIPS32_ACTUAL_HASH="$(sha256sum "$MIPS32_CORE_FILE" | awk '{ print $1 }')"
    if [ -z "$MIPS32_EXPECTED_HASH" ] ||
        [ "$MIPS32_ACTUAL_HASH" != "$MIPS32_EXPECTED_HASH" ]; then
        echo "Xray core checksum mismatch for MIPS32 little-endian." >&2
        exit 1
    fi
fi

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

for directory in DEBIAN etc usr; do
    cp -a "$PROJECT_DIR/$directory" "$STAGING/"
done

# Never ship development bytecode. A stale raw .pyc can leak readable source
# even when the corresponding .py file is obfuscated in the protected build.
find "$STAGING" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
if find "$STAGING" -type f \( -name '*.pyc' -o -name '*.pyo' \) -print | grep -q .; then
    echo "Refusing to build: Python bytecode remains in staging." >&2
    exit 1
fi
# Files copied from Windows/DrvFS can carry permissive or setgid directory
# bits into staging. dpkg-deb rejects a control directory outside 0755-0775.
# GNU chmod preserves setgid on directories when only a numeric mode is used,
# so clear special bits explicitly before applying the normal permissions.
chmod u-s,g-s "$STAGING/DEBIAN" 2>/dev/null || true
chmod 755 "$STAGING/DEBIAN"

PACKAGE_ARCH="$TARGET_ARCH"
PACKAGE_FILE_ARCH="$TARGET_ARCH"
if [ "$TARGET_ARCH" = "armv7-universal" ]; then
    PACKAGE_ARCH="all"
    PACKAGE_FILE_ARCH="all"
    cp "$PROJECT_DIR/packaging/armv7-universal/preinst" "$STAGING/DEBIAN/preinst"
elif [ "$TARGET_ARCH" = "mips-universal" ]; then
    PACKAGE_ARCH="all"
    PACKAGE_FILE_ARCH="mips-all"
    cp "$PROJECT_DIR/packaging/mips-universal/preinst" "$STAGING/DEBIAN/preinst"
elif [ "$TARGET_ARCH" = "deb-universal" ]; then
    PACKAGE_ARCH="all"
    PACKAGE_FILE_ARCH="all"
    cp "$PROJECT_DIR/packaging/deb-universal/preinst" "$STAGING/DEBIAN/preinst"
fi

sed -i \
    -e "s/^Architecture:[[:space:]].*/Architecture: $PACKAGE_ARCH/" \
    -e "s/^Version:[[:space:]].*/Version: $PACKAGE_VERSION/" \
    "$STAGING/DEBIAN/control"

if [ "$PACKAGE_FORMAT" = "ipk" ]; then
    # Ask opkg for the image-matched TUN module and full iproute2 when its feed
    # is reachable, without blocking installation on older receiver feeds.
    # Do not invoke opkg recursively while its package-manager lock is held.
    sed -i '/^Recommends:[[:space:]]/d' "$STAGING/DEBIAN/control"
    # iptables covers the TPROXY/REDIRECT fallbacks that receivers without a
    # TUN driver depend on. Several Vu+/OE-Alliance images ship none of these
    # by default even though their feed carries all of them.
    sed -i '/^Depends:[[:space:]]/a Recommends: kernel-module-tun, iproute2, iptables, iptables-modules' \
        "$STAGING/DEBIAN/control"
fi

mkdir -p "$STAGING/usr/lib/e2xray/bin"
if [ "$TARGET_ARCH" = "mips-universal" ]; then
    cp "$CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray-mips32le"
    cp "$MIPS64_CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray-mips64le"
elif [ "$TARGET_ARCH" = "deb-universal" ]; then
    cp "$CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray-arm64"
    cp "$ARMV7_CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray-armv7"
    cp "$MIPS32_CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray-mips32le"
    cp "$MIPS64_CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray-mips64le"
else
    cp "$CORE_FILE" "$STAGING/usr/lib/e2xray/bin/xray"
fi

# Plain-text version marker. The Python sources are obfuscated in a protected
# build, so PLUGIN_VERSION cannot be read back from __init__.py on the
# receiver; e2xrayctl.sh reads this file when writing the log header.
printf '%s\n' "$PACKAGE_VERSION" > "$STAGING/usr/lib/e2xray/version"
chmod 644 "$STAGING/usr/lib/e2xray/version"

chmod 755 "$STAGING/DEBIAN/postinst"
chmod 755 "$STAGING/DEBIAN/prerm"
chmod 755 "$STAGING/DEBIAN/postrm"
if [ -f "$STAGING/DEBIAN/preinst" ]; then
    chmod 755 "$STAGING/DEBIAN/preinst"
fi
chmod 755 "$STAGING/etc/init.d/e2xray"
chmod 755 "$STAGING/usr/lib/e2xray/bin/"xray*
chmod 755 "$STAGING/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"

# Protected build is the default and cannot be accidentally disabled.
# Readable repository source is copied to staging, then Python is obfuscated,
# critical files are signed in an RSA/SHA-256 manifest, and the final package
# receives detached SHA-256/RSA signatures. The private key never enters the
# package. Unprotected output is allowed only through the explicit development
# escape hatch E2XRAY_ALLOW_UNPROTECTED=1.
PROTECTED_BUILD=1
if [ "${E2XRAY_ALLOW_UNPROTECTED:-0}" = "1" ]; then
    PROTECTED_BUILD=0
    echo "WARNING: building an UNPROTECTED development package." >&2
elif [ "${E2XRAY_PROTECT:-1}" = "0" ]; then
    echo "Refusing unprotected build. Set E2XRAY_ALLOW_UNPROTECTED=1 only for local development." >&2
    exit 1
fi

if [ "$PROTECTED_BUILD" = "1" ]; then
    PROTECT_PYTHON=""
    if command -v python3 >/dev/null 2>&1; then
        PROTECT_PYTHON="python3"
    elif command -v python >/dev/null 2>&1 &&
        python -c 'import pathlib' >/dev/null 2>&1; then
        PROTECT_PYTHON="python"
    fi
    [ -n "$PROTECT_PYTHON" ] || {
        echo "Python 3 is required for protected builds." >&2
        exit 1
    }
    command -v openssl >/dev/null 2>&1 || {
        echo "openssl is required for protected builds." >&2
        exit 1
    }

    DEFAULT_SIGNING_KEY="${HOME:-}/.e2xray-keys/e2xray-signing.pem"
    E2XRAY_SIGNING_KEY="${E2XRAY_SIGNING_KEY:-$DEFAULT_SIGNING_KEY}"
    [ -n "$E2XRAY_SIGNING_KEY" ] && [ -f "$E2XRAY_SIGNING_KEY" ] || {
        echo "Protected build requires the RSA private key." >&2
        echo "Expected: ${DEFAULT_SIGNING_KEY:-<set E2XRAY_SIGNING_KEY>}" >&2
        exit 1
    }

    "$PROTECT_PYTHON" "$PROJECT_DIR/tools/obfuscate_py.py" \
        "$STAGING/usr/lib/enigma2/python/Plugins/Extensions/e2xray/__init__.py" \
        "$STAGING/usr/lib/enigma2/python/Plugins/Extensions/e2xray/plugin.py" \
        "$STAGING/usr/lib/enigma2/python/Plugins/Extensions/e2xray/proxy_config.py"

    "$PROTECT_PYTHON" "$PROJECT_DIR/tools/build_integrity.py" \
        "$STAGING" "$E2XRAY_SIGNING_KEY"
fi

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)"

finish_package() {
    package_path="$1"
    if [ "$PROTECTED_BUILD" = "1" ]; then
        package_hash="$(sha256sum "$package_path" | awk '{ print $1 }')"
        printf '%s  %s\n' "$package_hash" "$(basename "$package_path")" \
            > "$package_path.sha256"
        openssl dgst -sha256 -sign "$E2XRAY_SIGNING_KEY" \
            -out "$package_path.sig" "$package_path"
        openssl pkey -in "$E2XRAY_SIGNING_KEY" -pubout \
            -out "$OUTPUT_DIR/e2xray-signing-public.pem"
        echo "SHA256: $package_path.sha256"
        echo "Signature: $package_path.sig"
        echo "Public key: $OUTPUT_DIR/e2xray-signing-public.pem"
    fi
    echo "$package_path"
}

if [ "$PACKAGE_FORMAT" = "deb" ] && [ "$DPKG_DEB_MODE" = "native" ]; then
    PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_FILE_ARCH}.deb"
    dpkg-deb --build --root-owner-group -Zgzip -z9 \
        "$STAGING" "$OUTPUT_DIR/$PACKAGE"
    finish_package "$OUTPUT_DIR/$PACKAGE"
    exit 0
fi

if [ "$PACKAGE_FORMAT" = "deb" ]; then
    PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_FILE_ARCH}.deb"
else
    PACKAGE="${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_FILE_ARCH}.ipk"
fi
IPK_WORK="$STAGING/.ipk"
CONTROL_ARCHIVE="$IPK_WORK/control.tar.gz"
DATA_ARCHIVE="$IPK_WORK/data.tar.gz"
PACKAGE_PATH="$OUTPUT_DIR/$PACKAGE"

mkdir -p "$IPK_WORK"
printf '2.0\n' > "$IPK_WORK/debian-binary"
mv "$STAGING/DEBIAN" "$STAGING/CONTROL"

(
    if [ "$AR_MODE" = "native" ]; then
        cd "$STAGING/CONTROL"
        tar --owner=0 --group=0 -cf - . | gzip -9n > "$CONTROL_ARCHIVE"
    else
        "$AR_PYTHON" "$PROJECT_DIR/tools/package_tar.py" \
            "$CONTROL_ARCHIVE" "$STAGING/CONTROL"
    fi
)
(
    if [ "$AR_MODE" = "native" ]; then
        cd "$STAGING"
        tar --owner=0 --group=0 \
            --exclude='./CONTROL' \
            --exclude='./.ipk' \
            -cf - . | gzip -9n > "$DATA_ARCHIVE"
    else
        "$AR_PYTHON" "$PROJECT_DIR/tools/package_tar.py" \
            "$DATA_ARCHIVE" "$STAGING" CONTROL .ipk
    fi
)
(
    cd "$IPK_WORK"
    rm -f "$PACKAGE_PATH"
    if [ "$AR_MODE" = "native" ]; then
        ar r "$PACKAGE_PATH" debian-binary control.tar.gz data.tar.gz >/dev/null
    else
        "$AR_PYTHON" "$PROJECT_DIR/tools/ar_archive.py" \
            "$PACKAGE_PATH" debian-binary control.tar.gz data.tar.gz
    fi
)
finish_package "$PACKAGE_PATH"
