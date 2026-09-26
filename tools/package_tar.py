#!/usr/bin/env python3
"""Create a deterministic package tar.gz with Unix modes on any host OS."""

from __future__ import print_function

import gzip
import os
import sys
import tarfile


EXECUTABLES = {
    "postinst",
    "postrm",
    "preinst",
    "prerm",
    "etc/init.d/e2xray",
    "usr/lib/e2xray/bin/xray",
    "usr/lib/e2xray/bin/xray-arm64",
    "usr/lib/e2xray/bin/xray-armv7",
    "usr/lib/e2xray/bin/xray-mips32le",
    "usr/lib/e2xray/bin/xray-mips64le",
    "usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh",
}


def normalized_info(name, source_path, archive_name=None):
    # `name` stays the repository-relative path so the EXECUTABLES lookup keeps
    # working; `archive_name` is what actually goes into the archive.
    info = tarfile.TarInfo(archive_name or name)
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if os.path.isdir(source_path):
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
    elif os.path.islink(source_path):
        info.type = tarfile.SYMTYPE
        info.mode = 0o777
        info.linkname = os.readlink(source_path)
    else:
        info.type = tarfile.REGTYPE
        info.mode = 0o755 if name in EXECUTABLES else 0o644
        info.size = os.path.getsize(source_path)
    return info


def iter_paths(root, excluded):
    for current, directories, files in os.walk(root):
        relative_dir = os.path.relpath(current, root)
        relative_dir = "" if relative_dir == "." else relative_dir.replace(os.sep, "/")
        directories[:] = sorted(
            item
            for item in directories
            if (relative_dir + "/" + item).strip("/") not in excluded
        )
        if relative_dir:
            yield relative_dir, current
        for filename in sorted(files):
            name = (relative_dir + "/" + filename).strip("/")
            if name not in excluded:
                yield name, os.path.join(current, filename)


def main():
    if len(sys.argv) < 3:
        print("Usage: package_tar.py OUTPUT ROOT [EXCLUDE...]", file=sys.stderr)
        return 2
    output_path = os.path.abspath(sys.argv[1])
    root = os.path.abspath(sys.argv[2])
    excluded = {item.strip("/") for item in sys.argv[3:]}
    temporary_path = output_path + ".tmp"
    try:
        with open(temporary_path, "wb") as raw_output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
                    for name, source_path in iter_paths(root, excluded):
                        # "./" prefix, exactly as `tar -cf - .` produces on the
                        # native path. Some opkg builds only register files
                        # whose data.tar.gz members carry it, so an archive
                        # written by this fallback could install into the wrong
                        # place or not be tracked at all.
                        info = normalized_info(name, source_path, "./" + name)
                        if info.isreg():
                            with open(source_path, "rb") as source:
                                archive.addfile(info, source)
                        else:
                            archive.addfile(info)
        os.replace(temporary_path, output_path)
    except Exception as error:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        print("Could not create package tar archive: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
