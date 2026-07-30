#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import os
import re
import shlex
import sys
import uuid as uuid_module

try:
    from urllib.parse import parse_qs, unquote, urlsplit
except ImportError:
    from urlparse import parse_qs, urlsplit
    from urllib import unquote

try:
    text_type = unicode
except NameError:
    text_type = str


FIELDS = (
    "SERVER_ADDRESS",
    "SERVER_PORT",
    "UUID",
    "SNI",
    "PUBLIC_KEY",
    "SHORT_ID",
    "FINGERPRINT",
    "SECURITY",
    "NETWORK",
    "TRANSPORT_PATH",
    "HOST",
    "FLOW",
)

DEFAULTS = {
    "SERVER_PORT": "443",
    "SNI": "",
    "PUBLIC_KEY": "",
    "SHORT_ID": "",
    "FINGERPRINT": "chrome",
    "SECURITY": "none",
    "NETWORK": "tcp",
    "TRANSPORT_PATH": "",
    "HOST": "",
    "FLOW": "",
}


def query_value(query, key, default=""):
    values = query.get(key, [])
    if not values:
        return default
    return unquote(values[0])


def validate(values):
    address = values.get("SERVER_ADDRESS", "").strip()
    user_id = values.get("UUID", "").strip()
    try:
        port = int(values.get("SERVER_PORT", ""))
    except (TypeError, ValueError):
        raise ValueError("invalid port")

    if not address or not user_id or port < 1 or port > 65535:
        raise ValueError("missing required VLESS values")
    try:
        uuid_module.UUID(user_id)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("invalid UUID")

    security = values.get("SECURITY", "none").lower()
    network = values.get("NETWORK", "tcp").lower()
    if security not in ("none", "tls", "reality"):
        raise ValueError("unsupported VLESS security")
    if network == "raw":
        network = "tcp"
    if network not in ("tcp", "ws", "grpc"):
        raise ValueError("unsupported VLESS transport")

    values["SERVER_ADDRESS"] = address
    values["SERVER_PORT"] = str(port)
    values["UUID"] = user_id
    values["SECURITY"] = security
    values["NETWORK"] = network

    for key in FIELDS:
        value = values.get(key, "")
        if isinstance(value, bytes) and bytes is not text_type:
            try:
                value = value.decode("utf-8")
            except UnicodeError:
                raise ValueError("invalid UTF-8 in %s" % key)
        elif not isinstance(value, text_type):
            value = text_type(value)
        if any(character in value for character in ("\x00", "\r", "\n", '"', "\\")):
            raise ValueError("unsupported character in %s" % key)
        values[key] = value
    return values


def parse_vless(entry):
    parsed = urlsplit(entry.strip())
    if parsed.scheme.lower() != "vless":
        raise ValueError("configuration must start with vless://")

    try:
        port = parsed.port or 443
    except ValueError:
        raise ValueError("invalid port")

    query = parse_qs(parsed.query, keep_blank_values=True)
    address = parsed.hostname or ""
    security = query_value(query, "security", "none").lower()
    network = query_value(query, "type", "tcp").lower()
    values = dict(DEFAULTS)
    values.update(
        {
            "SERVER_ADDRESS": address,
            "SERVER_PORT": str(port),
            "UUID": unquote(parsed.username or ""),
            "SNI": query_value(
                query, "sni", query_value(query, "serverName", address)
            ),
            "PUBLIC_KEY": query_value(
                query, "pbk", query_value(query, "publicKey", "")
            ),
            "SHORT_ID": query_value(
                query, "sid", query_value(query, "shortId", "")
            ),
            "FINGERPRINT": query_value(query, "fp", "chrome"),
            "SECURITY": security,
            "NETWORK": network,
            "TRANSPORT_PATH": query_value(
                query, "path", query_value(query, "serviceName", "")
            ),
            "HOST": query_value(query, "host", ""),
            "FLOW": query_value(query, "flow", ""),
        }
    )
    return validate(values)


def parse_legacy(content):
    values = dict(DEFAULTS)
    assignment = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
    for source_line in content.splitlines():
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue
        match = assignment.match(line)
        if not match or match.group(1) not in FIELDS:
            raise ValueError("invalid legacy configuration")
        raw_value = match.group(2).strip()
        parts = shlex.split(raw_value, comments=False, posix=True)
        if len(parts) != 1:
            raise ValueError("invalid legacy value")
        values[match.group(1)] = parts[0]
    return validate(values)


def read_config(path):
    with io.open(path, "r", encoding="utf-8-sig") as config_file:
        content = config_file.read()
    entries = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not entries:
        raise ValueError("no VLESS configuration found")
    if entries[0].lower().startswith("vless://"):
        if len(entries) != 1:
            raise ValueError("config.txt must contain one VLESS link")
        return parse_vless(entries[0])
    return parse_legacy(content)


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_runtime(path, values):
    temporary_path = path + ".tmp"
    with io.open(temporary_path, "w", encoding="utf-8") as output:
        for key in FIELDS:
            output.write(
                text_type("%s=%s\n") % (key, shell_quote(values.get(key, "")))
            )
    os.chmod(temporary_path, 0o600)
    os.rename(temporary_path, path)


def main():
    if len(sys.argv) != 3:
        print("Usage: vless_config.py INPUT OUTPUT", file=sys.stderr)
        return 2
    try:
        values = read_config(sys.argv[1])
        write_runtime(sys.argv[2], values)
    except Exception as error:
        print("Invalid e2xray configuration: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
