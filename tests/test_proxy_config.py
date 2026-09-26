#!/usr/bin/env python3
from __future__ import print_function

import base64
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
PARSER_PATH = (
    ROOT
    / "usr"
    / "lib"
    / "enigma2"
    / "python"
    / "Plugins"
    / "Extensions"
    / "e2xray"
    / "proxy_config.py"
)

spec = importlib.util.spec_from_file_location("proxy_config", PARSER_PATH)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)

assert parser.decode_base64("SGVsbG8=") == "Hello"
assert parser.decode_base64("8J-YgA") == "😀"
try:
    parser.decode_base64("invalid!")
    raise AssertionError("invalid base64 was accepted")
except ValueError:
    pass


vmess = {
    "v": "2",
    "add": "198.51.100.2",
    "port": "443",
    "id": "22222222-2222-4222-8222-222222222222",
    "scy": "auto",
    "net": "xhttp",
    "path": "/xhttp",
    "host": "vmess.example.com",
    "tls": "tls",
    "sni": "vmess.example.com",
    "fp": "chrome",
    "ps": "VMess Main",
}
vmess_link = "vmess://" + base64.urlsafe_b64encode(
    json.dumps(vmess).encode()
).decode().rstrip("=")

xhttp_link = (
    "vless://bd146f3c-a00d-45e9-a9d4-b4c416362063"
    "@87.107.195.57:2092?encryption=none&security=tls"
    "&sni=servitro.alimail.ir&fp=chrome"
    "&alpn=h2%2Chttp%2F1.1%2Ch3&insecure=0&allowInsecure=0"
    "&type=xhttp&host=servitro.alimail.ir&path=%2F&mode=auto"
    "&extra=%7B%22xPaddingBytes%22%3A%22100-1000%22%7D#2092"
)
persian_name_link = (
    "vless://6d9ffde9-6823-4cea-894a-687284ce00a8"
    "@162.159.39.85:8443?encryption=none&security=tls"
    "&sni=1.yekseda.workers.dev&fp=chrome"
    "&insecure=0&allowInsecure=0&type=ws"
    "&host=1.yekseda.workers.dev&path=%2F"
    "#%D8%B3%D8%B1%D9%88%DB%8C%D8%B3%20%D8%B1%D8%A7%DB%8C%DA%AF%D8%A7%D9%86"
    "%20%D9%86%D9%88%D8%A7%209"
)

assert parser.parse_share_link(persian_name_link)["PROFILE_NAME"] == (
    "سرویس رایگان نوا 9"
)

parsed_xhttp = parser.parse_share_link(xhttp_link)
assert parsed_xhttp["PROFILE_NAME"] == "2092"
assert parsed_xhttp["outbound"]["streamSettings"]["network"] == "xhttp"
assert "method" not in parsed_xhttp["outbound"]["streamSettings"]
assert parsed_xhttp["outbound"]["streamSettings"]["tlsSettings"]["alpn"] == [
    "h2",
    "http/1.1",
    "h3",
]
assert parsed_xhttp["outbound"]["streamSettings"]["xhttpSettings"]["extra"][
    "xPaddingBytes"
] == "100-1000"

cases = [
    (
        "vless://11111111-1111-4111-8111-111111111111@192.0.2.1:2096"
        "?encryption=none&security=tls&sni=example.com&fp=chrome"
        "&type=ws&host=example.com&path=%2F#Germany%201",
        "vless",
        "websocket",
    ),
    (vmess_link, "vmess", "xhttp"),
    (
        "trojan://secret@203.0.113.3:443?security=reality"
        "&sni=example.org&fp=chrome&pbk=public-key&sid=abcd&type=grpc"
        "&serviceName=route#Trojan%20Main",
        "trojan",
        "grpc",
    ),
    (
        "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ@203.0.113.4:8388#SS%20Main",
        "shadowsocks",
        "raw",
    ),
]

for link, protocol, network in cases:
    parsed = parser.parse_share_link(link)
    assert parsed["PROTOCOL"] == protocol
    assert parsed["outbound"]["protocol"] == protocol
    assert parsed["outbound"]["streamSettings"]["network"] == network
    config = parser.build_xray_config(parsed)
    assert config["inbounds"][0]["protocol"] == "tun"
    assert config["outbounds"][0]["tag"] == "proxy"
    dns_direct_rules = [
        rule
        for rule in config["routing"]["rules"]
        if rule.get("network") == "udp"
        and rule.get("port") == "53"
        and rule.get("outboundTag") == "direct"
    ]
    # No protocol may send DNS out direct any more: that used to hand every
    # lookup to the ISP resolver in the clear and get a poisoned answer back.
    assert dns_direct_rules == [], protocol
    if protocol == "shadowsocks":
        # Carried over the proxy's TCP connection, so no UDP relay is needed.
        assert config["dns"]["servers"] == ["tcp://8.8.8.8", "tcp://1.1.1.1"]
    else:
        assert config["dns"]["servers"] == ["8.8.8.8", "1.1.1.1"]

with TemporaryDirectory() as folder:
    config_path = Path(folder) / "config.txt"
    selection_path = Path(folder) / "selected"
    runtime_path = Path(folder) / "user.conf"
    xray_path = Path(folder) / "xray.json"
    config_path.write_text(
        "\n".join(case[0] for case in cases) + "\n",
        encoding="utf-8",
    )
    profiles = parser.read_profiles(str(config_path))
    assert parser.select_profile(
        profiles,
        str(selection_path),
        fallback=False,
    ) is None
    assert [item["PROFILE_NAME"] for item in profiles] == [
        "Germany 1",
        "VMess Main",
        "Trojan Main",
        "SS Main",
    ]
    assert len({item["PROFILE_ID"] for item in profiles}) == 4
    parser.write_selection(
        str(selection_path),
        profiles[2]["PROFILE_ID"],
    )
    selected = parser.read_config(
        str(config_path),
        str(selection_path),
    )
    assert selected["PROFILE_NAME"] == "Trojan Main"
    parser.write_runtime(str(runtime_path), selected)
    parser.write_xray_config(str(xray_path), selected)
    assert "PROFILE_NAME='Trojan Main'" in runtime_path.read_text()
    assert json.loads(xray_path.read_text())["outbounds"][0][
        "protocol"
    ] == "trojan"
    parser.bind_tun_interface(str(xray_path), "eth0")
    tun_settings = json.loads(xray_path.read_text())["inbounds"][0]["settings"]
    # Xray-core spells this field lowercase; see proxy/tun documentation.
    assert tun_settings["mtu"] == 1492
    assert "MTU" not in tun_settings
    assert tun_settings["autoOutboundsInterface"] == "eth0"
    parser.clear_selection(str(selection_path))
    assert parser.read_selection(str(selection_path)) == ""

# Xray-core v26.2.6 removed "allowInsecure" and rejects any config that still
# carries the key, whatever its value. It must never be emitted again, not even
# when the share link explicitly asks for it.
for link in (xhttp_link, persian_name_link):
    rendered = json.dumps(parser.build_xray_config(parser.parse_share_link(link)))
    assert "allowInsecure" not in rendered, link

insecure_link = (
    "vless://11111111-1111-4111-8111-111111111111@192.0.2.9:443"
    "?encryption=none&security=tls&sni=example.com&allowInsecure=1"
    "&insecure=1&type=ws&path=%2F#Insecure"
)
insecure_tls = parser.parse_share_link(insecure_link)["outbound"][
    "streamSettings"
]["tlsSettings"]
assert "allowInsecure" not in insecure_tls
assert insecure_tls["serverName"] == "example.com"

pinned_link = (
    "vless://11111111-1111-4111-8111-111111111111@192.0.2.9:443"
    "?encryption=none&security=tls&sni=example.com"
    "&pinnedPeerCertSha256=2d711642b726b04401627ca9fbac32f5c8530fb"
    "1903cc4db02258717921a4881&type=ws&path=%2F#Pinned"
)
pinned_tls = parser.parse_share_link(pinned_link)["outbound"][
    "streamSettings"
]["tlsSettings"]
# A comma-separated string, not an array - that is the documented type.
assert pinned_tls["pinnedPeerCertSha256"] == (
    "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
)

# A base64 digest pasted from a certificate viewer must be rejected clearly.
try:
    parser.parse_share_link(
        "vless://11111111-1111-4111-8111-111111111111@192.0.2.9:443"
        "?encryption=none&security=tls&pinnedPeerCertSha256=aGFzaA%3D%3D"
        "&type=ws&path=%2F#Bad"
    )
    raise AssertionError("a non-hex pinned digest was accepted")
except ValueError as error:
    assert "hex SHA-256" in str(error), error

# Card-sharing bypass: discovered peers must be routed direct, ahead of every
# other routing rule, so OSCam/CCcam never enters the tunnel.
bypass_rules = parser.build_routing_rules(
    {"PROTOCOL": "vless"}, "tproxy", "185.10.20.30, 91.0.0.9 not-an-ip"
)
assert bypass_rules[0]["outboundTag"] == "direct"
assert bypass_rules[0]["ip"] == ["185.10.20.30/32", "91.0.0.9/32"]
assert parser.build_routing_rules({"PROTOCOL": "vless"}, "tproxy", "") == (
    parser.build_routing_rules({"PROTOCOL": "vless"}, "tproxy")
)
assert parser.normalize_bypass_ips("1.2.3.4,1.2.3.4") == ["1.2.3.4"]

assert parser.is_public_ipv4("8.8.8.8")
for private in ("10.1.2.3", "192.168.0.1", "172.16.0.1", "127.0.0.1",
                "169.254.1.1", "100.64.0.1", "224.0.0.1", "nonsense"):
    assert not parser.is_public_ipv4(private), private

assert parser._hex_to_ipv4("0100007F") == "127.0.0.1"
assert parser._hex_to_ipv4("3506A8C0") == "192.168.6.53"

print("All proxy configuration tests passed.")

# A fresh install has profiles but no selection. ensure_selection must adopt the
# first profile so Start does not fail with "No Configuration Selected".
with TemporaryDirectory() as folder:
    config_path = Path(folder) / "config.txt"
    selection_path = Path(folder) / "selected"
    config_path.write_text(
        "\n".join(case[0] for case in cases) + "\n", encoding="utf-8"
    )
    fresh = parser.read_profiles(str(config_path))

    assert parser.select_profile(fresh, str(selection_path), fallback=False) is None
    adopted = parser.ensure_selection(fresh, str(selection_path))
    assert adopted["PROFILE_NAME"] == "Germany 1"
    assert parser.read_selection(str(selection_path)) == fresh[0]["PROFILE_ID"]

    # An existing valid selection is never overridden.
    parser.write_selection(str(selection_path), fresh[2]["PROFILE_ID"])
    assert parser.ensure_selection(fresh, str(selection_path))["PROFILE_NAME"] == (
        "Trojan Main"
    )

    # A stale selection (profile removed from config.txt) falls back to the first.
    parser.write_selection(str(selection_path), "f" * 64)
    assert parser.ensure_selection(fresh, str(selection_path))["PROFILE_NAME"] == (
        "Germany 1"
    )

    assert parser.ensure_selection([], str(selection_path)) is None

print("Selection tests passed.")

# Xray resolves the outbound host itself, and in TUN mode that lookup is routed
# into the tunnel the lookup is needed to build. Pinning the pre-resolved IP
# breaks the deadlock; the name must survive wherever the handshake needs it.
def pinned_outbound(link, ips):
    data = parser.build_xray_config(parser.parse_share_link(link), "tun", "eth0")
    host = parser.pin_server_address(data, ips)
    return host, data["outbounds"][0]


host, outbound = pinned_outbound(
    "vless://11111111-1111-4111-8111-111111111111@cdn2.example.cfd:443"
    "?security=tls&type=ws&path=%2F#WS",
    "203.0.113.7",
)
assert host == "cdn2.example.cfd"
assert outbound["settings"]["address"] == "203.0.113.7"
# Neither SNI nor Host was given in the link, so both must inherit the name.
assert outbound["streamSettings"]["tlsSettings"]["serverName"] == "cdn2.example.cfd"
assert outbound["streamSettings"]["wsSettings"]["host"] == "cdn2.example.cfd"

host, outbound = pinned_outbound(
    "vless://11111111-1111-4111-8111-111111111111@cdn2.example.cfd:443"
    "?security=tls&type=ws&host=front.example&sni=real.example&path=%2F#WS2",
    "203.0.113.7",
)
# An explicit domain-front must never be overwritten by the dialled name.
assert outbound["streamSettings"]["tlsSettings"]["serverName"] == "real.example"
assert outbound["streamSettings"]["wsSettings"]["host"] == "front.example"

host, outbound = pinned_outbound(
    "trojan://pw@cdn3.example.cfd:443?security=reality&pbk=KEY"
    "&type=grpc&serviceName=svc#GRPC",
    "203.0.113.8",
)
assert outbound["settings"]["address"] == "203.0.113.8"
assert outbound["streamSettings"]["grpcSettings"]["authority"] == "cdn3.example.cfd"
assert outbound["streamSettings"]["realitySettings"]["serverName"] == "cdn3.example.cfd"

# An address that is already an IP, or a missing resolution, changes nothing.
literal = (
    "vless://11111111-1111-4111-8111-111111111111@87.107.195.57:443"
    "?security=tls&type=ws&path=%2F#IP"
)
assert pinned_outbound(literal, "87.107.195.57")[0] == ""
named = (
    "vless://11111111-1111-4111-8111-111111111111@cdn2.example.cfd:443"
    "?security=tls&type=ws&path=%2F#NoIP"
)
host, outbound = pinned_outbound(named, "")
assert host == ""
assert outbound["settings"]["address"] == "cdn2.example.cfd"
assert parser.is_ip_literal("1.2.3.4") and not parser.is_ip_literal("a.example")

print("Server pinning tests passed.")

# IPv6 must be captured, not ignored: the TUN interface needs a v6 gateway and
# the local v6 scopes need the same direct treatment as their v4 equivalents.
v6cfg = parser.build_xray_config(parser.parse_share_link(cases[0][0]), "tun", "eth0")
gateways = v6cfg["inbounds"][0]["settings"]["gateway"]
assert parser.TUN_GATEWAY4 in gateways and parser.TUN_GATEWAY6 in gateways
private_rule = [
    rule for rule in v6cfg["routing"]["rules"]
    if rule.get("outboundTag") == "direct" and "127.0.0.0/8" in rule.get("ip", [])
][0]
for scope in ("::1/128", "fe80::/10", "ff00::/8", "fdfe:e2e2::/64"):
    assert scope in private_rule["ip"], scope

# A poisoned answer must be blackholed, never sent out direct, and the rule has
# to precede the private-network rule because the sinkhole lives inside 10/8.
rules = v6cfg["routing"]["rules"]
block_index = [i for i, r in enumerate(rules) if r.get("outboundTag") == "block"][0]
private_index = rules.index(private_rule)
assert block_index < private_index
assert rules[block_index]["ip"] == ["10.10.34.0/24"]

# Resolving every sniffed domain locally would leak the browsing history around
# the tunnel, so routing must not do IP matching on domains.
assert v6cfg["routing"]["domainStrategy"] == "AsIs"

# A port bypass is unqualified by address, so ports carrying ordinary traffic
# must never be bypassed by port alone.
assert parser.is_safe_bypass_port(13000)
assert parser.is_safe_bypass_port(12000)
for unsafe in (443, 80, 8080, 8443, 853, 22, 53, 0, 70000, "x"):
    assert not parser.is_safe_bypass_port(unsafe), unsafe

print("IPv6, sinkhole and port-safety tests passed.")

# In a VMess share link "type" is the header obfuscation, not the transport -
# v2rayN and v2rayNG always emit "type":"none", which used to reject every link.
for net, expected in (("tcp", "raw"), ("ws", "websocket"), ("grpc", "grpc"),
                      ("xhttp", "xhttp")):
    payload = dict(vmess, net=net, type="none")
    link = "vmess://" + base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")
    got = parser.parse_share_link(link)["outbound"]["streamSettings"]["network"]
    assert got == expected, (net, got)

# One unusable line must not discard the whole file, but a file with nothing
# usable must still be an error.
with TemporaryDirectory() as folder:
    mixed = Path(folder) / "mixed.txt"
    mixed.write_text(
        cases[0][0] + "\nhysteria2://x@1.2.3.4:443#Nope\n" + vmess_link + "\n",
        encoding="utf-8",
    )
    kept = [p["PROFILE_NAME"] for p in parser.read_profiles(str(mixed))]
    assert kept == ["Germany 1", "VMess Main"], kept

    unusable = Path(folder) / "bad.txt"
    unusable.write_text("hysteria2://x@1.2.3.4:443#Nope\n", encoding="utf-8")
    try:
        parser.read_profiles(str(unusable))
        raise AssertionError("a file with no usable profile was accepted")
    except ValueError as error:
        assert "unsupported protocol" in str(error), error

    # A legacy config must not name itself after its own file contents, which
    # put the UUID on screen and into the runtime file.
    legacy = Path(folder) / "legacy.txt"
    legacy.write_text(
        "# my home config\nSERVER_ADDRESS=1.2.3.4\nSERVER_PORT=443\n"
        "UUID=11111111-1111-4111-8111-111111111111\n",
        encoding="utf-8",
    )
    name = parser.read_profiles(str(legacy))[0]["PROFILE_NAME"]
    assert name == "VLESS 1.2.3.4", name
    assert "UUID" not in name and "1111" not in name

    # A corrupted selection file must not raise into an Enigma2 callback.
    corrupt = Path(folder) / "selected"
    corrupt.write_bytes(b"\xff\xfe not ascii")
    assert parser.read_selection(str(corrupt)) == ""

# Only genuinely v4-mapped /proc/net/tcp6 rows may be reduced to their last word.
assert parser._hex_to_ipv4("0100007F") == "127.0.0.1"
assert parser._hex_to_ipv4("EFBEADDE") == "222.173.190.239"

print("VMess, resilience and legacy-name tests passed.")

# A server published only over IPv6 must be usable: the address is already an
# address, so it is never "resolved" or replaced, and a v6-only hostname pins to
# its AAAA record while the name is kept for SNI.
for literal in ("1.2.3.4", "2001:db8::1", "::1"):
    assert parser.is_ip_literal(literal), literal
for not_literal in ("a.example", "2001:db8::1x", ""):
    assert not parser.is_ip_literal(not_literal), not_literal

v6_link = (
    "vless://11111111-1111-4111-8111-111111111111@[2001:db8::1]:443"
    "?security=tls&type=ws&sni=a.example#V6"
)
v6_parsed = parser.parse_share_link(v6_link)
assert v6_parsed["outbound"]["settings"]["address"] == "2001:db8::1"
v6_config = parser.build_xray_config(v6_parsed, "tun", "eth0")
# Already an address: nothing to pin, and it must be left exactly as it is.
assert parser.pin_server_address(v6_config, "2001:db8::1") == ""
assert v6_config["outbounds"][0]["settings"]["address"] == "2001:db8::1"

v6_host = parser.build_xray_config(
    parser.parse_share_link(
        "vless://11111111-1111-4111-8111-111111111111@v6only.example:443"
        "?security=tls&type=ws#V6H"
    ),
    "tun",
    "eth0",
)
assert parser.pin_server_address(v6_host, "2001:db8::9") == "v6only.example"
assert v6_host["outbounds"][0]["settings"]["address"] == "2001:db8::9"
assert v6_host["outbounds"][0]["streamSettings"]["tlsSettings"][
    "serverName"
] == "v6only.example"

# When both families are known, IPv4 is dialled.
assert parser.normalize_server_ips("2001:db8::9, 5.6.7.8") == [
    "5.6.7.8",
    "2001:db8::9",
]
# The card-sharing bypass list stays IPv4-only, so a v6 peer cannot leak into
# an iptables rule that would not understand it.
assert parser.normalize_bypass_ips("2001:db8::9, 5.6.7.8") == ["5.6.7.8"]

print("IPv6 server-address tests passed.")

# Shadowsocks servers often refuse to relay UDP. The old answer was to send
# UDP/53 out direct, which handed every lookup to the ISP resolver in the clear
# and got a poisoned answer back. Lookups must now ride the TCP connection.
for backend in ("tun", "tproxy", "redirect"):
    ss = parser.build_xray_config(
        parser.parse_share_link(cases[3][0]), backend, "eth0"
    )
    assert ss["dns"]["servers"] == ["tcp://8.8.8.8", "tcp://1.1.1.1"], backend
    assert ss["dns"]["tag"] == parser.DNS_INTERNAL_TAG
    tags = [item["tag"] for item in ss["outbounds"]]
    assert "dns-out" in tags, backend
    assert "dns-in" in [item["tag"] for item in ss["inbounds"]], backend
    rules = ss["routing"]["rules"]
    # Nothing may send DNS out direct any more.
    assert not [
        r for r in rules
        if r.get("port") == "53" and r.get("outboundTag") == "direct"
    ], backend
    # Client query -> core resolver -> proxy.
    assert {"type": "field", "inboundTag": ["dns-in"],
            "outboundTag": "dns-out"} in rules, backend
    assert {"type": "field", "inboundTag": [parser.DNS_INTERNAL_TAG],
            "outboundTag": "proxy"} in rules, backend

# The rewrite* keys belong to the dns outbound, not to dokodemo-door; setting
# them on the inbound did nothing, which is why this never worked before.
dns_inbound = [
    item for item in
    parser.build_xray_config(parser.parse_share_link(cases[3][0]), "tun", "eth0")["inbounds"]
    if item["tag"] == "dns-in"
][0]
# Both spellings are emitted so one config loads on either core generation.
for current, legacy in (("rewriteAddress", "address"), ("rewritePort", "port")):
    assert current in dns_inbound["settings"], current
    assert legacy in dns_inbound["settings"], legacy
# rewriteNetwork belongs to the dns outbound, never to the inbound.
assert "rewriteNetwork" not in dns_inbound["settings"]

# Everything that is not Shadowsocks keeps the plain resolver path.
for backend in ("tun", "tproxy"):
    other = parser.build_xray_config(
        parser.parse_share_link(cases[0][0]), backend, "eth0"
    )
    assert other["dns"]["servers"] == ["8.8.8.8", "1.1.1.1"], backend
    assert "dns-out" not in [item["tag"] for item in other["outbounds"]], backend

print("Shadowsocks DNS-over-TCP tests passed.")
