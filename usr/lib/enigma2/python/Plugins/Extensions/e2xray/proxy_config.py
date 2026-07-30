#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import base64
import hashlib
import io
import json
import os
import re
import shlex
import sys

try:
    from urllib.parse import parse_qs, unquote, urlsplit
except ImportError:
    from urlparse import parse_qs, urlsplit
    from urllib import unquote

try:
    text_type = unicode
except NameError:
    text_type = str


SUPPORTED_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://")
RUNTIME_FIELDS = (
    "PROFILE_ID",
    "PROFILE_NAME",
    "PROTOCOL",
    "SERVER_ADDRESS",
    "SERVER_PORT",
)
LEGACY_FIELDS = (
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


def as_text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return text_type(value)


def sanitize_name(value):
    value = unquote(as_text(value or ""))
    value = value.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    value = " ".join(value.split())
    return value[:96]


def fragment_name(entry):
    parts = as_text(entry).split("#", 1)
    if len(parts) != 2:
        return ""
    return sanitize_name(parts[1])


def finalize_profile(parsed, entry, fallback_index=None):
    entry = as_text(entry).strip()
    embedded_name = parsed.pop("_NAME", "")
    name = fragment_name(entry) or sanitize_name(embedded_name)
    if not name:
        suffix = " %d" % fallback_index if fallback_index is not None else ""
        name = "%s%s" % (parsed["PROTOCOL"].upper(), suffix)
    parsed["PROFILE_ID"] = hashlib.sha256(entry.encode("utf-8")).hexdigest()
    parsed["PROFILE_NAME"] = name
    parsed["LINK"] = entry
    return parsed


def query_value(query, key, default=""):
    values = query.get(key, [])
    if not values:
        return default
    return unquote(as_text(values[0]))


def first_value(mapping, keys, default=""):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            if isinstance(value, list):
                value = value[0] if value else ""
            return as_text(value)
    return default


def parse_port(value, default=443):
    try:
        port = int(value or default)
    except (TypeError, ValueError):
        raise ValueError("invalid port")
    if port < 1 or port > 65535:
        raise ValueError("invalid port")
    return port


def decode_base64(value):
    compact = as_text(value).strip().replace("\r", "").replace("\n", "")
    compact += "=" * ((4 - len(compact) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(compact.encode("ascii"))
    except Exception:
        try:
            raw = base64.b64decode(compact.encode("ascii"))
        except Exception:
            raise ValueError("invalid base64 data")
    return raw.decode("utf-8")


def parse_bool(value):
    return as_text(value).strip().lower() in ("1", "true", "yes", "on")


def normalize_transport(value):
    transport = as_text(value or "raw").strip().lower()
    aliases = {
        "tcp": "raw",
        "raw": "raw",
        "ws": "websocket",
        "websocket": "websocket",
        "grpc": "grpc",
        "xhttp": "xhttp",
        "splithttp": "xhttp",
        "http": "xhttp",
    }
    if transport not in aliases:
        raise ValueError("unsupported transport: %s" % transport)
    return aliases[transport]


def normalize_security(value, default="none"):
    security = as_text(value or default).strip().lower()
    if security in ("", "none"):
        return "none"
    if security not in ("tls", "reality"):
        raise ValueError("unsupported transport security: %s" % security)
    return security


def split_alpn(value):
    if isinstance(value, list):
        return [as_text(item).strip() for item in value if as_text(item).strip()]
    value = as_text(value or "").replace("|", ",")
    return [item.strip() for item in value.split(",") if item.strip()]


def common_stream(values):
    transport = normalize_transport(first_value(values, ("type", "net"), "raw"))
    security = normalize_security(first_value(values, ("security", "tls"), "none"))
    if security == "reality" and transport == "websocket":
        raise ValueError("REALITY cannot be used with WebSocket")

    address = first_value(values, ("address", "add"))
    server_name = first_value(values, ("sni", "serverName"), address)
    fingerprint = first_value(values, ("fp", "fingerprint"), "chrome")
    path = first_value(values, ("path", "serviceName"), "")
    host = first_value(values, ("host", "authority"), "")
    mode = first_value(values, ("mode",), "")

    stream = {"method": transport, "security": security}
    if transport == "websocket":
        websocket = {"path": path or "/"}
        if host:
            websocket["host"] = host
        stream["wsSettings"] = websocket
    elif transport == "grpc":
        grpc = {"serviceName": path}
        if host:
            grpc["authority"] = host
        stream["grpcSettings"] = grpc
    elif transport == "xhttp":
        xhttp = {"path": path or "/"}
        if host:
            xhttp["host"] = host
        if mode:
            xhttp["mode"] = mode
        stream["xhttpSettings"] = xhttp

    if security == "tls":
        tls = {
            "serverName": server_name,
            "fingerprint": fingerprint,
            "allowInsecure": parse_bool(
                first_value(values, ("allowInsecure", "insecure"), "0")
            ),
        }
        alpn = split_alpn(first_value(values, ("alpn",), ""))
        if alpn:
            tls["alpn"] = alpn
        stream["tlsSettings"] = tls
    elif security == "reality":
        password = first_value(values, ("pbk", "publicKey", "password"), "")
        if not password:
            raise ValueError("REALITY public key is missing")
        reality = {
            "serverName": server_name,
            "fingerprint": fingerprint,
            "password": password,
            "shortId": first_value(values, ("sid", "shortId"), ""),
        }
        spider_x = first_value(values, ("spx", "spiderX"), "")
        if spider_x:
            reality["spiderX"] = spider_x
        stream["realitySettings"] = reality
    return stream


def parsed_result(protocol, address, port, settings, stream):
    address = as_text(address).strip()
    if not address:
        raise ValueError("server address is missing")
    outbound = {
        "tag": "proxy",
        "protocol": protocol,
        "settings": settings,
        "streamSettings": stream,
    }
    return {
        "PROTOCOL": protocol,
        "SERVER_ADDRESS": address,
        "SERVER_PORT": str(parse_port(port)),
        "outbound": outbound,
    }


def uri_values(entry):
    parsed = urlsplit(entry.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    values = {}
    for key in query:
        values[key] = query_value(query, key)
    values["address"] = parsed.hostname or ""
    values["port"] = str(parsed.port or 443)
    return parsed, values


def uri_userinfo(parsed):
    netloc = parsed.netloc.rsplit("@", 1)
    if len(netloc) != 2:
        return ""
    return unquote(netloc[0])


def parse_vless(entry):
    parsed, values = uri_values(entry)
    user_id = uri_userinfo(parsed)
    if not user_id:
        raise ValueError("VLESS user ID is missing")
    encryption = first_value(values, ("encryption",), "none")
    settings = {
        "address": values["address"],
        "port": parse_port(values["port"]),
        "id": user_id,
        "encryption": encryption,
        "flow": first_value(values, ("flow",), ""),
    }
    return parsed_result(
        "vless", values["address"], values["port"], settings, common_stream(values)
    )


def parse_trojan(entry):
    parsed, values = uri_values(entry)
    password = uri_userinfo(parsed)
    if not password:
        raise ValueError("Trojan password is missing")
    if "security" not in values:
        values["security"] = "tls"
    settings = {
        "address": values["address"],
        "port": parse_port(values["port"]),
        "password": password,
    }
    return parsed_result(
        "trojan", values["address"], values["port"], settings, common_stream(values)
    )


def parse_vmess(entry):
    payload = entry.strip()[len("vmess://") :].split("#", 1)[0]
    try:
        values = json.loads(decode_base64(payload))
    except ValueError:
        raise
    except Exception:
        raise ValueError("invalid VMess JSON")
    if not isinstance(values, dict):
        raise ValueError("invalid VMess JSON")

    address = first_value(values, ("add", "address"))
    port = parse_port(first_value(values, ("port",), "443"))
    user_id = first_value(values, ("id",))
    if not user_id:
        raise ValueError("VMess user ID is missing")
    settings = {
        "address": address,
        "port": port,
        "id": user_id,
        "security": first_value(values, ("scy", "security"), "auto"),
    }
    stream_values = dict(values)
    stream_values["security"] = first_value(values, ("tls",), "none")
    parsed = parsed_result(
        "vmess", address, port, settings, common_stream(stream_values)
    )
    parsed["_NAME"] = first_value(values, ("ps", "name"), "")
    return parsed


def split_host_port(value):
    parsed = urlsplit("//" + value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("invalid Shadowsocks port")
    if not parsed.hostname or not port:
        raise ValueError("invalid Shadowsocks server")
    return parsed.hostname, parse_port(port)


def parse_shadowsocks(entry):
    body = entry.strip()[len("ss://") :].split("#", 1)[0]
    body, separator, query_string = body.partition("?")
    query = parse_qs(query_string, keep_blank_values=True) if separator else {}
    if query_value(query, "plugin", ""):
        raise ValueError("Shadowsocks plugins are not supported")

    if "@" in body:
        credential_part, server_part = body.rsplit("@", 1)
        decoded_credentials = unquote(credential_part)
        if ":" not in decoded_credentials:
            decoded_credentials = decode_base64(decoded_credentials)
    else:
        decoded = decode_base64(body)
        if "@" not in decoded:
            raise ValueError("invalid Shadowsocks link")
        decoded_credentials, server_part = decoded.rsplit("@", 1)

    if ":" not in decoded_credentials:
        raise ValueError("invalid Shadowsocks credentials")
    method, password = decoded_credentials.split(":", 1)
    address, port = split_host_port(server_part)
    if not method or not password:
        raise ValueError("invalid Shadowsocks credentials")

    settings = {
        "address": address,
        "port": port,
        "method": method,
        "password": password,
    }
    stream_values = {"address": address}
    for key in query:
        stream_values[key] = query_value(query, key)
    return parsed_result(
        "shadowsocks",
        address,
        port,
        settings,
        common_stream(stream_values),
    )


def parse_legacy(content):
    values = {}
    assignment = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
    for source_line in content.splitlines():
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue
        match = assignment.match(line)
        if not match or match.group(1) not in LEGACY_FIELDS:
            raise ValueError("invalid legacy configuration")
        parts = shlex.split(match.group(2).strip(), comments=False, posix=True)
        if len(parts) != 1:
            raise ValueError("invalid legacy value")
        values[match.group(1)] = parts[0]

    address = values.get("SERVER_ADDRESS", "").strip()
    user_id = values.get("UUID", "").strip()
    port = parse_port(values.get("SERVER_PORT", "443"))
    if not address or not user_id:
        raise ValueError("legacy VLESS configuration is incomplete")
    stream_values = {
        "address": address,
        "security": values.get("SECURITY", "none"),
        "type": values.get("NETWORK", "tcp"),
        "sni": values.get("SNI", address),
        "pbk": values.get("PUBLIC_KEY", ""),
        "sid": values.get("SHORT_ID", ""),
        "fp": values.get("FINGERPRINT", "chrome"),
        "path": values.get("TRANSPORT_PATH", ""),
        "host": values.get("HOST", ""),
    }
    settings = {
        "address": address,
        "port": port,
        "id": user_id,
        "encryption": "none",
        "flow": values.get("FLOW", ""),
    }
    return parsed_result(
        "vless", address, port, settings, common_stream(stream_values)
    )


def parse_share_link(entry):
    entry = as_text(entry).strip()
    lower = entry.lower()
    if lower.startswith("vless://"):
        parsed = parse_vless(entry)
    elif lower.startswith("vmess://"):
        parsed = parse_vmess(entry)
    elif lower.startswith("trojan://"):
        parsed = parse_trojan(entry)
    elif lower.startswith("ss://"):
        parsed = parse_shadowsocks(entry)
    else:
        raise ValueError("unsupported configuration protocol")
    return finalize_profile(parsed, entry)


def read_profiles(path):
    with io.open(path, "r", encoding="utf-8-sig") as config_file:
        content = config_file.read()
    entries = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not entries:
        raise ValueError("no configuration found")
    if entries[0].lower().startswith(SUPPORTED_SCHEMES):
        profiles = []
        for index, entry in enumerate(entries, 1):
            if not entry.lower().startswith(SUPPORTED_SCHEMES):
                raise ValueError("line %d is not a supported share link" % index)
            try:
                parsed = parse_share_link(entry)
            except ValueError as error:
                raise ValueError("line %d: %s" % (index, error))
            if not fragment_name(entry) and not parsed.get("PROFILE_NAME"):
                parsed["PROFILE_NAME"] = "%s %d" % (
                    parsed["PROTOCOL"].upper(),
                    index,
                )
            elif parsed["PROFILE_NAME"] == parsed["PROTOCOL"].upper():
                parsed["PROFILE_NAME"] = "%s %d" % (
                    parsed["PROTOCOL"].upper(),
                    index,
                )
            profiles.append(parsed)
        return profiles
    return [finalize_profile(parse_legacy(content), content, 1)]


def read_selection(path):
    try:
        with io.open(path, "r", encoding="ascii") as source:
            profile_id = source.readline().strip().lower()
    except (IOError, OSError):
        return ""
    if re.match(r"^[0-9a-f]{64}$", profile_id):
        return profile_id
    return ""


def write_selection(path, profile_id):
    profile_id = as_text(profile_id).strip().lower()
    if not re.match(r"^[0-9a-f]{64}$", profile_id):
        raise ValueError("invalid profile ID")
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    atomic_write(path, profile_id + "\n")


def select_profile(profiles, selection_path):
    selected_id = read_selection(selection_path)
    for profile in profiles:
        if profile["PROFILE_ID"] == selected_id:
            return profile
    return profiles[0]


def read_config(path, selection_path):
    return select_profile(read_profiles(path), selection_path)


def build_xray_config(parsed):
    return {
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["8.8.8.8", "1.1.1.1"]},
        "inbounds": [
            {
                "tag": "tun-in",
                "protocol": "tun",
                "settings": {
                    "name": "e2xray0",
                    "mtu": 1492,
                    "gateway": ["10.255.0.1/30"],
                    "autoOutboundsInterface": "auto",
                },
            }
        ],
        "outbounds": [
            parsed["outbound"],
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "ip": [
                        "127.0.0.0/8",
                        "10.0.0.0/8",
                        "100.64.0.0/10",
                        "169.254.0.0/16",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "224.0.0.0/4",
                        "255.255.255.255/32",
                    ],
                    "outboundTag": "direct",
                }
            ],
        },
    }


def shell_quote(value):
    return "'" + as_text(value).replace("'", "'\"'\"'") + "'"


def atomic_write(path, content, mode=0o600):
    temporary_path = path + ".tmp"
    with io.open(temporary_path, "w", encoding="utf-8") as output:
        output.write(content)
    os.chmod(temporary_path, mode)
    os.rename(temporary_path, path)


def write_runtime(path, parsed):
    content = "".join(
        "%s=%s\n" % (key, shell_quote(parsed.get(key, "")))
        for key in RUNTIME_FIELDS
    )
    atomic_write(path, content)


def write_xray_config(path, parsed):
    content = json.dumps(
        build_xray_config(parsed),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write(path, as_text(content) + "\n")


def main():
    if len(sys.argv) != 5:
        print(
            "Usage: proxy_config.py INPUT SELECTION RUNTIME_OUTPUT XRAY_CONFIG_OUTPUT",
            file=sys.stderr,
        )
        return 2
    try:
        profiles = read_profiles(sys.argv[1])
        parsed = select_profile(profiles, sys.argv[2])
        if read_selection(sys.argv[2]) != parsed["PROFILE_ID"]:
            write_selection(sys.argv[2], parsed["PROFILE_ID"])
        write_runtime(sys.argv[3], parsed)
        write_xray_config(sys.argv[4], parsed)
    except Exception as error:
        print("Invalid e2xray configuration: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
