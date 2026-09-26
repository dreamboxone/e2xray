#!/usr/bin/env python3
"""Create the small deterministic Unix ar archive used by an IPK package."""

from __future__ import print_function

import os
import sys


def ar_field(value, width):
    encoded = str(value).encode("ascii")
    if len(encoded) > width:
        raise ValueError("ar header field is too long: %r" % value)
    return encoded.ljust(width, b" ")


def write_member(output, path):
    name = os.path.basename(path)
    if len(name.encode("ascii")) > 15:
        raise ValueError("ar member name is too long: %s" % name)
    with open(path, "rb") as source:
        data = source.read()
    header = b"".join(
        (
            ar_field(name + "/", 16),
            ar_field(0, 12),
            ar_field(0, 6),
            ar_field(0, 6),
            ar_field("100644", 8),
            ar_field(len(data), 10),
            b"`\n",
        )
    )
    if len(header) != 60:
        raise AssertionError("invalid ar header length")
    output.write(header)
    output.write(data)
    if len(data) % 2:
        output.write(b"\n")


def main():
    if len(sys.argv) < 3:
        print("Usage: ar_archive.py OUTPUT INPUT...", file=sys.stderr)
        return 2
    output_path = sys.argv[1]
    temporary_path = output_path + ".tmp"
    try:
        with open(temporary_path, "wb") as output:
            output.write(b"!<arch>\n")
            for path in sys.argv[2:]:
                write_member(output, path)
        os.replace(temporary_path, output_path)
    except Exception as error:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        print("Could not create ar archive: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
