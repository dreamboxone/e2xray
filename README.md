# e2xray

e2xray is an Xray client for Enigma2 receivers. It routes the receiver's
traffic through an Xray TUN interface and provides Start, Stop, Ping, status,
configuration selection and settings from the Enigma2 user interface.

The architecture-specific DEB/IPK packages contain the official Xray-core `v26.5.9`
binary. Users do not need to install Xray-core or download additional packages
from the Internet.

## Compatibility

| Receiver family | Image/package manager | Kernel reports | Package architecture |
| --- | --- | --- | --- |
| Dreambox One / Two | OpenDreambox (`dpkg`) | `aarch64` | `arm64` DEB |
| DM520 / DM525 | OpenDreambox (`dpkg`) | `mips` | `mipsel` DEB |
| GigaBlue UHD ARM receivers | OpenPLi/OpenBH/OpenATV (`opkg`) | `armv7l` | architecture printed by `opkg print-architecture` |

The `mipsel` package contains the official little-endian
`Xray-linux-mips32le` core. In particular, a DM525 can report `mips` from
`uname -m` while `dpkg --print-architecture` correctly reports `mipsel`.

Do not install the ARM64 or MIPS DEBs on an ARM32 receiver. GigaBlue ARMv7
receivers must use the IPK whose architecture name appears in
`opkg print-architecture` (normally `armv7ahf-vfp-neon`, `armv7ahf-neon` or
`cortexa15hf-neon-vfpv4`). Users who are unsure may use the ARMv7 `_all.ipk`;
its installer checks the CPU before installing the bundled core.

OpenATV 8 images for Dreambox One also use `opkg` and IPK packages. On those images,
`opkg print-architecture` includes `arm64`, so build and install the OpenATV
package as `enigma2-plugin-extensions-e2xray_0.6.7_arm64.ipk`.

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
- Automatic fallback for receivers whose BusyBox does not support `ip rule`
- DNS and routing restoration when e2xray stops
- Embedded architecture-matched Xray-core with no online installation dependency

e2xray is **stopped by default** after installation and after boot. It starts
only when the user selects a configuration and presses **Start**.

## Requirements

Before installation, confirm that:

- The receiver runs Enigma2 and installs packages with `dpkg` or `opkg`.
- `dpkg --print-architecture` or `opkg print-architecture` reports an architecture
  matching one of the supplied packages.
- The image kernel provides TUN support. Version 0.6.7 automatically loads the
  `tun` module and creates `/dev/net/tun` when the driver is available.
- You have a valid VLESS, VMess, Trojan or Shadowsocks share link.

Run these commands over SSH:

```sh
uname -m
(command -v dpkg >/dev/null && dpkg --print-architecture) || opkg print-architecture
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

Download the DEB/IPK matching the receiver's package architecture from the
[e2xray Releases page](https://github.com/dreamboxone/e2xray/releases).

Version `0.6.7` produces these packages:

```text
enigma2-plugin-extensions-e2xray_0.6.7_arm64.deb
enigma2-plugin-extensions-e2xray_0.6.7_mipsel.deb
enigma2-plugin-extensions-e2xray_0.6.7_arm64.ipk
enigma2-plugin-extensions-e2xray_0.6.7_armv7ahf-vfp-neon.ipk
enigma2-plugin-extensions-e2xray_0.6.7_armv7ahf-neon.ipk
enigma2-plugin-extensions-e2xray_0.6.7_cortexa15hf-neon-vfpv4.ipk
enigma2-plugin-extensions-e2xray_0.6.7_all.ipk
enigma2-plugin-extensions-e2xray_0.6.7_mips-all.ipk
enigma2-plugin-extensions-e2xray_0.6.7_all.deb
```

The single `_all.deb` contains ARM64, ARMv7, mips32le and mips64le cores. Its
pre-install script rejects unsupported CPUs, verifies ARMv7 floating-point and
MIPS byte-order requirements, and its post-install script selects and executes
the matching core before Enigma2 is restarted.

### Which package should I install?

| Receiver/image | Recommended package |
| --- | --- |
| GigaBlue ARMv7 with OpenPLi/OpenBH/OpenATV | `_all.ipk`, or the IPK exactly matching `opkg print-architecture` |
| Dreambox One/Two with `dpkg` | `_arm64.deb` |
| Dreambox One with `opkg` | `_arm64.ipk` |
| DM520/DM525 with `dpkg` | `_mipsel.deb` |
| Little-endian MIPS receiver with `opkg` | `_mips-all.ipk` |

Do not use `_all.deb` on an `opkg` image and do not rename a DEB to IPK.

## What's new in 0.6.7

Version 0.6.7 fixes the startup error seen on some GigaBlue/OpenPLi receivers:

```text
TUN routing failed; the original network settings were restored.
```

Some Enigma2 images provide a reduced BusyBox `ip` command without `ip rule`,
and some receiver kernels cannot use a separate policy-routing table. e2xray
now detects this condition and automatically switches to safe split-default
routes. No manual setting is required.

This release also:

- records the exact failed network command in `/tmp/e2xray.log`;
- recommends full `iproute2` and the matching `kernel-module-tun` on IPK images;
- checks that Xray remains alive while routes are installed;
- safely restores DNS, reverse-path filtering and plugin-owned routes;
- preserves pre-existing routes, table `101` and priority `1001` rules.

## Installation

### 1. Upload the package

Upload the DEB/IPK to the receiver's `/tmp` directory with SCP, FTP or an Enigma2
file manager.

Example from Windows PowerShell:

```powershell
scp .\enigma2-plugin-extensions-e2xray_0.6.7_arm64.deb root@RECEIVER_IP:/tmp/
```

For a MIPS receiver, use the `_mipsel.deb` filename instead. Replace
`RECEIVER_IP` with the receiver's IP address.

### 2. Install over SSH

On Dreambox One/Two:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.7_arm64.deb
```

On DM520/DM525:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.7_mipsel.deb
```

On GigaBlue ARMv7 with OpenPLi, OpenBH or OpenATV, first choose the filename
whose suffix is listed by
`opkg print-architecture`, then install it with:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_0.6.7_ARCH.ipk
```

Alternatively, use the single `_all.ipk` ARMv7 package. Its pre-install script
rejects non-ARMv7 CPUs and ARMv7 CPUs without VFPv3/VFPv4 before files are
installed; the post-install script then verifies that the embedded core runs.

Recommended simple installation for an ARMv7 GigaBlue receiver:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_0.6.7_all.ipk
```

For opkg-based little-endian MIPS receivers, use the single `_mips-all.ipk`
package. It includes the official mips32le and mips64le cores, rejects non-MIPS
and detectable big-endian systems, then selects the matching core from
`uname -m` and verifies that it runs before restarting Enigma2.

The installer verifies that its embedded Xray binary can run on the receiver
before restarting Enigma2.

At the end of installation, the terminal displays:

```text
Now we are restarting your Enigma2
```

The Enigma2 user interface restarts automatically. A full receiver reboot is
not required. The Xray core is already included in the package.

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

## راهنمای فارسی نصب و به‌روزرسانی

### انتخاب بسته مناسب

برای مشاهده معماری و نوع package manager این دستورها را در Telnet یا SSH اجرا کنید:

```sh
uname -m
(command -v opkg >/dev/null && opkg print-architecture) || dpkg --print-architecture
```

- برای ریسیورهای ARMv7 گیگابلو با OpenPLi، OpenBH یا OpenATV، بسته
  `enigma2-plugin-extensions-e2xray_0.6.7_all.ipk` پیشنهاد می‌شود.
- برای Dreambox One/Two دارای `dpkg` از بسته `_arm64.deb` استفاده کنید.
- برای Dreambox One دارای `opkg` از بسته `_arm64.ipk` استفاده کنید.
- برای DM520/DM525 دارای `dpkg` از بسته `_mipsel.deb` استفاده کنید.
- برای ریسیور MIPS دارای `opkg` از بسته `_mips-all.ipk` استفاده کنید.

### نصب روی گیگابلو ARMv7

فایل IPK را در مسیر `/tmp` کپی و اجرا کنید:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_0.6.7_all.ipk
```

اگر نام معماری دقیق ریسیور را می‌دانید، می‌توانید به‌جای بسته عمومی از IPK
هم‌نام با خروجی `opkg print-architecture` استفاده کنید.

### نصب روی Dreambox

برای Dreambox One/Two:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.7_arm64.deb
```

برای DM520/DM525:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_0.6.7_mipsel.deb
```

### ارتقا از نسخه قبلی

نیازی به حذف نسخه قبلی نیست. بسته ۰.۶.۷ را مستقیماً نصب کنید. فایل
`/root/config.txt` و کانفیگ‌های کاربر حفظ می‌شوند. پس از نصب، Enigma2 خودکار
راه‌اندازی مجدد می‌شود.

در نسخه ۰.۶.۷ خطای `TUN routing failed` در ایمیج‌هایی که دستور `ip rule`
ندارند به‌صورت خودکار با روش جایگزین routing حل می‌شود. در صورت ادامه خطا،
این دستورها را اجرا و فایل لاگ را ارسال کنید:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh status
tail -n 150 /tmp/e2xray.log
uname -a
opkg print-architecture 2>/dev/null || dpkg --print-architecture
```

کانفیگ‌ها را به‌صورت یک لینک در هر خط داخل `/root/config.txt` قرار دهید. سپس
وارد `Plugin Browser > e2xray` شوید، کانفیگ را با دکمه OK انتخاب کنید و دکمه
سبز Start را بزنید. هسته Xray داخل بسته است و نصب جداگانه لازم نیست.

## Files

| Path | Purpose |
| --- | --- |
| `/root/config.txt` | User share links |
| `/etc/e2xray/config.json` | Generated Xray runtime configuration |
| `/etc/e2xray/selected` | Selected profile ID |
| `/tmp/e2xray.log` | Service and Xray log |
| `/var/run/e2xray/` | Runtime state and backups |
| `/usr/lib/e2xray/bin/xray` | Embedded core matching the package architecture |

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

Version 0.6.7 also shows the concrete start failure on screen. `Error (3)` in
older versions is only Enigma2's numeric message-box type; it is not the Xray
exit code.

Confirm that TUN is available:

```sh
ls -l /dev/net/tun
```

The 0.6.7 IPKs recommend `kernel-module-tun` and full `iproute2`. During
installation, opkg tries to install packages built for the receiver's image.
Because this is a soft dependency, an offline or blocked feed does not prevent e2xray
itself from being installed. The installer and plugin UI warn that TUN must be
installed manually, and e2xray remains unusable until it is available. At start,
e2xray also tries `modprobe tun`, a direct `insmod` fallback and safe creation of
the standard character device (`10:200`). To install the module manually:

```sh
uname -r
opkg update
opkg install kernel-module-tun
reboot
```

Do not copy `tun.ko` from a different image or kernel version.

### Check TUN routing

While e2xray is running:

```sh
ip rule show
ip route show table 101
ip route get 1.1.1.1
```

The route to public addresses should use `e2xray0`. The proxy server itself
must continue to use the receiver's physical network interface. On receivers
whose BusyBox or kernel cannot use `ip rule`, version 0.6.7 automatically uses
the portable `0.0.0.0/1` and `128.0.0.0/1` split-default routes instead; this is
reported as `TUN routing mode: split default routes` in `/tmp/e2xray.log`.

To see which mode was selected:

```sh
grep 'TUN routing mode' /tmp/e2xray.log | tail -n 1
```

Expected output is either `policy table 101` or `split default routes`.

### Stop and restore networking

Use the red **Stop** button in the plugin or run:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh stop
```

Stopping e2xray removes only the policy or split routes that it successfully
created, brings down its TUN interface and restores saved DNS/network settings.

## Updating

The existing `/root/config.txt` is preserved during a normal upgrade.

Users upgrading specifically to fix the GigaBlue/OpenPLi routing error should
install version 0.6.7 directly over the older version; uninstalling first is
not required.

Upload the newer package to `/tmp`, then run either:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_NEW_VERSION_ARCH.deb
opkg install /tmp/enigma2-plugin-extensions-e2xray_NEW_VERSION_ARCH.ipk
```

The installer stops the old service, installs the new files and restarts the
Enigma2 user interface automatically. Keep using the same architecture shown
by `dpkg --print-architecture` or `opkg print-architecture`.

## Uninstalling

Remove the plugin but preserve `/root/config.txt`:

```sh
dpkg --remove enigma2-plugin-extensions-e2xray
opkg remove enigma2-plugin-extensions-e2xray
```

Remove the plugin and all of its configuration, including
`/root/config.txt`:

```sh
dpkg --purge enigma2-plugin-extensions-e2xray
```

The removal script stops e2xray, restores networking, removes the embedded
core, init links, runtime files and generated configuration, and then restarts
the Enigma2 user interface.

## Building the packages

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

Build one auto-detecting little-endian MIPS32/MIPS64 IPK:

```sh
./build.sh ipk mips-universal
```

Build one auto-detecting DEB for ARM64, ARMv7, MIPS32LE and MIPS64LE:

```sh
./build.sh deb deb-universal
```

The outputs are:

```text
enigma2-plugin-extensions-e2xray_0.6.7_arm64.deb
enigma2-plugin-extensions-e2xray_0.6.7_mipsel.deb
enigma2-plugin-extensions-e2xray_0.6.7_arm64.ipk
enigma2-plugin-extensions-e2xray_0.6.7_armv7ahf-vfp-neon.ipk
enigma2-plugin-extensions-e2xray_0.6.7_armv7ahf-neon.ipk
enigma2-plugin-extensions-e2xray_0.6.7_cortexa15hf-neon-vfpv4.ipk
enigma2-plugin-extensions-e2xray_0.6.7_all.ipk
enigma2-plugin-extensions-e2xray_0.6.7_mips-all.ipk
enigma2-plugin-extensions-e2xray_0.6.7_all.deb
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
filter values. It resolves the proxy server before enabling either its private
policy-routing table or the split-default fallback and keeps every resolved
proxy-server IPv4 address on the original gateway. The generated Xray
configuration binds outbound traffic to the original physical interface.

Stopping e2xray removes only routes and rules recorded as plugin-owned, restores
DNS and reverse-path filter values, and brings the TUN interface down. An
administrator-owned table `101`, priority `1001` rule, `/1` route or proxy-host
route is never overwritten. Stale state left by a previous crash is recovered
before the next start.

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
