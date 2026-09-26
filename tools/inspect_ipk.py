#!/usr/bin/env python3
"""Validate an IPK/DEB archive and its embedded Xray cores using only stdlib."""

from __future__ import print_function

import gzip
import hashlib
import io
import sys
import tarfile


def read_ar(path):
    with open(path, "rb") as source:
        content = source.read()
    if not content.startswith(b"!<arch>\n"):
        raise ValueError("not a Unix ar archive")
    members = {}
    offset = 8
    while offset < len(content):
        header = content[offset : offset + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ValueError("invalid ar member header")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        offset += 60
        members[name] = content[offset : offset + size]
        if len(members[name]) != size:
            raise ValueError("truncated ar member: %s" % name)
        offset += size + (size % 2)
    return members


def tar_members(compressed):
    raw = gzip.GzipFile(fileobj=io.BytesIO(compressed)).read()
    archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
    return archive, {item.name.lstrip("./"): item for item in archive.getmembers()}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if len(sys.argv) not in (4, 5, 7):
        print(
            "Usage: inspect_ipk.py PACKAGE EXPECTED_ARCH CORE [SECOND_CORE]\n"
            "       inspect_ipk.py PACKAGE all ARM64 ARMV7 MIPS32LE MIPS64LE",
            file=sys.stderr,
        )
        return 2
    package, expected_arch, expected_core_path = sys.argv[1:4]
    expected_second_core_path = sys.argv[4] if len(sys.argv) == 5 else None
    universal_core_paths = sys.argv[3:7] if len(sys.argv) == 7 else None
    members = read_ar(package)
    expected_members = {"debian-binary", "control.tar.gz", "data.tar.gz"}
    if set(members) != expected_members:
        raise ValueError("unexpected ar members: %s" % sorted(members))
    if members["debian-binary"] != b"2.0\n":
        raise ValueError("invalid debian-binary")

    control_archive, control_members = tar_members(members["control.tar.gz"])
    control = control_archive.extractfile(control_members["control"]).read().decode("utf-8")
    if "Architecture: %s\n" % expected_arch not in control:
        raise ValueError("package architecture does not match %s" % expected_arch)
    if package.lower().endswith(".ipk"):
        if "Recommends: kernel-module-tun, iproute2" not in control:
            raise ValueError("IPK does not recommend TUN and full iproute2 support")
    if expected_arch == "all":
        preinst = control_members.get("preinst")
        if preinst is None or not preinst.isfile() or preinst.mode & 0o111 == 0:
            raise ValueError("universal package ARMv7 pre-install guard is missing")
        preinst_content = control_archive.extractfile(preinst).read()
        arm_guard = b"armv7" in preinst_content and b"vfpv3" in preinst_content
        mips_guard = b"mips" in preinst_content and b"little-endian" in preinst_content
        arm64_guard = b"aarch64" in preinst_content
        if universal_core_paths and not (arm64_guard and arm_guard and mips_guard):
            raise ValueError("universal DEB pre-install guard is incomplete")
        if not universal_core_paths and not arm_guard and not mips_guard:
            raise ValueError("universal package pre-install guard is incomplete")

    data_archive, data_members = tar_members(members["data.tar.gz"])
    if universal_core_paths:
        core_specs = tuple(
            zip(
                (
                    "usr/lib/e2xray/bin/xray-arm64",
                    "usr/lib/e2xray/bin/xray-armv7",
                    "usr/lib/e2xray/bin/xray-mips32le",
                    "usr/lib/e2xray/bin/xray-mips64le",
                ),
                universal_core_paths,
            )
        )
    elif expected_second_core_path:
        core_specs = (
            ("usr/lib/e2xray/bin/xray-mips32le", expected_core_path),
            ("usr/lib/e2xray/bin/xray-mips64le", expected_second_core_path),
        )
    else:
        core_specs = (("usr/lib/e2xray/bin/xray", expected_core_path),)

    packaged_cores = []
    for core_name, expected_path in core_specs:
        core_member = data_members.get(core_name)
        if core_member is None or not core_member.isfile():
            raise ValueError("embedded Xray core is missing: %s" % core_name)
        packaged_core = data_archive.extractfile(core_member).read()
        with open(expected_path, "rb") as source:
            expected_core = source.read()
        if packaged_core != expected_core:
            raise ValueError("embedded Xray core does not match: %s" % core_name)
        packaged_cores.append((core_name, packaged_core))

    executable_paths = tuple(name for name, unused in core_specs) + (
        "usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh",
        "etc/init.d/e2xray",
    )
    for name in executable_paths:
        if name not in data_members or data_members[name].mode & 0o111 == 0:
            raise ValueError("file is not executable: %s" % name)

    print("package=%s" % package)
    print("architecture=%s" % expected_arch)
    for core_name, packaged_core in packaged_cores:
        print("%s_sha256=%s" % (core_name.rsplit("/", 1)[-1], sha256(packaged_core)))
    print("data_members=%d" % len(data_members))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("IPK validation failed: %s" % error, file=sys.stderr)
        sys.exit(1)
