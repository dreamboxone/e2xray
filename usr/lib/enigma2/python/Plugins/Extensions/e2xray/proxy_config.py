#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import errno
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

PY2 = sys.version_info[0] == 2


SUPPORTED_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://")
# Must match the addresses e2xrayctl.sh assigns to the TUN interface.
TUN_GATEWAY4 = "10.255.0.1/30"
TUN_GATEWAY6 = "fdfe:e2e2::1/64"
# Xray tags its own sockets with this fwmark so the transparent iptables chains
# can RETURN early instead of capturing the proxy's own transport and looping.
SELF_MARK = 255
TRANSPARENT_PORT = 12345
# Not 5353: that is the mDNS port and avahi-daemon already owns it on most
# Enigma2 images, which makes the whole core fail to start with EADDRINUSE.
DNS_PORT = 15353
PROBE_HOST = "cp.cloudflare.com"
PROBE_PATH = "/generate_204"
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


def emit(line):
    """print() that survives a non-ASCII value on Python 2.

    The control script redirects this output into the log, so stdout has no
    encoding and Python 2 falls back to ASCII - a Persian or Arabic profile name
    then raises UnicodeEncodeError and kills the process mid-run.
    """
    line = as_text(line)
    if PY2:
        sys.stdout.write(line.encode("utf-8") + b"\n")
    else:
        sys.stdout.write(line + "\n")


def url_decode(value):
    value = as_text(value or "")
    if PY2:
        # Python 2 unquotes Unicode one byte at a time. Work with bytes first,
        # then decode the complete UTF-8 sequence so Persian/Arabic stays intact.
        return unquote(value.encode("utf-8")).decode("utf-8", "replace")
    return unquote(value)


def parse_query(value):
    if PY2 and isinstance(value, text_type):
        value = value.encode("utf-8")
    return parse_qs(value, keep_blank_values=True)


def sanitize_name(value):
    value = url_decode(value)
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
    return url_decode(values[0])


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
    compact = compact.replace("-", "+").replace("_", "/")
    if len(compact) % 4 == 1:
        raise ValueError("invalid base64 data")
    compact += "=" * ((4 - len(compact) % 4) % 4)

    # Some DreamOS images expose a minimal command-line Python installation
    # without the stdlib base64.py module. Decode locally so VLESS/Trojan are
    # not rejected at module import time and VMess/Shadowsocks keep working.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    decoded = []
    for offset in range(0, len(compact), 4):
        block = compact[offset : offset + 4]
        if len(block) != 4 or block[0] == "=" or block[1] == "=":
            raise ValueError("invalid base64 data")
        if block[2] == "=" and block[3] != "=":
            raise ValueError("invalid base64 data")
        values = []
        for character in block:
            if character == "=":
                values.append(0)
            else:
                index = alphabet.find(character)
                if index < 0:
                    raise ValueError("invalid base64 data")
                values.append(index)
        decoded.append((values[0] << 2) | (values[1] >> 4))
        if block[2] != "=":
            decoded.append(((values[1] & 15) << 4) | (values[2] >> 2))
        if block[3] != "=":
            decoded.append(((values[2] & 3) << 6) | values[3])

    if PY2:
        raw = "".join(chr(value) for value in decoded)
    else:
        raw = bytes(bytearray(decoded))
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

    # The embedded Xray 26.5.9 reads streamSettings.network, not method.
    stream = {"network": transport, "security": security}
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
        extra = first_value(values, ("extra",), "")
        if extra:
            try:
                extra_settings = json.loads(extra)
            except Exception:
                raise ValueError("invalid XHTTP extra settings")
            if not isinstance(extra_settings, dict):
                raise ValueError("XHTTP extra settings must be an object")
            xhttp["extra"] = extra_settings
        stream["xhttpSettings"] = xhttp

    if security == "tls":
        tls = {
            "serverName": server_name,
            "fingerprint": fingerprint,
        }
        # Xray-core removed "allowInsecure" in v26.2.6 and now REJECTS every
        # config that still carries the key, whatever its value. Emitting it
        # made all TLS profiles die with:
        #   The feature "allowInsecure" has been removed and migrated to
        #   "pinnedPeerCertSha256".
        # The key is therefore never written any more. A share link that wants
        # to accept a self-signed certificate can pin it instead, which is the
        # supported replacement.
        pinned = split_alpn(
            first_value(
                values,
                ("pinnedPeerCertSha256", "pinnedPeerCertChainSha256", "pinSHA256"),
                "",
            )
        )
        if pinned:
            # The core wants hex, and rejects anything else deep inside the TLS
            # builder with "encoding/hex: invalid byte", which tells the user
            # nothing. A base64 digest pasted from a certificate viewer is the
            # obvious mistake, so it is caught here instead.
            for digest in pinned:
                if not re.match(r"^[0-9A-Fa-f]{64}$", digest):
                    raise ValueError(
                        "pinnedPeerCertSha256 must be a hex SHA-256 digest "
                        "(64 hex characters), not %r" % digest
                    )
            # A string, with multiple hashes separated by commas - not an array.
            tls["pinnedPeerCertSha256"] = ",".join(pinned)
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
    query = parse_query(parsed.query)
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
    return url_decode(netloc[0])


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
    # In a VMess share link "type" is the *header obfuscation* ("none", "http"),
    # not the transport - that is "net". Feeding "type" to the transport parser
    # rejected every link v2rayN and v2rayNG produce, because they always emit
    # "type":"none".
    stream_values.pop("type", None)
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
    query = parse_query(query_string) if separator else {}
    if query_value(query, "plugin", ""):
        raise ValueError("Shadowsocks plugins are not supported")

    if "@" in body:
        credential_part, server_part = body.rsplit("@", 1)
        decoded_credentials = url_decode(credential_part)
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
    if "://" in entries[0] and not entries[0].lower().startswith(SUPPORTED_SCHEMES):
        raise ValueError(
            "line 1 uses an unsupported protocol; only VLESS, VMess, Trojan "
            "and Shadowsocks links are supported"
        )
    if entries[0].lower().startswith(SUPPORTED_SCHEMES):
        profiles = []
        rejected = []
        for index, entry in enumerate(entries, 1):
            # A single unusable line - an unsupported protocol, a typo, a
            # provider's comment - used to discard the entire file and leave the
            # user with "No Config. Found" and no idea why. Bad lines are
            # skipped and reported instead.
            if not entry.lower().startswith(SUPPORTED_SCHEMES):
                rejected.append("line %d: unsupported protocol" % index)
                continue
            try:
                parsed = parse_share_link(entry)
            except ValueError as error:
                rejected.append("line %d: %s" % (index, as_text(error)))
                continue
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
        if not profiles:
            raise ValueError("; ".join(rejected) or "no usable configuration")
        for message in rejected:
            print("Skipped %s" % as_text(message), file=sys.stderr)
        return profiles
    # The whole file is the identity of a legacy config, but it must not be
    # used as the display name: fragment_name splits on "#", so any comment
    # line turned the profile name into the file's contents - including the
    # UUID, shown on screen and written to the runtime file.
    legacy = parse_legacy(content)
    legacy["_NAME"] = "%s %s" % (
        legacy["PROTOCOL"].upper(),
        legacy["SERVER_ADDRESS"],
    )
    return [finalize_profile(legacy, "#" + legacy["_NAME"], 1)]


def read_selection(path):
    try:
        with io.open(path, "r", encoding="ascii") as source:
            profile_id = source.readline().strip().lower()
    except (IOError, OSError):
        return ""
    except ValueError:
        # A hand-edited or corrupted file raises UnicodeDecodeError, which is a
        # ValueError. It used to escape all the way out of an Enigma2 keypress
        # callback and take the GUI down.
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


def clear_selection(path):
    try:
        os.unlink(path)
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise


def select_profile(profiles, selection_path, fallback=True):
    selected_id = read_selection(selection_path)
    for profile in profiles:
        if profile["PROFILE_ID"] == selected_id:
            return profile
    if fallback and profiles:
        return profiles[0]
    return None


def ensure_selection(profiles, selection_path):
    """Guarantee that some profile is selected.

    A freshly installed plugin has a populated config.txt but no selection yet,
    so pressing Start used to fail with "No Configuration Selected" even though
    a perfectly usable profile was sitting in the list. The first profile is
    adopted automatically whenever the stored selection is missing or stale.

    Returns the selected profile, or None when there is nothing to select.
    """
    if not profiles:
        return None
    selected = select_profile(profiles, selection_path, fallback=False)
    if selected is not None:
        return selected
    first = profiles[0]
    try:
        write_selection(selection_path, first["PROFILE_ID"])
    except (IOError, OSError, ValueError):
        # A read-only /etc must not stop the profile from being used.
        pass
    return first


def read_config(path, selection_path):
    return select_profile(read_profiles(path), selection_path)


def sniffing_settings():
    # Transparent inbounds only see the destination IP the receiver already
    # resolved locally. Recovering the hostname from the HTTP/TLS/QUIC handshake
    # is what lets the remote server resolve the name itself, so a poisoned
    # local resolver no longer decides where the connection really goes.
    return {
        "enabled": True,
        "destOverride": ["http", "tls", "quic"],
        "routeOnly": False,
    }


def transparent_settings(networks, follow_redirect=True):
    # Xray v25+ renamed the dokodemo-door fields. Both spellings are emitted so
    # one generated config loads on either core generation.
    return {
        "allowedNetwork": networks,
        "network": networks,
        "followRedirect": follow_redirect,
    }


def build_dns_inbound(dns_server="8.8.8.8"):
    # Xray v26 renamed these on the inbound: "rewriteAddress"/"rewritePort" are
    # the current names, "address"/"port" the original ones. Both are emitted so
    # one generated config loads on either core generation - the same approach
    # already used for allowedNetwork/network.
    # "rewriteNetwork" is NOT an inbound field; it belongs to the dns outbound.
    # Setting it here did nothing, which is why the old "DNS over TCP" path
    # never actually took effect.
    settings = transparent_settings("tcp,udp", follow_redirect=False)
    settings["rewriteAddress"] = dns_server
    settings["address"] = dns_server
    settings["rewritePort"] = 53
    settings["port"] = 53
    return {
        "tag": "dns-in",
        "listen": "127.0.0.1",
        "port": DNS_PORT,
        "protocol": "dokodemo-door",
        "settings": settings,
    }


def build_dns_outbound():
    """Hands DNS queries to the core's own resolver.

    With no rules the documented default imports A and AAAA queries into the
    built-in DNS module, which then queries its configured servers. Those
    upstream queries follow the routing rules and carry the dns tag, so they can
    be forced through the proxy.
    """
    return {"tag": "dns-out", "protocol": "dns", "settings": {}}


DNS_INTERNAL_TAG = "dns-internal"


def build_inbounds(backend, interface="auto", dns_server="8.8.8.8", dns_over_tcp=False):
    backend = as_text(backend or "tun").strip().lower()

    if backend == "tun":
        tun_inbounds = [
            {
                "tag": "tun-in",
                "protocol": "tun",
                "settings": {
                    "name": "e2xray0",
                    "mtu": 1492,
                    # A ULA is assigned alongside the IPv4 gateway so IPv6 can
                    # be captured too. Without it the interface has no v6
                    # address, no v6 default route can point at it, and every
                    # AAAA-capable destination leaves the receiver natively -
                    # outside the tunnel - on any connection that offers IPv6.
                    "gateway": [TUN_GATEWAY4, TUN_GATEWAY6],
                    "autoOutboundsInterface": interface or "auto",
                },
                "sniffing": sniffing_settings(),
            }
        ]
        if dns_over_tcp:
            # Shadowsocks: the receiver's own queries are captured here so they
            # can be carried over TCP instead of being sent out in the clear.
            tun_inbounds.append(build_dns_inbound(dns_server))
        return tun_inbounds

    if backend == "tproxy":
        sockopt = {"tproxy": "tproxy"}
        networks = "tcp,udp"
    elif backend == "redirect":
        sockopt = {"tproxy": "redirect"}
        networks = "tcp"
    else:
        raise ValueError("unsupported network backend: %s" % backend)

    # "tunnel" is the current name and "dokodemo-door" the original one; both
    # resolve to the same proxy. The original name is used because it is the
    # one every core generation registers.
    return [
        {
            "tag": "transparent-in",
            "listen": "0.0.0.0",
            "port": TRANSPARENT_PORT,
            "protocol": "dokodemo-door",
            "settings": transparent_settings(networks),
            "sniffing": sniffing_settings(),
            "streamSettings": {"sockopt": sockopt},
        },
        build_dns_inbound(dns_server),
    ]


def build_inbound(backend, interface="auto"):
    return build_inbounds(backend, interface)[0]


# A filtered domain resolves to the censor's block page rather than failing.
# Such an answer must never be treated as a normal private address and sent out
# direct, or the request for the blocked site leaves the receiver in the clear
# and lands on the filtering page while the tunnel reports itself healthy.
FILTERING_SINKHOLES = ["10.10.34.0/24"]

PRIVATE_NETWORKS = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "255.255.255.255/32",
    # IPv6 is captured as well, so its local scopes need the same treatment.
    # fdfe:e2e2::/64 is the tunnel's own prefix and must never be proxied.
    "::1/128",
    "fdfe:e2e2::/64",
    "fe80::/10",
    "ff00::/8",
]


def normalize_bypass_ips(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        candidates = as_text(value).replace(",", " ").split()
    result = []
    for candidate in candidates:
        address = as_text(candidate).strip()
        if not address:
            continue
        if not re.match(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$", address):
            continue
        if address not in result:
            result.append(address)
    return result


def normalize_server_ips(value):
    """Resolved server addresses, IPv4 and IPv6, in preference order."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        candidates = as_text(value).replace(",", " ").split()
    v4 = []
    v6 = []
    for candidate in candidates:
        address = as_text(candidate).strip()
        if not address or not is_ip_literal(address):
            continue
        target = v6 if ":" in address else v4
        if address not in target:
            target.append(address)
    return v4 + v6


def build_routing_rules(parsed, backend, bypass_ips=None):
    rules = []
    # Card-sharing servers must leave the receiver untouched. This rule is the
    # last line of defence: the OS-level bypass normally keeps the traffic away
    # from the core entirely, but if a packet still arrives it is sent straight
    # out through the freedom outbound instead of into the tunnel.
    bypass = normalize_bypass_ips(bypass_ips)
    if bypass:
        rules.append(
            {
                "type": "field",
                "ip": ["%s/32" % address for address in bypass],
                "outboundTag": "direct",
            }
        )
    # The dedicated DNS inbound must never fall back to the receiver's own
    # resolver, otherwise transparent mode inherits the poisoned answers it was
    # added to avoid.
    if parsed.get("PROTOCOL") == "shadowsocks":
        # Shadowsocks servers often refuse to relay UDP, and the old answer to
        # that was to send UDP/53 out direct - which handed every lookup to the
        # ISP resolver in the clear and got a poisoned answer back, defeating
        # the entire point of the tunnel. Instead the query is handed to the
        # core's own resolver, which is configured with tcp:// servers, so it
        # travels over the Shadowsocks TCP connection and never needs UDP.
        rules.append(
            {
                "type": "field",
                "inboundTag": ["dns-in"],
                "outboundTag": "dns-out",
            }
        )
        rules.append(
            {
                "type": "field",
                "inboundTag": [DNS_INTERNAL_TAG],
                "outboundTag": "proxy",
            }
        )
    elif backend != "tun":
        rules.append(
            {
                "type": "field",
                "inboundTag": ["dns-in"],
                "outboundTag": "proxy",
            }
        )
    # Must precede the private-network rule: the sinkhole lives inside 10/8.
    rules.append(
        {
            "type": "field",
            "ip": list(FILTERING_SINKHOLES),
            "outboundTag": "block",
        }
    )
    rules.append(
        {"type": "field", "ip": list(PRIVATE_NETWORKS), "outboundTag": "direct"}
    )
    return rules


def apply_socket_options(config_data, interface="auto", mark=SELF_MARK):
    interface = as_text(interface or "auto").strip()
    for outbound in config_data.get("outbounds", []):
        tag = outbound.get("tag")
        if tag == "block":
            continue
        sockopt = outbound.setdefault("streamSettings", {}).setdefault("sockopt", {})
        sockopt["mark"] = mark
        # Only the proxy transport is pinned to the physical interface. Binding
        # the freedom outbound too would break the loopback and LAN traffic that
        # routing deliberately sends out direct.
        if tag == "proxy" and interface and interface != "auto":
            sockopt["interface"] = interface
    return config_data


def build_xray_config(parsed, backend="tun", interface="auto"):
    backend = as_text(backend or "tun").strip().lower()
    dns_over_tcp = parsed.get("PROTOCOL") == "shadowsocks"
    outbounds = [
        parsed["outbound"],
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
    ]
    if dns_over_tcp:
        # tcp:// keeps the lookup on the proxy's TCP connection, and it is the
        # documented form whose queries still follow the routing rules; the tag
        # is what lets those queries be aimed at the proxy.
        dns_settings = {
            "servers": ["tcp://8.8.8.8", "tcp://1.1.1.1"],
            "tag": DNS_INTERNAL_TAG,
        }
        outbounds.append(build_dns_outbound())
    else:
        dns_settings = {"servers": ["8.8.8.8", "1.1.1.1"]}
    config_data = {
        "log": {"loglevel": "warning"},
        "dns": dns_settings,
        "inbounds": build_inbounds(backend, interface, "8.8.8.8", dns_over_tcp),
        "outbounds": outbounds,
        "routing": {
            # "AsIs", not "IPIfNonMatch". Sniffing hands routing a domain, and
            # IPIfNonMatch makes the core resolve that domain locally just to
            # test the IP-only rules below. Those lookups are the core's own
            # sockets, which every backend deliberately routes around the
            # tunnel, so the receiver ends up emitting a cleartext DNS query to
            # 8.8.8.8 for every single site it visits - handing the full
            # browsing history to exactly the network the plugin exists to hide
            # from, and on a filtering ISP getting a poisoned answer back.
            # Nothing is lost: private and card-sharing destinations never reach
            # the core at all, because the OS-level routes and iptables RETURN
            # rules already send them out directly.
            "domainStrategy": "AsIs",
            "rules": build_routing_rules(parsed, backend),
        },
    }
    return apply_socket_options(config_data, interface)

def shell_quote(value):
    return "'" + as_text(value).replace("'", "'\"'\"'") + "'"


def atomic_write(path, content, mode=0o600):
    temporary_path = path + ".tmp"
    with io.open(temporary_path, "w", encoding="utf-8") as output:
        output.write(content)
    os.chmod(temporary_path, mode)
    replace = getattr(os, "replace", os.rename)
    replace(temporary_path, path)


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


def is_ip_literal(value):
    value = as_text(value).strip()
    if re.match(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$", value):
        return True
    # An IPv6 literal is already an address and must never be "resolved" or
    # replaced; the server may legitimately be reachable only over IPv6.
    return ":" in value and bool(re.match(r"^[0-9A-Fa-f:.]+$", value))


def pin_server_address(config_data, server_ips):
    """Dial the proxy by pre-resolved IP instead of by name.

    Xray resolves the outbound host itself, and in TUN mode that lookup is
    routed into the very tunnel the lookup is needed to build:

        failed to dial to cdn2.example:443 > dial tcp: lookup cdn2.example
        on 1.1.1.1:53: read udp 10.255.0.1:36577->1.1.1.1:53: i/o timeout

    The query leaves from the TUN address, never gets an answer, and every
    hostname-based profile hangs forever while the receiver loses all working
    DNS. The control script has already resolved the name over the untouched
    resolver, so the address is pinned here and the name is preserved wherever
    the handshake still needs it: TLS/REALITY SNI, the WebSocket and XHTTP Host
    header, and the gRPC authority.

    Returns the host name that was pinned, or "" when nothing changed.
    """
    addresses = normalize_server_ips(server_ips)
    if not addresses:
        return ""
    for outbound in config_data.get("outbounds", []):
        if outbound.get("tag") != "proxy":
            continue
        settings = outbound.get("settings")
        if not isinstance(settings, dict):
            return ""
        host = as_text(settings.get("address", "")).strip()
        if not host or is_ip_literal(host):
            return ""

        stream = outbound.setdefault("streamSettings", {})
        for security_key in ("tlsSettings", "realitySettings"):
            security = stream.get(security_key)
            if isinstance(security, dict) and not security.get("serverName"):
                security["serverName"] = host
        for transport_key, field in (
            ("wsSettings", "host"),
            ("xhttpSettings", "host"),
            ("grpcSettings", "authority"),
        ):
            transport = stream.get(transport_key)
            if isinstance(transport, dict) and not transport.get(field):
                transport[field] = host

        settings["address"] = addresses[0]
        return host
    return ""


def set_network_backend(
    path, backend, interface="auto", bypass_ips=None, server_ips=None
):
    backend = as_text(backend).strip().lower()
    interface = as_text(interface or "auto").strip()
    if interface != "auto" and not re.match(r"^[A-Za-z0-9_.:-]+$", interface):
        raise ValueError("invalid outbound interface")
    if backend not in ("tun", "tproxy", "redirect"):
        raise ValueError("unsupported network backend: %s" % backend)
    with io.open(path, "r", encoding="utf-8") as source:
        config_data = json.load(source)

    protocol = ""
    for outbound in config_data.get("outbounds", []):
        if outbound.get("tag") == "proxy":
            protocol = as_text(outbound.get("protocol", ""))
            break
    dns_over_tcp = protocol == "shadowsocks"

    config_data["inbounds"] = build_inbounds(
        backend, interface, "8.8.8.8", dns_over_tcp
    )
    config_data.setdefault("routing", {})["rules"] = build_routing_rules(
        {"PROTOCOL": protocol}, backend, bypass_ips
    )
    if dns_over_tcp:
        config_data["dns"] = {
            "servers": ["tcp://8.8.8.8", "tcp://1.1.1.1"],
            "tag": DNS_INTERNAL_TAG,
        }
        outbounds = config_data.setdefault("outbounds", [])
        if not any(item.get("tag") == "dns-out" for item in outbounds):
            outbounds.append(build_dns_outbound())
    else:
        config_data["dns"] = {"servers": ["8.8.8.8", "1.1.1.1"]}
        config_data["outbounds"] = [
            item
            for item in config_data.get("outbounds", [])
            if item.get("tag") != "dns-out"
        ]
    # Tag every outbound with the self fwmark and bind it to the receiver's real
    # interface. Without the mark, Xray's own transport is re-captured by the
    # TPROXY/REDIRECT chains and the connection loops back into itself.
    apply_socket_options(config_data, interface)
    pinned = pin_server_address(config_data, server_ips)
    content = json.dumps(
        config_data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write(path, as_text(content) + "\n")
    if pinned:
        emit("PINNED_SERVER=%s" % pinned)

def bind_tun_interface(path, interface):
    # Backward-compatible helper retained for existing tests/tools.
    set_network_backend(path, "tun", interface)


def build_probe_config(parsed, socks_port):
    outbound = json.loads(json.dumps(parsed["outbound"]))
    outbound.setdefault("streamSettings", {}).setdefault("sockopt", {})[
        "mark"
    ] = SELF_MARK
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "probe-in",
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": False},
            }
        ],
        "outbounds": [outbound],
    }


def _free_local_port(socket_module):
    probe = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


def _wait_for_listener(socket_module, time_module, port, deadline):
    while time_module.time() < deadline:
        probe = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
        probe.settimeout(0.5)
        try:
            probe.connect(("127.0.0.1", port))
            return True
        except Exception:
            time_module.sleep(0.2)
        finally:
            probe.close()
    return False


def _recv_exact(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ValueError("the probe connection closed early")
        chunks.extend(chunk)
    return chunks


def _socks5_connect(sock, host, port):
    sock.sendall(b"\x05\x01\x00")
    if _recv_exact(sock, 2) != bytearray(b"\x05\x00"):
        raise ValueError("SOCKS5 handshake was rejected")

    host_bytes = host.encode("utf-8")
    request = bytearray(b"\x05\x01\x00\x03")
    request.append(len(host_bytes))
    request.extend(host_bytes)
    request.append(port >> 8)
    request.append(port & 0xFF)
    sock.sendall(bytes(request))

    reply = _recv_exact(sock, 4)
    if reply[1] != 0:
        raise ValueError("SOCKS5 CONNECT was refused")
    address_type = reply[3]
    if address_type == 1:
        _recv_exact(sock, 6)
    elif address_type == 4:
        _recv_exact(sock, 18)
    elif address_type == 3:
        _recv_exact(sock, _recv_exact(sock, 1)[0] + 2)
    else:
        raise ValueError("SOCKS5 returned an unknown address type")


def measure_real_delay(xray_binary, parsed, work_dir, timeout=12):
    """Time a full HTTP round trip through the profile, the way clients do.

    A TCP connect to the server only proves the edge is reachable; it says
    nothing about whether the tunnel itself carries traffic.
    """
    import socket
    import subprocess
    import time

    port = _free_local_port(socket)
    config_path = os.path.join(work_dir, "probe.json")
    content = json.dumps(build_probe_config(parsed, port), ensure_ascii=False)
    atomic_write(config_path, as_text(content) + "\n")

    devnull = open(os.devnull, "wb")
    process = subprocess.Popen(
        [xray_binary, "run", "-c", config_path],
        stdout=devnull,
        stderr=devnull,
    )
    try:
        deadline = time.time() + timeout
        if not _wait_for_listener(socket, time, port, deadline):
            raise ValueError("the probe instance did not start")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(max(1, int(deadline - time.time())))
        try:
            sock.connect(("127.0.0.1", port))
            _socks5_connect(sock, PROBE_HOST, 80)
            request = (
                "GET %s HTTP/1.1\r\nHost: %s\r\n"
                "User-Agent: e2xray\r\nConnection: close\r\n\r\n"
                % (PROBE_PATH, PROBE_HOST)
            )
            started = time.time()
            sock.sendall(request.encode("ascii"))
            response = sock.recv(64)
            elapsed = time.time() - started
        finally:
            sock.close()
    finally:
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait()
        except Exception:
            pass
        devnull.close()
        try:
            os.unlink(config_path)
        except OSError:
            pass

    if not response.startswith(b"HTTP/"):
        raise ValueError("the probe target did not answer over the tunnel")
    return max(1, int(round(elapsed * 1000)))


# ---------------------------------------------------------------------------
# Card-sharing (softcam) bypass discovery
#
# OSCam/CCcam/mgcamd talk to card-sharing servers on arbitrary public IPs and
# ports. Once the transparent backend captures every outbound connection, that
# traffic is pushed through the proxy too, where it is usually blocked or
# mangled -- which is why encrypted channels stop opening while e2xray runs.
#
# The endpoints are discovered automatically so the user never has to configure
# anything, from two independent sources:
#   1. The live sockets the running softcam process already owns. This is exact
#      and needs no knowledge of the config format.
#   2. The softcam configuration files, which also cover peers that happen to be
#      disconnected at the moment e2xray starts.
# ---------------------------------------------------------------------------

SOFTCAM_PROCESS_NAMES = (
    "oscam",
    "cccam",
    "mgcamd",
    "gbox",
    "ncam",
    "camd3",
    "newcs",
    "wicardd",
    "doscam",
    "supcam",
    "mbox",
    "rqcamd",
    "cardserverproxy",
)

SOFTCAM_CONFIG_DIRECTORIES = (
    "/etc",
    "/etc/tuxbox/config",
    "/etc/tuxbox/config/oscam",
    "/etc/tuxbox/config/oscam-emu",
    "/etc/tuxbox/config/ncam",
    "/usr/keys",
    "/var/keys",
    "/var/etc",
    "/etc/clist",
)

SOFTCAM_CONFIG_NAMES = (
    "CCcam.cfg",
    "cccam.cfg",
    "CCcam.prio",
    "oscam.server",
    "ncam.server",
    "newcamd.list",
    "mgcamd.list",
    "cccamd.list",
    "camd3.list",
    "wicardd.conf",
)

# Only used as a last-resort net for ports that no discovery source revealed.
# These are the defaults shipped by the common card-sharing daemons.
SOFTCAM_DEFAULT_PORTS = (12000, 15000, 16000, 34000)

# A port bypass is not qualified by destination address - it has to work when a
# reader reconnects to a different address of the same dynamic name. That makes
# it a blunt instrument: bypassing port 443 because someone runs a peer there
# would push ALL HTTPS traffic outside the tunnel and silently disable the whole
# plugin. Ports that carry ordinary traffic are therefore never bypassed by
# port alone; such a peer is still covered by its discovered address.
SOFTCAM_UNSAFE_PORTS = frozenset(
    [80, 443, 853, 1080, 3128, 5228, 8080, 8443, 8888]
)


def is_safe_bypass_port(port):
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if port < 1024 or port > 65535:
        return False
    return port not in SOFTCAM_UNSAFE_PORTS

_PRIVATE_PREFIXES = ("0.", "10.", "127.", "169.254.", "172.", "192.168.", "100.")


def is_public_ipv4(address):
    parts = as_text(address).split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(part) for part in parts]
    except (TypeError, ValueError):
        return False
    for octet in octets:
        if octet < 0 or octet > 255:
            return False
    first, second = octets[0], octets[1]
    if first in (0, 10, 127):
        return False
    if first == 172 and 16 <= second <= 31:
        return False
    if first == 192 and second == 168:
        return False
    if first == 169 and second == 254:
        return False
    if first == 100 and 64 <= second <= 127:
        return False
    if first >= 224:
        return False
    return True


def softcam_pids():
    """PIDs of every running card-sharing daemon."""
    found = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        name = ""
        try:
            with open("/proc/%s/comm" % entry, "rb") as source:
                name = source.read().decode("utf-8", "replace").strip()
        except (IOError, OSError):
            name = ""
        if not name:
            try:
                with open("/proc/%s/cmdline" % entry, "rb") as source:
                    raw = source.read().decode("utf-8", "replace")
                name = os.path.basename(raw.split("\x00", 1)[0])
            except (IOError, OSError):
                continue
        lowered = os.path.basename(name.lower())
        for candidate in SOFTCAM_PROCESS_NAMES:
            # Anchored, not "in": a bare substring test let short names such as
            # "mbox" or "gbox" match unrelated daemons and pull their peers into
            # the bypass.
            if lowered == candidate or lowered.startswith(candidate):
                found.append(entry)
                break
    return found


def _socket_inodes(pid):
    inodes = set()
    directory = "/proc/%s/fd" % pid
    try:
        names = os.listdir(directory)
    except OSError:
        return inodes
    for name in names:
        try:
            target = os.readlink(os.path.join(directory, name))
        except OSError:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            inodes.add(target[8:-1])
    return inodes


def _hex_to_ipv4(value):
    # /proc/net/tcp stores the address as a little-endian 32-bit hex word.
    if len(value) != 8:
        return ""
    try:
        packed = int(value, 16)
    except ValueError:
        return ""
    return "%d.%d.%d.%d" % (
        packed & 0xFF,
        (packed >> 8) & 0xFF,
        (packed >> 16) & 0xFF,
        (packed >> 24) & 0xFF,
    )


def _proc_net_tcp_entries():
    """Map socket inode -> (remote ip, remote port) for every IPv4 TCP socket."""
    entries = {}
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path, "r") as source:
                lines = source.readlines()
        except (IOError, OSError):
            continue
        for line in lines[1:]:
            fields = line.split()
            if len(fields) < 10:
                continue
            remote = fields[2].split(":")
            if len(remote) != 2:
                continue
            address, port_hex = remote
            if len(address) == 32:
                # Only a genuinely v4-mapped address may be reduced to its last
                # word. Doing it unconditionally turned a real IPv6 peer into a
                # fabricated public IPv4 address, which then received a
                # permanent bypass route belonging to somebody else.
                if address[:24].upper() != "0000000000000000FFFF0000":
                    continue
                address = address[24:]
            ip_address = _hex_to_ipv4(address)
            if not ip_address:
                continue
            try:
                port = int(port_hex, 16)
            except ValueError:
                continue
            if port < 1 or port > 65535:
                continue
            entries[fields[9]] = (ip_address, port)
    return entries


def softcam_live_endpoints():
    """Remote endpoints the running softcam processes are connected to."""
    pids = softcam_pids()
    if not pids:
        return []
    sockets = _proc_net_tcp_entries()
    if not sockets:
        return []
    results = []
    for pid in pids:
        for inode in _socket_inodes(pid):
            endpoint = sockets.get(inode)
            if endpoint is None:
                continue
            if not is_public_ipv4(endpoint[0]):
                continue
            results.append(endpoint)
    return results


def _softcam_config_files():
    paths = []
    for directory in SOFTCAM_CONFIG_DIRECTORIES:
        for name in SOFTCAM_CONFIG_NAMES:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                paths.append(path)
    return paths


def _clean_host(value):
    host = as_text(value).strip().strip(",").strip()
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    if not host or host.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
        return ""
    if any(character in host for character in " \t/\\'\"$;|"):
        return ""
    return host


def softcam_config_endpoints():
    """(host, port) pairs declared in the installed softcam configuration."""
    results = []
    # CCcam:        C: host port user pass      /  N: host port user pass ...
    # mgcamd:       CWS = host port user pass ...
    # OSCam:        device = host,port          (inside a [reader] block)
    cccam_line = re.compile(r"^[CN]:\s*(\S+)\s+([0-9]{1,5})\b")
    cws_line = re.compile(r"^\s*CWS\s*=\s*(\S+)\s+([0-9]{1,5})\b", re.IGNORECASE)
    device_line = re.compile(
        r"^\s*device\s*=\s*([^,\s]+)\s*,\s*([0-9]{1,5})", re.IGNORECASE
    )
    for path in _softcam_config_files():
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as source:
                content = source.read()
        except (IOError, OSError):
            continue
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            for pattern in (cccam_line, cws_line, device_line):
                match = pattern.match(line)
                if not match:
                    continue
                host = _clean_host(match.group(1))
                if not host:
                    break
                try:
                    port = parse_port(match.group(2))
                except ValueError:
                    break
                results.append((host, port))
                break
    return results


def _resolve_host(host):
    if not re.search(r"[^0-9.]", host):
        return [host] if is_public_ipv4(host) else []
    import socket

    addresses = []
    try:
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            address = info[4][0]
            if is_public_ipv4(address):
                addresses.append(address)
    except Exception:
        return []
    return addresses


def discover_softcam_bypass():
    """Public card-sharing IPs and ports that must never enter the tunnel."""
    ip_addresses = []
    ports = []

    dropped_ports = []

    def remember(address, port):
        if address and address not in ip_addresses:
            ip_addresses.append(address)
        if not port:
            return
        if not is_safe_bypass_port(port):
            # The address of such a peer is still bypassed; only the unqualified
            # port rule is refused.
            if port not in dropped_ports:
                dropped_ports.append(port)
            return
        if port not in ports:
            ports.append(port)

    for address, port in softcam_live_endpoints():
        remember(address, port)

    for host, port in softcam_config_endpoints():
        resolved = _resolve_host(host)
        if resolved:
            for address in resolved:
                remember(address, port)
        else:
            # The name did not resolve (no DNS yet, or a dead peer). The port is
            # still worth bypassing so the reader can reconnect later.
            remember("", port)

    if not ports and not dropped_ports and (ip_addresses or softcam_pids()):
        ports = list(SOFTCAM_DEFAULT_PORTS)

    return ip_addresses, sorted(ports), sorted(dropped_ports)


def print_softcam_bypass():
    ip_addresses, ports, dropped_ports = discover_softcam_bypass()
    emit("SOFTCAM_BYPASS_IPS=%s" % shell_quote(" ".join(ip_addresses)))
    emit("SOFTCAM_BYPASS_PORTS=%s" % shell_quote(" ".join(str(p) for p in ports)))
    # Surfaced rather than dropped silently: a peer on a shared port is a real
    # configuration the user may need to hear about.
    emit(
        "SOFTCAM_UNSAFE_PORTS=%s"
        % shell_quote(" ".join(str(p) for p in dropped_ports))
    )
    return 0


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--softcam-bypass":
        try:
            return print_softcam_bypass()
        except Exception as error:
            print("Softcam bypass discovery failed: %s" % as_text(error), file=sys.stderr)
            print("SOFTCAM_BYPASS_IPS=''")
            print("SOFTCAM_BYPASS_PORTS=''")
            return 0
    if len(sys.argv) in (4, 5, 6, 7) and sys.argv[1] == "--set-backend":
        try:
            backend = sys.argv[3]
            interface = sys.argv[4] if len(sys.argv) >= 5 else "auto"
            bypass_ips = sys.argv[5] if len(sys.argv) >= 6 else ""
            server_ips = sys.argv[6] if len(sys.argv) == 7 else ""
            set_network_backend(
                sys.argv[2], backend, interface, bypass_ips, server_ips
            )
        except Exception as error:
            print("Could not configure Xray network backend: %s" % as_text(error), file=sys.stderr)
            return 1
        return 0
    if len(sys.argv) == 6 and sys.argv[1] == "--realping":
        try:
            profiles = read_profiles(sys.argv[3])
            parsed = select_profile(profiles, sys.argv[4], fallback=False)
            if parsed is None:
                raise ValueError("no configuration selected")
            delay = measure_real_delay(sys.argv[2], parsed, sys.argv[5])
        except Exception as error:
            print("Real delay test failed: %s" % as_text(error), file=sys.stderr)
            return 1
        print("REAL_DELAY_MS=%d" % delay)
        print("REAL_DELAY_ID=%s" % parsed["PROFILE_ID"])
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "--ensure-selection":
        try:
            profiles = read_profiles(sys.argv[2])
            selected = ensure_selection(profiles, sys.argv[3])
            if selected is None:
                raise ValueError("no configuration found")
        except Exception as error:
            print("Could not select a configuration: %s" % as_text(error), file=sys.stderr)
            return 1
        emit("SELECTED_ID=%s" % selected["PROFILE_ID"])
        emit("SELECTED_NAME=%s" % selected["PROFILE_NAME"])
        return 0
    if len(sys.argv) != 5:
        print(
            "Usage: proxy_config.py INPUT SELECTION RUNTIME_OUTPUT XRAY_CONFIG_OUTPUT\n"
            "       proxy_config.py --set-backend XRAY_CONFIG BACKEND [INTERFACE]"
            " [BYPASS_IPS] [SERVER_IPS]\n"
            "       proxy_config.py --realping XRAY_BINARY INPUT SELECTION WORK_DIR\n"
            "       proxy_config.py --ensure-selection INPUT SELECTION\n"
            "       proxy_config.py --softcam-bypass",
            file=sys.stderr,
        )
        return 2
    try:
        profiles = read_profiles(sys.argv[1])
        parsed = select_profile(profiles, sys.argv[2], fallback=False)
        if parsed is None:
            raise ValueError("no configuration selected")
        write_runtime(sys.argv[3], parsed)
        write_xray_config(sys.argv[4], parsed)
    except Exception as error:
        print("Invalid e2xray configuration: %s" % as_text(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
