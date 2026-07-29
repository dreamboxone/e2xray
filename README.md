# e2xray

e2xray is an Enigma2 plugin for Dreambox One UHD / OpenDreambox 2.6.0 / ARM64.
It embeds the official Xray-core `v26.5.9` Linux ARM64 v8a binary.

It runs an embedded Xray-core binary from:

```sh
/usr/lib/e2xray/bin/xray
```

The user does not need to install Xray separately.

## Download

Download the ARM64 Debian package from:

```text
https://github.com/dreamboxone/e2xray/releases/download/v0.3.2/enigma2-plugin-extensions-e2xray_0.3.2_arm64.deb
```

The SHA256 checksum is published beside the package in the GitHub release notes.

## Build

The repository is already laid out as a Debian package root. On a Debian-based
build machine:

```sh
chmod +x build.sh
./build.sh
```

## Main Screen

The main plugin screen contains:

- Stop
- Start
- Ping
- Settings
- Internet status / وضعیت اینترنت / حالة الإنترنت

The default interface language is English. Settings contains:

- Language: English, Persian or Arabic
- Config. Entry: VLESS link import plus manual server fields
- About: project version and Telegram, YouTube and GitHub addresses

Internet status logic:

- Cannot reach `https://www.arvancloud.ir`: red lamp, `آفلاین`
- Can reach ArvanCloud and `https://dash.cloudflare.com`: green lamp, `آنلاین`
- Can reach ArvanCloud but cannot reach Cloudflare dashboard: yellow lamp, `اینترنت ملی`

Ping checks the server from the saved VLESS configuration. It reports
`No Config. Found` when no valid configuration has been saved.

## Install

Copy the package to `/tmp` on Dreambox:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.3.2_arm64.deb
```

Reboot the Dreambox after installation so Enigma2 reloads the plugin and icon:

```sh
reboot
```

## Configuration

Open Settings and select Config. Entry. You can import a `vless://` share link
or enter the server, port, UUID, SNI, public key, short ID, fingerprint,
security, network, path, host and flow manually. Save with the green button.
Reality, TLS, TCP, WebSocket and gRPC VLESS links are supported.

e2xray is always off after installation and after boot. It starts only when
the user presses Start.

The parsed settings are saved in:

```sh
/etc/e2xray/server.conf
```

The generated runtime config is:

```sh
/etc/e2xray/config.json
```

DNS is managed internally and is not requested from the user:

```text
Primary:   8.8.8.8
Secondary: 1.1.1.1
```

## TUN Safety

The control script saves current DNS and routing state before start. It uses a separate policy-routing table, preserves directly connected LAN routes, and adds direct routes for every resolved Xray server IPv4 address. Xray's official `autoOutboundsInterface` protection is enabled as an additional loop guard.

On stop it restores DNS, removes the policy rule and flushes the private routing table. A stale state left by a power loss or crash is recovered before the next start.
The original reverse-path-filter values are also saved and restored.

## GitHub

Project repository:

```text
https://github.com/dreamboxone/e2xray
```
