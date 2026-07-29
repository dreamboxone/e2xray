# e2xray

e2xray is an Enigma2 plugin for Dreambox One UHD / OpenDreambox 2.6.0 / ARM64.
It embeds the official Xray-core `v26.5.9` Linux ARM64 v8a binary.

It runs an embedded Xray-core binary from:

```sh
/usr/lib/e2xray/bin/xray
```

The package also includes:

```sh
/usr/share/e2xray/geoip.dat
/usr/share/e2xray/geosite.dat
```

The user does not need to install Xray separately.

## Build

The repository is already laid out as a Debian package root. On a Debian-based
build machine:

```sh
chmod +x build.sh
./build.sh
```

## Main Screen

The main plugin screen contains:

- Start
- Stop
- Ping
- Internet status / وضعیت اینترنت / حالة الإنترنت
- About
- Settings
- Restart, service status and logs in the Menu screen

Internet status logic:

- Cannot reach `https://www.arvancloud.ir`: red lamp, `آفلاین`
- Can reach ArvanCloud and `https://dash.cloudflare.com`: green lamp, `آنلاین`
- Can reach ArvanCloud but cannot reach Cloudflare dashboard: yellow lamp, `اینترنت ملی`

## Install

Copy the package to `/tmp` on Dreambox:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.2.0_arm64.deb
```

Restart Enigma2 after installation.

If the plugin list is not refreshed automatically:

```sh
systemctl restart enigma2
```

## Configuration

Use the settings screen or edit:

```sh
/etc/e2xray/server.conf
```

The generated runtime config is:

```sh
/etc/e2xray/config.json
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
