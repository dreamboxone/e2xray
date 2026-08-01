# e2xray

e2xray is an Xray client for Enigma2 receivers. It routes the receiver's
traffic through an Xray TUN interface and provides Start, Stop, Ping, status,
configuration selection and settings from the Enigma2 user interface.

The architecture-specific DEBs contain the official Xray-core `v26.5.9`
binary. Users do not need to install Xray-core or download additional packages
from the Internet.

## Compatibility

| Receiver family | DreamOS | Kernel reports | DEB architecture |
| --- | --- | --- | --- |
| Dreambox One / Two | OpenDreambox 2.6 | `aarch64` | `arm64` |
| DM520 / DM525 | OpenDreambox 2.5 | `mips` | `mipsel` |

The `mipsel` package contains the official little-endian
`Xray-linux-mips32le` core. In particular, a DM525 can report `mips` from
`uname -m` while `dpkg --print-architecture` correctly reports `mipsel`.

Do not install either package on ARM32, x86 or an Enigma2 image that does not
use `dpkg`.

OpenATV 8 images for Dreambox One use `opkg` and IPK packages. On those images,
`opkg print-architecture` includes `arm64`, so build and install the OpenATV
package as `enigma2-plugin-extensions-e2xray_0.6.0_arm64.ipk`.

The ARM64 build has been tested on Dreambox One. The MIPS little-endian build
targets DM525/OpenDreambox 2.5 and is statically validated in GitHub Actions;
an on-receiver test is still required for final runtime confirmation.

## Features

- Full-device traffic routing through an Xray TUN interface
- Start, Stop, Ping and Settings controls
- English, Persian and Arabic user interfaces
- VLESS, VMess, Trojan and Shadowsocks share links
- Multiple named configurations on the main screen
- UTF-8 profile names, including Persian and Arabic names
- RAW/TCP, WebSocket, gRPC and XHTTP transports where supported
- XHTTP `mode`, `extra` and padding settings from share links
- TLS and REALITY transport security
- Ping latency displayed beside the selected configuration
- Embedded DNS defaults: `8.8.8.8` and `1.1.1.1`
- Direct routes for the proxy server to prevent routing loops
- DNS and policy-routing restoration when e2xray stops
- Embedded architecture-matched Xray-core with no online installation dependency

e2xray is **stopped by default** after installation and after boot. It starts
only when the user selects a configuration and presses **Start**.

## Requirements

Before installation, confirm that:

- The receiver runs Enigma2 and installs packages with `dpkg`.
- `dpkg --print-architecture` reports `arm64` or `mipsel`.
- `/dev/net/tun` exists.
- You have a valid VLESS, VMess, Trojan or Shadowsocks share link.

Run these commands over SSH:

```sh
uname -m
dpkg --print-architecture
ls -l /dev/net/tun
```

Typical output is one of:

```text
aarch64
arm64
```

or on a DM525:

```text
mips
mipsel
```

No separate Xray-core installation is required.

## Download

Download the DEB matching `dpkg --print-architecture` from the
[e2xray Releases page](https://github.com/dreamboxone/e2xray/releases).

Version `0.6.0` produces two packages:

```text
enigma2-plugin-extensions-e2xray_0.6.0_arm64.deb
enigma2-plugin-extensions-e2xray_0.6.0_mipsel.deb
```

## Installation

### 1. Upload the package

Upload the DEB to the receiver's `/tmp` directory with SCP, FTP or an Enigma2
file manager.

Example from Windows PowerShell:

```powershell
scp .\enigma2-plugin-extensions-e2xray_0.6.0_arm64.deb root@RECEIVER_IP:/tmp/
```

For a MIPS receiver, use the `_mipsel.deb` filename instead. Replace
`RECEIVER_IP` with the receiver's IP address.

### 2. Install over SSH

On Dreambox One/Two:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.0_arm64.deb
```

On DM520/DM525:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.0_mipsel.deb
```

The installer verifies that its embedded Xray binary can run on the receiver
before restarting Enigma2.

At the end of installation, the terminal displays:

```text
Now we are restarting your Enigma2
```

The Enigma2 user interface restarts automatically. A full receiver reboot is
not required. The Xray core is already included in the DEB.

### 3. Add proxy configurations

Create or upload this file:

```text
/root/config.txt
```

Put one supported share link on each line:

```text
vless://...
vmess://...
trojan://...
ss://...
```

Example:

```text
vless://UUID@SERVER:443?encryption=none&security=tls&type=ws&path=%2F#My%20Server
```

Do not add quotation marks around links. Empty lines and lines beginning with
`#` are ignored.

The name after `#` is URL-decoded and shown in the plugin. VMess uses its `ps`
field when the link has no fragment name.

### 4. Start e2xray

1. Open **Plugin Browser > e2xray**.
2. Move through configurations with the Up and Down keys.
3. Press **OK** on a configuration. A green `X` marks it as selected.
4. Press the green **Start** button.
5. The marker changes to a green `V` while that configuration is running.

Press **OK** again before starting to clear the selection. A running
configuration must be stopped before selecting another one.

### 5. Test the configuration

Select a configuration and press the yellow **Ping** button. The measured
latency is displayed in milliseconds beside its name.

The Internet Status lamp uses Cloudflare:

- Green: Online
- Red: Offline

To verify the public IP over SSH while e2xray is running:

```sh
curl -4 --connect-timeout 5 --max-time 15 https://api.ipify.org ; echo
```

## Persian Quick Install

فایل DEB را در مسیر `/tmp` ریسیور کپی کنید و دستور زیر را اجرا کنید:

```sh
dpkg --print-architecture
```

برای Dreambox One/Two:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.0_arm64.deb
```

برای DM520/DM525:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.0_mipsel.deb
```

پس از نصب، رابط Enigma2 خودکار راه‌اندازی مجدد می‌شود. کانفیگ‌ها را به‌صورت
یک لینک در هر خط داخل فایل `/root/config.txt` قرار دهید. سپس وارد
`Plugin Browser > e2xray` شوید، کانفیگ را با دکمه OK انتخاب کنید و دکمه سبز
Start را بزنید. هسته Xray داخل بسته قرار دارد و نصب جداگانه لازم نیست.

## Files

| Path | Purpose |
| --- | --- |
| `/root/config.txt` | User share links |
| `/etc/e2xray/config.json` | Generated Xray runtime configuration |
| `/etc/e2xray/selected` | Selected profile ID |
| `/tmp/e2xray.log` | Service and Xray log |
| `/var/run/e2xray/` | Runtime state and backups |
| `/usr/lib/e2xray/bin/xray` | Embedded core matching the DEB architecture |

## Troubleshooting

### `No Config. Found`

Confirm that `/root/config.txt` exists and contains at least one supported
share link:

```sh
sed -n '1,20p' /root/config.txt
```

### e2xray does not start

Check the service status and recent log messages:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh status
tail -n 100 /tmp/e2xray.log
```

Confirm that TUN is available:

```sh
ls -l /dev/net/tun
```

### Check TUN routing

While e2xray is running:

```sh
ip rule show
ip route show table 101
ip route get 1.1.1.1
```

The route to public addresses should use `e2xray0`. The proxy server itself
must continue to use the receiver's physical network interface.

### Stop and restore networking

Use the red **Stop** button in the plugin or run:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh stop
```

Stopping e2xray removes its policy rule and TUN interface and restores the
saved DNS and network settings.

## Updating

The existing `/root/config.txt` is preserved during a normal upgrade.

Upload the newer DEB to `/tmp`, then run:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_NEW_VERSION_ARCH.deb
```

The installer stops the old service, installs the new files and restarts the
Enigma2 user interface automatically. Keep using the same architecture shown
by `dpkg --print-architecture`.

## Uninstalling

Remove the plugin but preserve `/root/config.txt`:

```sh
dpkg --remove enigma2-plugin-extensions-e2xray
```

Remove the plugin and all of its configuration, including
`/root/config.txt`:

```sh
dpkg --purge enigma2-plugin-extensions-e2xray
```

The removal script stops e2xray, restores networking, removes the embedded
core, init links, runtime files and generated configuration, and then restarts
the Enigma2 user interface.

## Building the DEB

On Debian or Ubuntu, build ARM64:

```sh
chmod +x build.sh
./build.sh arm64
```

Build MIPS little-endian:

```sh
./build.sh mipsel
```

Build OpenATV 8 IPK for Dreambox One:

```sh
./build.sh ipk arm64
```

The outputs are:

```text
enigma2-plugin-extensions-e2xray_0.6.0_arm64.deb
enigma2-plugin-extensions-e2xray_0.6.0_mipsel.deb
enigma2-plugin-extensions-e2xray_0.6.0_arm64.ipk
```

The build uses gzip for `control.tar.gz` and `data.tar.gz`. This is required
because the older `dpkg` in OpenDreambox 2.6.0 cannot read zstd-compressed
Debian archive members.

GitHub Actions builds both packages from a single run:

```text
Actions > Build Debian packages > Run workflow
```

The run produces separate `arm64` and `mipsel` artifacts. Each artifact
contains its DEB and SHA256 file.

## TUN Safety

Before starting, e2xray saves the current DNS, default route and reverse-path
filter values. It resolves the proxy server before enabling its private
policy-routing table and keeps every resolved proxy-server IPv4 address on the
original gateway. The generated Xray configuration binds outbound traffic to
the original physical network interface.

Stopping e2xray removes the policy rule, flushes table `101`, restores DNS and
reverse-path filter values, and brings the TUN interface down. Stale state
left by a previous crash is recovered before the next start.

## Credits

Special thanks to the
[XTLS/Xray-core team and contributors](https://github.com/XTLS/Xray-core) for
developing and maintaining Xray-core. Their work provides the networking core
embedded in this plugin.

از تیم و توسعه‌دهندگان XTLS/Xray-core برای توسعه و نگهداری هسته Xray
صمیمانه سپاسگزاریم.

e2xray is an independent Enigma2 plugin and is not an official XTLS project.

## License

The e2xray plugin source is released under the
[MIT License](https://github.com/dreamboxone/e2xray/blob/main/LICENSE).

The embedded Xray-core binary is distributed under the Mozilla Public License
2.0. A copy is installed at:

```text
/usr/share/doc/enigma2-plugin-extensions-e2xray/Xray-LICENSE
```

## Project

https://github.com/dreamboxone/e2xray
