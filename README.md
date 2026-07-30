# e2xray

e2xray is an Enigma2 Xray client for Dreambox One UHD, OpenDreambox 2.6.0
and ARM64. The package embeds the official Xray-core `v26.5.9` Linux ARM64
binary, so the user does not need to download or install Xray separately.

## Features

- Full-device traffic routing through an Xray TUN interface
- Start, Stop, Ping and Settings controls
- Three-language success and failure messages for Start and Stop
- English, Persian and Arabic user interfaces
- VLESS, VMess, Trojan and Shadowsocks share links
- Multiple named configurations selected directly on the main screen
- RAW/TCP, WebSocket, gRPC and XHTTP transports where the protocol permits
- XHTTP `mode`, `extra` and padding settings from share links
- TLS and REALITY transport security
- Embedded DNS defaults: `8.8.8.8` and `1.1.1.1`
- Direct routes for the proxy server to prevent a routing loop
- DNS and policy-routing restoration when the plugin stops
- Embedded ARM64 Xray core with no online installation dependency

The plugin is off after installation and after boot. It starts only when the
user presses Start.

## Configuration

Paste one supported share link per line into:

```text
/root/config.txt
```

Supported link prefixes:

```text
vless://
vmess://
trojan://
ss://
```

The name after `#` is URL-decoded and displayed below Internet Status on the
main screen. VMess also uses its `ps` field when no fragment name exists.
Move through the vertical list with Up/Down and press OK to select a profile.
A green `X` marks the selected stopped profile; a green check mark identifies
the profile currently running. Start and Ping always use the selected profile.

The selected profile ID is stored in:

```text
/etc/e2xray/selected
```

The generated Xray runtime configuration is:

```text
/etc/e2xray/config.json
```

## Internet Status

- ArvanCloud unavailable: red lamp, Offline
- ArvanCloud and Cloudflare available: green lamp, Online
- ArvanCloud available but Cloudflare unavailable: yellow lamp, National internet

Ping checks the server address in the saved proxy link. If no valid link is
saved, the plugin displays `No Config. Found`.

## Build

On Debian or Ubuntu:

```sh
chmod +x build.sh
./build.sh
```

The output is:

```text
enigma2-plugin-extensions-e2xray_0.5.3_arm64.deb
```

The build uses gzip for `control.tar.gz` and `data.tar.gz`. This is required
because the older `dpkg` in OpenDreambox 2.6.0 cannot read zstd-compressed
Debian archive members.

GitHub Actions can build the same package from **Actions > Build Debian
package > Run workflow**. The artifact contains the DEB and its SHA256 file.

## Install

Upload the DEB to `/tmp` and run:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.5.3_arm64.deb
```

The post-install script prints:

```text
Now we are restarting your Enigma2
```

It then restarts the Enigma2 user interface automatically. A full Dreambox
reboot is not required.

## Uninstall

To remove the package but preserve `/root/config.txt` for a later reinstall:

```sh
dpkg --remove enigma2-plugin-extensions-e2xray
```

To remove the plugin and all of its configuration:

```sh
dpkg --purge enigma2-plugin-extensions-e2xray
```

The removal script stops e2xray first, removes stale Python bytecode, the
embedded core, init links, runtime files and generated configuration, then
restarts the Enigma2 user interface. `purge` also deletes `/root/config.txt`.

## TUN Safety

Before start, e2xray saves the current DNS, default route and reverse-path
filter values. It resolves the proxy server before replacing the default route
in its private policy-routing table, then keeps every resolved server IPv4
address on the original gateway. The generated Xray config also enables
`autoOutboundsInterface`.

Stop removes the policy rule, flushes the private table, restores DNS and
reverse-path filter values, and brings the TUN interface down. Stale state left
by a previous crash is recovered before the next start.

## Project

https://github.com/dreamboxone/e2xray
