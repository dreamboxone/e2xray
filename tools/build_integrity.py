#!/usr/bin/env python3
from __future__ import print_function

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

SHA256_DIGESTINFO_PREFIX = "3031300d060960864801650304020105000420"

VERIFIER_TEMPLATE = r'''#!/usr/bin/env python
# -*- coding: ascii -*-
from __future__ import print_function

import binascii
import hashlib
import io
import os
import sys

ROOT = os.environ.get("E2XRAY_VERIFY_ROOT", "/")
MANIFEST = os.path.join(ROOT, "usr/lib/e2xray/protection/manifest.sha256")
SIGNATURE = os.path.join(ROOT, "usr/lib/e2xray/protection/manifest.sig")
RSA_N = int("{modulus}", 16)
RSA_E = {exponent}
SHA256_DIGESTINFO_PREFIX = "3031300d060960864801650304020105000420"


def _read_bytes(path):
    with open(path, "rb") as source:
        return source.read()


def _int_from_bytes(value):
    text = binascii.hexlify(value)
    if not isinstance(text, str):
        text = text.decode("ascii")
    return int(text or "0", 16)


def _int_to_bytes(value, length):
    text = ("%0*x" % (length * 2, value))
    raw = binascii.unhexlify(text.encode("ascii"))
    return raw


def _verify_signature(manifest, signature):
    size = (RSA_N.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    sig_int = _int_from_bytes(signature)
    if sig_int <= 0 or sig_int >= RSA_N:
        return False
    decoded = _int_to_bytes(pow(sig_int, RSA_E, RSA_N), size)
    digest = hashlib.sha256(manifest).hexdigest()
    expected_tail = binascii.unhexlify(
        (SHA256_DIGESTINFO_PREFIX + digest).encode("ascii")
    )
    if len(decoded) < len(expected_tail) + 11:
        return False
    if decoded[:2] != b"\x00\x01":
        return False
    separator = decoded.find(b"\x00", 2)
    if separator < 10:
        return False
    if decoded[2:separator] != b"\xff" * (separator - 2):
        return False
    return decoded[separator + 1:] == expected_tail


def _safe_path(relative_path):
    if not relative_path.startswith("/"):
        return None
    normalized = os.path.normpath(relative_path)
    if normalized != relative_path or ".." in relative_path.split("/"):
        return None
    return normalized


def main():
    try:
        manifest = _read_bytes(MANIFEST)
        signature = _read_bytes(SIGNATURE)
    except IOError as error:
        print("e2xray integrity: missing protection file: %s" % error)
        return 1

    if not _verify_signature(manifest, signature):
        print("e2xray integrity: manifest signature is invalid")
        return 1

    try:
        text = manifest.decode("utf-8")
    except Exception:
        print("e2xray integrity: manifest encoding is invalid")
        return 1

    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            print("e2xray integrity: malformed manifest entry")
            return 1
        expected, relative_path = parts
        path = _safe_path(relative_path)
        if path is None:
            print("e2xray integrity: unsafe manifest path")
            return 1
        actual_path = os.path.join(ROOT, path.lstrip("/"))
        try:
            actual = hashlib.sha256(_read_bytes(actual_path)).hexdigest()
        except IOError:
            print("e2xray integrity: missing protected file: %s" % path)
            return 1
        if actual.lower() != expected.lower():
            print("e2xray integrity: modified protected file: %s" % path)
            return 1

    print("e2xray integrity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT).decode("utf-8", "replace")


def get_public_numbers(private_key):
    public_pem = run("openssl", "pkey", "-in", private_key, "-pubout")
    process = subprocess.Popen(
        ["openssl", "pkey", "-pubin", "-text", "-noout"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = process.communicate(public_pem.encode("ascii"))[0].decode("utf-8", "replace")
    if process.returncode != 0:
        raise RuntimeError(output.strip())

    modulus_match = re.search(r"Modulus:\s*\n((?:\s+[0-9a-fA-F:]+\n?)+)\s*Exponent:\s*(\d+)", output)
    if not modulus_match:
        raise RuntimeError("could not parse RSA public key")
    modulus = re.sub(r"[^0-9a-fA-F]", "", modulus_match.group(1)).lstrip("0") or "0"
    exponent = int(modulus_match.group(2))
    return modulus.lower(), exponent


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def collect_files(staging, verifier_path):
    candidates = [
        staging / "etc/init.d/e2xray",
        verifier_path,
    ]

    # Protect the complete installed plugin implementation and branding.
    # Runtime-generated bytecode/cache files are intentionally excluded.
    plugin_dir = staging / "usr/lib/enigma2/python/Plugins/Extensions/e2xray"
    if plugin_dir.is_dir():
        for path in sorted(plugin_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            candidates.append(path)

    # Protect architecture cores. For universal packages the generic `xray`
    # path is replaced by postinst with a symlink to xray-<arch>; in that case
    # protect the immutable architecture-specific cores instead of the alias.
    core_dir = staging / "usr/lib/e2xray/bin"
    if core_dir.is_dir():
        architecture_cores = sorted(
            path for path in core_dir.iterdir()
            if path.is_file() and not path.is_symlink() and path.name.startswith("xray-")
        )
        if architecture_cores:
            candidates.extend(architecture_cores)
        else:
            core = core_dir / "xray"
            if core.is_file() and not core.is_symlink():
                candidates.append(core)

    result = []
    seen = set()
    for path in candidates:
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def main():
    if len(sys.argv) != 3:
        print("usage: build_integrity.py STAGING PRIVATE_KEY", file=sys.stderr)
        return 2
    staging = Path(sys.argv[1]).resolve()
    private_key = str(Path(sys.argv[2]).resolve())
    if not staging.is_dir():
        print("staging directory not found", file=sys.stderr)
        return 2
    if not os.path.isfile(private_key):
        print("private key not found", file=sys.stderr)
        return 2

    protection = staging / "usr/lib/e2xray/protection"
    protection.mkdir(parents=True, exist_ok=True)
    verifier_path = protection / "integrity_verify.py"
    manifest_path = protection / "manifest.sha256"
    signature_path = protection / "manifest.sig"

    modulus, exponent = get_public_numbers(private_key)
    verifier_path.write_text(
        VERIFIER_TEMPLATE.format(modulus=modulus, exponent=exponent),
        encoding="ascii",
    )
    os.chmod(str(verifier_path), 0o755)

    lines = []
    for path in collect_files(staging, verifier_path):
        relative = "/" + path.relative_to(staging).as_posix()
        lines.append("%s  %s" % (sha256(path), relative))
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(str(manifest_path), 0o644)

    subprocess.check_call(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            private_key,
            "-out",
            str(signature_path),
            str(manifest_path),
        ]
    )
    os.chmod(str(signature_path), 0o644)
    print("Protected %d files with RSA/SHA-256 integrity metadata." % len(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
