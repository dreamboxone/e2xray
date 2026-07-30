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
    assert json.loads(xray_path.read_text())["inbounds"][0]["settings"][
        "autoOutboundsInterface"
    ] == "eth0"
    parser.clear_selection(str(selection_path))
    assert parser.read_selection(str(selection_path)) == ""

print("All proxy configuration tests passed.")
