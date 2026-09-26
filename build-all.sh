#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_DIR="${1:-dist}"

cd "$PROJECT_DIR"

# build.sh is protected-by-default. If the signing key is not available,
# the first build stops instead of silently producing a readable package.
./build.sh deb arm64 "$OUTPUT_DIR"
./build.sh ipk arm64 "$OUTPUT_DIR"
./build.sh deb deb-universal "$OUTPUT_DIR"
./build.sh ipk armv7ahf-neon "$OUTPUT_DIR"
./build.sh ipk armv7ahf-vfp-neon "$OUTPUT_DIR"
./build.sh ipk cortexa15hf-neon-vfpv4 "$OUTPUT_DIR"
./build.sh ipk armv7-universal "$OUTPUT_DIR"
./build.sh deb mipsel "$OUTPUT_DIR"
./build.sh ipk mips-universal "$OUTPUT_DIR"

echo "All e2xray packages built with mandatory protection."
