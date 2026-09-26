# e2xray

Configuration file location: `/root/config.txt` when `/root` is a directory;
otherwise `/home/root/config.txt`. Installation creates a missing file with
permissions `0600` and preserves existing configuration contents.

e2xray is an Xray client for Enigma2 receivers. It routes the whole receiver's
traffic through Xray and provides Start, Stop, real-delay testing, status,
configuration selection and settings from the Enigma2 user interface.

The architecture-specific DEB/IPK packages contain the official Xray-core `v26.5.9`
binary. Users do not need to install Xray-core or download additional packages
from the Internet.

## How traffic is captured

Enigma2 images differ widely in what their kernel and userland provide, so
e2xray probes the receiver at start and picks the first backend that works:

| Order | Backend | Captures | Requires |
| --- | --- | --- | --- |
| 1 | TUN | everything | `/dev/net/tun` (`kernel-module-tun`) |
| 2 | TPROXY | TCP + UDP | `iptables`, `xt_TPROXY`, `xt_socket`, `ip rule` |
| 3 | REDIRECT | TCP only | `iptables` with NAT |

The selected backend is written to `/tmp/e2xray.log` and shown next to
**Configurations** on the main screen while e2xray runs.

In both transparent backends, DNS is redirected into Xray on port `15353` and
resolved through the tunnel, and connections are sniffed for their HTTP/TLS
hostname. This matters: without it the receiver's own resolver decides where a
connection goes, and a filtered network answers with the wrong address.

If none of the three is available, e2xray refuses to start and names the
missing component. That is an image limitation, not a configuration problem —
see [Receivers without TUN](#receivers-without-tun).

## Compatibility

| Receiver family | Image/package manager | Kernel reports | Package architecture |
| --- | --- | --- | --- |
| Dreambox One / Two | OpenDreambox (`dpkg`) | `aarch64` | `arm64` DEB |
| DM520 / DM525 | OpenDreambox (`dpkg`) | `mips` | `mipsel` DEB |
| GigaBlue UHD ARM receivers | OpenPLi/OpenBH/OpenATV (`opkg`) | `armv7l` | architecture printed by `opkg print-architecture` |
| Vu+ 4K ARM receivers | OpenPLi/OpenBH/OpenATV/VTi (`opkg`) | normally `armv7l` | ARMv7 `_all.ipk` or architecture-specific ARMv7 IPK |
| Older Vu+ MIPS receivers | OpenPLi/OpenBH/OpenATV/VTi (`opkg`) | normally `mips` | `_mips-all.ipk` |

The `mipsel` package contains the official little-endian
`Xray-linux-mips32le` core. In particular, a DM525 can report `mips` from
`uname -m` while `dpkg --print-architecture` correctly reports `mipsel`.

Do not install the ARM64 or MIPS DEBs on an ARM32 receiver. GigaBlue ARMv7
receivers must use the IPK whose architecture name appears in
`opkg print-architecture` (normally `armv7ahf-vfp-neon`, `armv7ahf-neon` or
`cortexa15hf-neon-vfpv4`). Users who are unsure may use the ARMv7 `_all.ipk`;
its installer checks the CPU before installing the bundled core.

Vu+ models are split between two CPU families. The 4K generation—including
Solo 4K, Uno 4K/SE, Ultimo 4K, Zero 4K and Duo 4K/SE—is ARM-based and normally
uses the ARMv7 `_all.ipk`. Older non-4K models—including Duo/Duo2, Solo/Solo2,
Solo SE, Uno, Ultimo and Zero—are generally MIPS and should use
`_mips-all.ipk`. Model names alone are not the final test: always verify
`uname -m` and `opkg print-architecture` before installing.

OpenATV 8 images for Dreambox One also use `opkg` and IPK packages. On those images,
`opkg print-architecture` includes `arm64`, so build and install the OpenATV
package as `enigma2-plugin-extensions-e2xray_2.0.4_arm64.ipk`.

The ARM64 build has been tested on Dreambox One. The MIPS little-endian build
targets DM525/OpenDreambox 2.5 and is statically validated in GitHub Actions;
an on-receiver test is still required for final runtime confirmation. Vu+
package selection is documented by CPU family, but runtime validation on each
Vu+ model/image combination is still required.

## Features

- Full-device traffic routing over TUN, TPROXY or iptables REDIRECT, selected
  automatically for the image
- Real-delay testing: a genuine HTTP round trip through the configuration, not
  a TCP ping to the server
- Start, Stop, Ping and Settings controls
- English, Persian and Arabic user interfaces, including translated start errors
- VLESS, VMess, Trojan and Shadowsocks share links
- Multiple named configurations on the main screen
- UTF-8 profile names, including Persian and Arabic names
- RAW/TCP, WebSocket, gRPC and XHTTP transports where supported
- XHTTP `mode`, `extra` and padding settings from share links
- TLS and REALITY transport security
- DNS resolved through the tunnel on every backend
- Hostname sniffing, so a filtered local resolver cannot redirect connections
- Direct routes and an fwmark self-bypass to prevent routing loops
- Automatic fallback for receivers whose BusyBox does not support `ip rule`
- DNS, routing and iptables restoration when e2xray stops
- Embedded architecture-matched Xray-core with no online installation dependency

e2xray is **stopped by default** after installation and after boot. It starts
only when the user selects a configuration and presses **Start**.

## Requirements

Before installation, confirm that:

- The receiver runs Enigma2 and installs packages with `dpkg` or `opkg`.
- `dpkg --print-architecture` or `opkg print-architecture` reports an architecture
  matching one of the supplied packages.
- The image provides **either** TUN **or** `iptables`. e2xray automatically
  loads the `tun` module and creates `/dev/net/tun` when the driver exists, and
  falls back to TPROXY or REDIRECT when it does not.
- You have a valid VLESS, VMess, Trojan or Shadowsocks share link.

Run these commands over SSH:

```sh
uname -m
(command -v dpkg >/dev/null && dpkg --print-architecture) || opkg print-architecture
ls -l /dev/net/tun
which iptables ip
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

Version `2.0.4` produces these packages:

```text
enigma2-plugin-extensions-e2xray_2.0.4_arm64.deb
enigma2-plugin-extensions-e2xray_2.0.4_mipsel.deb
enigma2-plugin-extensions-e2xray_2.0.4_arm64.ipk
enigma2-plugin-extensions-e2xray_2.0.4_armv7ahf-vfp-neon.ipk
enigma2-plugin-extensions-e2xray_2.0.4_armv7ahf-neon.ipk
enigma2-plugin-extensions-e2xray_2.0.4_cortexa15hf-neon-vfpv4.ipk
enigma2-plugin-extensions-e2xray_2.0.4_all.ipk
enigma2-plugin-extensions-e2xray_2.0.4_mips-all.ipk
enigma2-plugin-extensions-e2xray_2.0.4_all.deb
```

The single `_all.deb` contains ARM64, ARMv7, mips32le and mips64le cores. Its
pre-install script rejects unsupported CPUs, verifies ARMv7 floating-point and
MIPS byte-order requirements, and its post-install script selects and executes
the matching core before Enigma2 is restarted.

### Which package should I install?

| Receiver/image | Recommended package |
| --- | --- |
| GigaBlue ARMv7 with OpenPLi/OpenBH/OpenATV | `_all.ipk`, or the IPK exactly matching `opkg print-architecture` |
| Vu+ 4K ARM with OpenPLi/OpenBH/OpenATV/VTi | `_all.ipk`, or the matching ARMv7 IPK |
| Older Vu+ MIPS with `opkg` | `_mips-all.ipk` |
| Dreambox One/Two with `dpkg` | `_arm64.deb` |
| Dreambox One with `opkg` | `_arm64.ipk` |
| DM520/DM525 with `dpkg` | `_mipsel.deb` |
| Little-endian MIPS receiver with `opkg` | `_mips-all.ipk` |

Do not use `_all.deb` on an `opkg` image and do not rename a DEB to IPK.

## What's new in 2.0.4

**Ping is now a real-delay test.** Earlier versions measured a TCP connect to
the proxy server, which only proved the edge host was reachable. The yellow
button now starts a temporary Xray instance and times a complete HTTP request
carried through the selected configuration. On a tested receiver the same
profile reported `7 ms` as a TCP connect and `371 ms` as a real round trip.

**Transparent backends actually carry traffic.** TPROXY and REDIRECT were
present before but incomplete:

- Connections are now sniffed for their HTTP/TLS/QUIC hostname, so the remote
  server resolves the name instead of trusting the receiver's local answer.
- DNS is redirected into a dedicated Xray inbound and resolved through the
  tunnel, instead of staying with the receiver's resolver.
- Xray's own transport is tagged with an fwmark and returned early from the
  iptables chains, so the proxy connection can no longer capture itself.

Both were verified on real hardware: TCP, UDP and DNS confirmed flowing through
`transparent-in` and `dns-in`.

Also in this release:

- The DNS inbound listens on `15353`. Port `5353` is mDNS and `avahi-daemon`
  already owns it on most Enigma2 images.
- Cleanup loops are bounded, so a BusyBox `ip` that returns success for an
  unsupported subcommand can no longer hang Stop and strand the receiver.
- `/usr/sbin` and `/sbin` are added to `PATH` before probing, so `ip` and
  `iptables` are not reported missing merely because of a restricted
  environment.
- Start failures show a translated explanation and the actionable next step,
  not only an English detail string.
- The active backend is shown next to **Configurations**.

## Installation

### 1. Upload the package

Upload the DEB/IPK to the receiver's `/tmp` directory with SCP, FTP or an Enigma2
file manager.

Example from Windows PowerShell:

```powershell
scp .\enigma2-plugin-extensions-e2xray_2.0.4_arm64.deb root@RECEIVER_IP:/tmp/
```

For a MIPS receiver, use the `_mipsel.deb` filename instead. Replace
`RECEIVER_IP` with the receiver's IP address.

### 2. Install over SSH

On Dreambox One/Two:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_2.0.4_arm64.deb
```

On DM520/DM525:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_2.0.4_mipsel.deb
```

On GigaBlue ARMv7 with OpenPLi, OpenBH or OpenATV, first choose the filename
whose suffix is listed by
`opkg print-architecture`, then install it with:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_ARCH.ipk
```

Alternatively, use the single `_all.ipk` ARMv7 package. Its pre-install script
rejects non-ARMv7 CPUs and ARMv7 CPUs without VFPv3/VFPv4 before files are
installed; the post-install script then verifies that the embedded core runs.

Recommended simple installation for an ARMv7 GigaBlue receiver:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_all.ipk
```

The same ARMv7 package is recommended for ARM-based Vu+ 4K receivers:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_all.ipk
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

Select a configuration and press the yellow **Ping** button. e2xray starts a
temporary Xray instance, sends a real HTTP request through that configuration
and shows the round-trip time in milliseconds beside its name.

This is a real-delay test, not a TCP ping. It measures what the tunnel actually
delivers, so a server that answers TCP quickly but proxies badly is visible as a
high number rather than a low one. Expect values well above a raw `ping` to the
same host.

The Network lamp is green when the receiver has a usable IPv4 address on a real
interface. The Internet lamp probes Google, Cloudflare and Apple independently;
one success is enough, and all three failing triggers a retry before the lamp
turns red.

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
  `enigma2-plugin-extensions-e2xray_2.0.4_all.ipk` پیشنهاد می‌شود.
- برای مدل‌های 4K ویوپلاس مانند Solo 4K، Uno 4K/SE، Ultimo 4K، Zero 4K و
  Duo 4K/SE که پردازنده ARM دارند، بسته `_all.ipk` پیشنهاد می‌شود.
- برای مدل‌های قدیمی‌تر و غیر 4K ویوپلاس با پردازنده MIPS، مانند Duo2،
  Solo2، Solo SE و Zero معمولی، از بسته `_mips-all.ipk` استفاده کنید.
- برای Dreambox One/Two دارای `dpkg` از بسته `_arm64.deb` استفاده کنید.
- برای Dreambox One دارای `opkg` از بسته `_arm64.ipk` استفاده کنید.
- برای DM520/DM525 دارای `dpkg` از بسته `_mipsel.deb` استفاده کنید.
- برای ریسیور MIPS دارای `opkg` از بسته `_mips-all.ipk` استفاده کنید.

### نصب روی گیگابلو ARMv7

فایل IPK را در مسیر `/tmp` کپی و اجرا کنید:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_all.ipk
```

اگر نام معماری دقیق ریسیور را می‌دانید، می‌توانید به‌جای بسته عمومی از IPK
هم‌نام با خروجی `opkg print-architecture` استفاده کنید.

### نصب روی Vu+‎

برای مدل‌های ARM خانواده 4K:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_all.ipk
```

برای مدل‌های قدیمی‌تر دارای پردازنده MIPS:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_mips-all.ipk
```

پیش از نصب حتماً `uname -m` را بررسی کنید. خروجی `armv7l` به بسته ARMv7 و
خروجی `mips` به بسته MIPS نیاز دارد.

### خطای قفل opkg هنگام نصب

```text
error: opkg_lock: Could not lock /run/opkg.lock: Resource temporarily unavailable.
```

این خطای e2xray نیست. یعنی پروسهٔ opkg دیگری قفل مدیر بسته را گرفته است و
معمولاً وقتی پیش می‌آید که نصب از داخل صفحهٔ File Manager یا Plugin Browser
انجام شود، چون خود آن ابزار opkg را در پس‌زمینه اجرا می‌کند.

نصب را از SSH یا Telnet انجام دهید، نه از منوی روی تلویزیون. اگر خطا ادامه
داشت، ببینید واقعاً پروسه‌ای در حال اجراست یا نه:

```sh
ps w | grep "[o]pkg"
```

اگر چیزی نبود، قفل کهنه مانده و می‌توان پاکش کرد:

```sh
killall opkg 2>/dev/null; sleep 2; rm -f /run/opkg.lock
```

### ریسیورهایی که TUN ندارند

بسیاری از ایمیج‌های ویوپلاس نه ماژول TUN دارند و نه `iptables`. برای نمونه یک
Vu+ Zero 4K با کرنل `4.1.20` چنین می‌دهد:

```text
ls: /dev/net/tun: No such file or directory
-bash: iptables: command not found
```

روی چنین ریسیوری e2xray با خطای `NO_NETWORK_BACKEND` بالا نمی‌آید و می‌گوید چه
چیزی کم است.

**روش مطمئن** دستور `deps` خود پلاگین است. e2xray روی این ریسیورها هم درست نصب
می‌شود و فقط Start شکست می‌خورد، پس این دستور همیشه از طریق SSH در دسترس است:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh deps
```

می‌گوید چه چیزی کم است، نام دقیق بسته‌ها را از فید همان ریسیور پیدا می‌کند و
دستورهای لازم را چاپ می‌کند. با افزودن `install` خودش نصب هم می‌کند:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh deps install
```

فایل [`tools/e2xray-deps.sh`](tools/e2xray-deps.sh) همین کار را پیش از نصب
e2xray انجام می‌دهد.

اگر دستی انجام می‌دهید، اول وضعیت را ببینید:

```sh
ls -l /dev/net/tun
which iptables
```

اگر `/dev/net/tun` از قبل وجود داشته باشد، هیچ بسته‌ای لازم نیست.

نام بسته‌ها به نسخهٔ کرنل گره خورده و بین ایمیج‌ها فرق می‌کند، پس نمی‌توان آن را
از ریسیور دیگری کپی کرد. اول پیدایشان کنید:

```sh
opkg update
opkg list | grep kernel-module-tun
opkg list | grep ^iptables
```

سپس **یکی‌یکی** و با همان نام‌هایی که بالا دیدید نصب کنید:

```sh
opkg install kernel-module-tun-4.1.20-1.9
opkg install iptables
opkg install iptables-modules
opkg install iptables-module-xt-tproxy
opkg install iptables-module-xt-socket
```

تک‌تک نصب کردن مهم است. اگر چند نام را در یک دستور بدهید و فقط **یکی** از آن‌ها
در فید نباشد، opkg کل تراکنش را رد می‌کند و هیچ‌کدام نصب نمی‌شوند — یعنی نبودِ
یک ماژول اختیاری جلوی نصب خود TUN را هم می‌گیرد. معنی پیام
`No candidates to install` همین است.

بعد حتماً `reboot` کنید، چون ماژول TUN فقط در بوت تازه بارگذاری می‌شود.

هیچ‌کدام از این‌ها همه‌یا‌هیچ نیستند: فقط TUN بهترین حالت است، و فقط `iptables`
هم کافی است تا e2xray از مسیر REDIRECT کار کند؛ افزودن `xt_TPROXY` و
`xt_socket` علاوه بر آن UDP را هم فعال می‌کند.

### نصب روی Dreambox

برای Dreambox One/Two:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_2.0.4_arm64.deb
```

برای DM520/DM525:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-e2xray_2.0.4_mipsel.deb
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

Version 2.0.4 also shows the concrete start failure on screen. `Error (3)` in
older versions is only Enigma2's numeric message-box type; it is not the Xray
exit code.

### `opkg_lock: Could not lock /run/opkg.lock`

```text
error: opkg_lock: Could not lock /run/opkg.lock: Resource temporarily unavailable.
error: opkg_cmd_exec: Command failed to capture privilege lock.
```

Another opkg process holds the package-manager lock. This is not an e2xray
error, and it usually appears when the package is installed from an Enigma2
File Manager or Plugin Browser screen that is itself running opkg in the
background.

Install from SSH or Telnet instead of the on-screen file manager. If the error
persists, check whether an opkg process is really running:

```sh
ps w | grep "[o]pkg"
```

Wait for it to finish. If nothing is listed, the lock is stale and can be
cleared:

```sh
killall opkg 2>/dev/null; sleep 2; rm -f /run/opkg.lock
```

Then install normally:

```sh
opkg install /tmp/enigma2-plugin-extensions-e2xray_2.0.4_ARCH.ipk
```

### Receivers without TUN

Several Vu+ and other OE-Alliance images ship neither the TUN driver nor
`iptables`. A Vu+ Zero 4K on kernel `4.1.20` reports:

```text
ls: /dev/net/tun: No such file or directory
-bash: iptables: command not found
```

On such a receiver e2xray cannot capture traffic by any method and refuses to
start with `NO_NETWORK_BACKEND`, naming what is missing.

**The reliable way** is the plugin's own `deps` command. e2xray installs
successfully even on these receivers — only Start fails — so this is always
available over SSH:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh deps
```

It reports what is missing, looks up the exact package names in that receiver's
own feed, and prints the commands to run. Add `install` to let it install them:

```sh
/usr/lib/enigma2/python/Plugins/Extensions/e2xray/e2xrayctl.sh deps install
```

[`tools/e2xray-deps.sh`](tools/e2xray-deps.sh) does the same before e2xray is
installed.

To do it by hand, check the state first:

```sh
ls -l /dev/net/tun
which iptables
```

If `/dev/net/tun` already exists, nothing needs to be installed.

Package names are tied to the running kernel, so they differ between images and
cannot be copied from another receiver. Look them up:

```sh
opkg update
opkg list | grep kernel-module-tun
opkg list | grep ^iptables
```

Then install them **one at a time**, using the names that appeared above:

```sh
opkg install kernel-module-tun-4.1.20-1.9
opkg install iptables
opkg install iptables-modules
opkg install iptables-module-xt-tproxy
opkg install iptables-module-xt-socket
```

Installing them one per command matters. `opkg install` with several names
aborts the whole transaction when a single one is not in the feed, so one
missing optional module would also prevent the TUN driver from being
installed — which is what `No candidates to install` means.

Reboot afterwards, because the TUN module is only picked up on a fresh boot.

None of these are all-or-nothing. TUN alone is the best case. `iptables` alone
is enough for the REDIRECT backend; adding `xt_TPROXY` and `xt_socket`
additionally enables UDP.

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
whose BusyBox or kernel cannot use `ip rule`, version 2.0.4 automatically uses
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
install version 2.0.4 directly over the older version; uninstalling first is
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
enigma2-plugin-extensions-e2xray_2.0.4_arm64.deb
enigma2-plugin-extensions-e2xray_2.0.4_mipsel.deb
enigma2-plugin-extensions-e2xray_2.0.4_arm64.ipk
enigma2-plugin-extensions-e2xray_2.0.4_armv7ahf-vfp-neon.ipk
enigma2-plugin-extensions-e2xray_2.0.4_armv7ahf-neon.ipk
enigma2-plugin-extensions-e2xray_2.0.4_cortexa15hf-neon-vfpv4.ipk
enigma2-plugin-extensions-e2xray_2.0.4_all.ipk
enigma2-plugin-extensions-e2xray_2.0.4_mips-all.ipk
enigma2-plugin-extensions-e2xray_2.0.4_all.deb
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
