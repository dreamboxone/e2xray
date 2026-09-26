#!/bin/sh
# Build every e2xray package for the version in __init__.py.
#
#   ./build-release.sh [output-directory]      (default: ./dist)
#
# Requirements, all of which already exist on the build machine:
#   * the RSA signing key at ~/.e2xray-keys/e2xray-signing.pem
#     (or point E2XRAY_SIGNING_KEY at it)
#   * openssl, python3, tar, gzip, sha256sum
#   * the Xray cores under cores/ , unchanged (build.sh checks their SHA-256)
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_DIR="${1:-$PROJECT_DIR/dist}"
VERSION="$(sed -n 's/^PLUGIN_VERSION[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$PROJECT_DIR/usr/lib/enigma2/python/Plugins/Extensions/e2xray/__init__.py" |
    head -n 1)"

SIGNING_KEY="${E2XRAY_SIGNING_KEY:-${HOME:-}/.e2xray-keys/e2xray-signing.pem}"
if [ ! -f "$SIGNING_KEY" ]; then
    echo "Signing key not found: $SIGNING_KEY" >&2
    echo "Protected builds cannot be produced without it." >&2
    exit 1
fi
export E2XRAY_SIGNING_KEY="$SIGNING_KEY"

echo "Building e2xray $VERSION into $OUTPUT_DIR"
echo

# Nothing stale may reach the package: build.sh refuses to continue if any
# bytecode survives staging, and a leftover .pyc would also expose the source
# that obfuscation is meant to protect.
find "$PROJECT_DIR/usr" "$PROJECT_DIR/tests" "$PROJECT_DIR/tools" \
    -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

# Fail before packaging rather than after, if the parser is broken.
python3 "$PROJECT_DIR/tests/test_proxy_config.py"
sh -n "$PROJECT_DIR/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh"
echo

mkdir -p "$OUTPUT_DIR"

build() {
    format="$1"
    arch="$2"
    printf '==> %s / %s\n' "$format" "$arch"
    # Invoked through sh on purpose: a repository checked out on a Windows
    # filesystem often loses the execute bit, and calling it directly would
    # fail with "Permission denied" before a single package is built.
    sh "$PROJECT_DIR/build.sh" "$format" "$arch" "$OUTPUT_DIR"
    echo
}

build deb deb-universal              # _all.deb      (arm64+armv7+mips, auto-selected)
build deb arm64                      # _arm64.deb
build deb mipsel                     # _mipsel.deb
build ipk arm64                      # _arm64.ipk
build ipk armv7-universal            # _all.ipk
build ipk armv7ahf-neon              # _armv7ahf-neon.ipk
build ipk armv7ahf-vfp-neon          # _armv7ahf-vfp-neon.ipk
build ipk cortexa15hf-neon-vfpv4     # _cortexa15hf-neon-vfpv4.ipk
build ipk mips-universal             # _mips-all.ipk

echo "=================================================================="
echo "e2xray $VERSION packages in $OUTPUT_DIR:"
ls -1 "$OUTPUT_DIR" | grep "_${VERSION}_" || true
echo
echo "Verifying detached signatures against the public key..."
PUBLIC_KEY="$OUTPUT_DIR/e2xray-signing-public.pem"
status=0
for package in "$OUTPUT_DIR"/*_"$VERSION"_*.deb "$OUTPUT_DIR"/*_"$VERSION"_*.ipk; do
    [ -f "$package" ] || continue
    if openssl dgst -sha256 -verify "$PUBLIC_KEY" \
        -signature "$package.sig" "$package" >/dev/null 2>&1; then
        echo "  OK       $(basename "$package")"
    else
        echo "  BAD SIG  $(basename "$package")"
        status=1
    fi
done
exit "$status"
