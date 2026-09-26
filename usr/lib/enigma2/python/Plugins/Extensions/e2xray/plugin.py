# -*- coding: utf-8 -*-
from __future__ import print_function

import os

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.config import (
    ConfigSelection,
    ConfigSubsection,
    config,
    configfile,
    getConfigListEntry,
)
from Tools.Directories import fileExists
from enigma import (
    RT_HALIGN_LEFT,
    RT_HALIGN_RIGHT,
    RT_VALIGN_CENTER,
    eConsoleAppContainer,
    eListboxPythonMultiContent,
    gFont,
)
from skin import parseColor
from . import PLUGIN_VERSION
from .proxy_config import (
    clear_selection,
    ensure_selection,
    read_profiles,
    read_selection,
    write_selection,
)

PLUGIN_NAME = "e2xray"
PLUGIN_DESCRIPTION = "Xray Client for Enigma2"
BASE = "/usr/lib/enigma2/python/Plugins/Extensions/e2xray"
CTL = BASE + "/e2xrayctl.sh"


def userconf_path():
    """Use the root home directory provided by the receiver image."""
    if os.path.isdir("/root"):
        return "/root/config.txt"
    return "/home/root/config.txt"


USERCONF = userconf_path()
SELECTION = "/etc/e2xray/selected"
PIDFILE = "/var/run/e2xray/xray.pid"
ACTIVE_PROFILE = "/var/run/e2xray/active_profile"
BACKEND_FILE = "/var/run/e2xray/network-backend"
RUNTIME_MARKERS = (
    PIDFILE,
    ACTIVE_PROFILE,
    "/var/run/e2xray/state",
    "/var/run/e2xray/resolv.conf.bak",
    "/var/run/e2xray/policy-table-owned",
    "/var/run/e2xray/policy-rule-owned",
    "/var/run/e2xray/split-routes-owned",
    "/var/run/e2xray/network-backend",
)
config.plugins.e2xray = ConfigSubsection()
config.plugins.e2xray.ui_language = ConfigSelection(
    default="en",
    choices=[("en", "English"), ("fa", "فارسی"), ("ar", "العربية")],
)

TEXT = {
    "en": {
        "network": "Network status",
        "internet": "Internet status",
        "checking": "Checking",
        "online": "Online",
        "offline": "Offline",
        "start": "Start",
        "stop": "Stop",
        "started": "VPN Started",
        "stopped": "VPN Stopped",
        "start_failed": "Could not start the configuration.",
        "start_detail": "Could not start the configuration:\n%s",
        "execute_failed": "Could not run the e2xray control command.",
        "stop_failed": "Could not stop the proxy.",
        "ping": "Ping",
        "settings": "Settings",
        "language": "Language",
        "configurations": "Configurations",
        "about": "About",
        "save": "Save",
        "cancel": "Cancel",
        "close": "Close",
        "no_config": "No Config. Found",
        "no_selected": "No Configuration Selected.",
        "invalid_config": "Invalid proxy configuration.",
        "stop_before_change": "Stop e2xray before changing configuration.",
        "ping_ok": "Configuration server is reachable.",
        "ping_failed": "Configuration server is not reachable.",
        "missing": "e2xray control file was not found.",
        "save_error": "Could not save configuration: %s",
        "version": "Plugin version",
    },
    "fa": {
        "network": "وضعیت شبکه",
        "internet": "وضعیت اینترنت",
        "checking": "در حال بررسی",
        "online": "آنلاین",
        "offline": "آفلاین",
        "start": "شروع",
        "stop": "توقف",
        "started": "کانفیگ استارت شد",
        "stopped": "فیلترشکن متوقف شد",
        "start_failed": "کانفیگ استارت نشد",
        "start_detail": "کانفیگ استارت نشد:\n%s",
        "execute_failed": "فرمان کنترل e2xray اجرا نشد.",
        "stop_failed": "فیلترشکن متوقف نشد",
        "ping": "پینگ",
        "settings": "تنظیمات",
        "language": "زبان",
        "configurations": "کانفیگ‌ها",
        "about": "درباره",
        "save": "ذخیره",
        "cancel": "انصراف",
        "close": "خروج",
        "no_config": "کانفیگی پیدا نشد",
        "no_selected": "هیچ کانفیگی انتخاب نشده",
        "invalid_config": "کانفیگ پراکسی معتبر نیست.",
        "stop_before_change": "پیش از تغییر کانفیگ، e2xray را متوقف کنید.",
        "ping_ok": "سرور کانفیگ در دسترس است.",
        "ping_failed": "سرور کانفیگ در دسترس نیست.",
        "missing": "فایل کنترل e2xray پیدا نشد.",
        "save_error": "کانفیگ ذخیره نشد: %s",
        "version": "نسخه پلاگین",
    },
    "ar": {
        "network": "حالة الشبكة",
        "internet": "حالة الإنترنت",
        "checking": "جار الفحص",
        "online": "متصل",
        "offline": "غير متصل",
        "start": "تشغيل",
        "stop": "إيقاف",
        "started": "تم تشغيل الاتصال",
        "stopped": "تم إيقاف البروكسي",
        "start_failed": "تعذر تشغيل الاتصال",
        "start_detail": "تعذر تشغيل الاتصال:\n%s",
        "execute_failed": "تعذر تشغيل أمر التحكم في e2xray.",
        "stop_failed": "تعذر إيقاف البروكسي",
        "ping": "اختبار",
        "settings": "الإعدادات",
        "language": "اللغة",
        "configurations": "الاتصالات",
        "about": "حول",
        "save": "حفظ",
        "cancel": "إلغاء",
        "close": "إغلاق",
        "no_config": "لم يتم العثور على إعداد",
        "no_selected": "لم يتم اختيار أي اتصال",
        "invalid_config": "إعداد البروكسي غير صالح.",
        "stop_before_change": "أوقف e2xray قبل تغيير الاتصال.",
        "ping_ok": "خادم الإعداد متاح.",
        "ping_failed": "خادم الإعداد غير متاح.",
        "missing": "لم يتم العثور على ملف التحكم e2xray.",
        "save_error": "تعذر حفظ الإعداد: %s",
        "version": "إصدار الإضافة",
    },
}


# The control layer reports a machine-readable code plus an English detail.
# Users see the localized explanation and the actionable next step; the raw
# detail is kept in /tmp/e2xray.log for support.
ERROR_TEXT = {
    "en": {
        "NO_CONFIG": "No valid configuration was found. Check %s." % USERCONF,
        "CORE_MISSING": "The bundled Xray core is missing. Reinstall the package.",
        "INTEGRITY_FAILED": "Protected files were modified. Reinstall the original package.",
        "PYTHON_MISSING": "This image has no usable Python interpreter.",
        "ROUTE_MISSING": "No default network interface was found. Check the network settings.",
        "DNS_FAILED": "The proxy server address could not be resolved.",
        "CONFIG_INVALID": "Xray rejected this configuration. Check the share link.",
        "NO_NETWORK_BACKEND": (
            "This image cannot capture traffic: it has neither TUN nor iptables.\n"
            "Install kernel-module-tun and iptables with opkg, then reboot."
        ),
        "TUN_CREATE_FAILED": "The TUN interface could not be created.",
        "TUN_LINK_FAILED": "The TUN interface could not be brought up.",
        "TUN_ADDRESS_FAILED": "The TUN interface address could not be assigned.",
        "ROUTE_TABLE_FAILED": "The routing table could not be prepared.",
        "IP_RULE_FAILED": "This image's ip command does not support policy routing.",
        "SERVER_BYPASS_ROUTE_FAILED": "The proxy-server bypass route could not be installed.",
        "TPROXY_SETUP_FAILED": "TPROXY is unavailable on this image.",
        "REDIRECT_SETUP_FAILED": "iptables REDIRECT is unavailable on this image.",
        "BACKEND_CONFIG_FAILED": "Xray could not be configured for this mode.",
        "DNS_WRITE_FAILED": "/etc/resolv.conf could not be updated.",
        "SERVER_FILTERED": (
            "This configuration's server address is blocked on your connection:\n"
            "your provider redirects it to a filtering page. Choose another\n"
            "configuration, or one that uses a plain IP address."
        ),
        "TUNNEL_DEAD": (
            "The tunnel started but carried no traffic, so the server is not\n"
            "answering. Normal networking has been restored. Try another\n"
            "configuration."
        ),
    },
    "fa": {
        "NO_CONFIG": "کانفیگ معتبری پیدا نشد. فایل ‎%s را بررسی کنید." % USERCONF,
        "CORE_MISSING": "هستهٔ Xray در بسته نیست. بسته را دوباره نصب کنید.",
        "INTEGRITY_FAILED": "فایل‌های محافظت‌شده تغییر کرده‌اند. بستهٔ اصلی را دوباره نصب کنید.",
        "PYTHON_MISSING": "این ایمیج مفسر پایتون قابل استفاده ندارد.",
        "ROUTE_MISSING": "کارت شبکهٔ پیش‌فرض پیدا نشد. تنظیمات شبکه را بررسی کنید.",
        "DNS_FAILED": "آدرس سرور پروکسی resolve نشد.",
        "CONFIG_INVALID": "Xray این کانفیگ را نپذیرفت. لینک اشتراک را بررسی کنید.",
        "NO_NETWORK_BACKEND": (
            "این ایمیج امکان گرفتن ترافیک را ندارد: نه TUN دارد نه iptables.\n"
            "با opkg بسته‌های kernel-module-tun و iptables را نصب و ریست کنید."
        ),
        "TUN_CREATE_FAILED": "رابط TUN ساخته نشد.",
        "TUN_LINK_FAILED": "رابط TUN بالا نیامد.",
        "TUN_ADDRESS_FAILED": "آدرس رابط TUN تنظیم نشد.",
        "ROUTE_TABLE_FAILED": "جدول مسیریابی آماده نشد.",
        "IP_RULE_FAILED": "دستور ip این ایمیج از policy routing پشتیبانی نمی‌کند.",
        "SERVER_BYPASS_ROUTE_FAILED": "مسیر مستقیم به سرور پروکسی نصب نشد.",
        "TPROXY_SETUP_FAILED": "TPROXY روی این ایمیج در دسترس نیست.",
        "REDIRECT_SETUP_FAILED": "iptables REDIRECT روی این ایمیج در دسترس نیست.",
        "BACKEND_CONFIG_FAILED": "Xray برای این حالت پیکربندی نشد.",
        "DNS_WRITE_FAILED": "فایل ‎/etc/resolv.conf به‌روزرسانی نشد.",
        "SERVER_FILTERED": (
            "آدرس سرور این کانفیگ روی اینترنت شما فیلتر است:\n"
            "سرویس‌دهنده آن را به صفحهٔ فیلترینگ هدایت می‌کند. کانفیگ دیگری\n"
            "انتخاب کنید، یا کانفیگی که مستقیم از IP استفاده می‌کند."
        ),
        "TUNNEL_DEAD": (
            "تونل بالا آمد اما هیچ ترافیکی از آن عبور نکرد؛ سرور پاسخ نمی‌دهد.\n"
            "اینترنت به حالت عادی برگردانده شد. کانفیگ دیگری را امتحان کنید."
        ),
    },
    "ar": {
        "NO_CONFIG": "لم يتم العثور على إعداد صالح. تحقق من ‎%s." % USERCONF,
        "CORE_MISSING": "نواة Xray مفقودة. أعد تثبيت الحزمة.",
        "INTEGRITY_FAILED": "تم تعديل الملفات المحمية. أعد تثبيت الحزمة الأصلية.",
        "PYTHON_MISSING": "لا يوجد مفسر Python صالح في هذه النسخة.",
        "ROUTE_MISSING": "لم يتم العثور على واجهة الشبكة الافتراضية.",
        "DNS_FAILED": "تعذر ترجمة عنوان خادم البروكسي.",
        "CONFIG_INVALID": "رفض Xray هذا الإعداد. تحقق من رابط المشاركة.",
        "NO_NETWORK_BACKEND": (
            "هذه النسخة لا تستطيع التقاط حركة المرور: لا TUN ولا iptables.\n"
            "ثبّت kernel-module-tun و iptables عبر opkg ثم أعد التشغيل."
        ),
        "TUN_CREATE_FAILED": "تعذر إنشاء واجهة TUN.",
        "TUN_LINK_FAILED": "تعذر تشغيل واجهة TUN.",
        "TUN_ADDRESS_FAILED": "تعذر تعيين عنوان واجهة TUN.",
        "ROUTE_TABLE_FAILED": "تعذر تجهيز جدول التوجيه.",
        "IP_RULE_FAILED": "أمر ip في هذه النسخة لا يدعم توجيه السياسات.",
        "SERVER_BYPASS_ROUTE_FAILED": "تعذر تثبيت مسار تجاوز خادم البروكسي.",
        "TPROXY_SETUP_FAILED": "TPROXY غير متاح في هذه النسخة.",
        "REDIRECT_SETUP_FAILED": "iptables REDIRECT غير متاح في هذه النسخة.",
        "BACKEND_CONFIG_FAILED": "تعذر تهيئة Xray لهذا الوضع.",
        "DNS_WRITE_FAILED": "تعذر تحديث ‎/etc/resolv.conf.",
        "SERVER_FILTERED": (
            "عنوان خادم هذا الإعداد محجوب على اتصالك: يعيد مزود الخدمة\n"
            "توجيهه إلى صفحة الحجب. اختر إعدادًا آخر أو إعدادًا يستخدم عنوان IP."
        ),
        "TUNNEL_DEAD": (
            "بدأ النفق لكن لم تمر أي حركة مرور خلاله؛ الخادم لا يستجيب.\n"
            "تمت استعادة الاتصال الطبيعي. جرّب إعدادًا آخر."
        ),
    },
}


def tr(key):
    language = config.plugins.e2xray.ui_language.value
    return TEXT.get(language, TEXT["en"]).get(key, key)


def errorText(code, detail):
    """Localized explanation for a control-layer error code."""
    language = config.plugins.e2xray.ui_language.value
    table = ERROR_TEXT.get(language, ERROR_TEXT["en"])
    message = table.get(code) or ERROR_TEXT["en"].get(code)
    if not message:
        return detail or tr("start_failed")
    if detail and detail != message:
        return "%s\n\n(%s)" % (message, detail)
    return message


def guiText(value):
    if value is None:
        return ""
    try:
        if isinstance(value, unicode):
            return value.encode("utf-8")
    except NameError:
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value
    return str(value)


def sameLabel(left, right):
    """Compare two menu labels regardless of str/unicode representation.

    On Python 2 images the listbox hands back a unicode object while the label
    list still holds UTF-8 byte strings. Comparing the two makes Python decode
    the bytes as ASCII, which silently fails for every non-Latin script: the
    menu worked in English and stopped responding in Persian and Arabic.
    """
    return guiText(left) == guiText(right)


def menuIndex(menu):
    """Selected row of a MenuList, across Enigma2 API variations."""
    for name in ("getSelectionIndex", "getSelectedIndex", "getCurrentIndex"):
        getter = getattr(menu, name, None)
        if not callable(getter):
            continue
        try:
            index = int(getter())
        except Exception:
            continue
        if index >= 0:
            return index
    return -1


def connectSignal(signal, callback):
    if hasattr(signal, "connect"):
        return signal.connect(callback)
    if hasattr(signal, "get"):
        signal.get().append(callback)
        return None
    signal.append(callback)
    return None


def outputValue(output, key):
    prefix = key + "="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def coreRunning():
    """Return True only when the recorded PID is the bundled Xray process."""
    try:
        with open(PIDFILE, "r") as source:
            pid = int(source.readline().strip())
        if pid <= 1:
            return False
        os.kill(pid, 0)

        proc_cmdline = "/proc/%d/cmdline" % pid
        with open(proc_cmdline, "rb") as source:
            command = source.read().replace(b"\x00", b" ")
        if not isinstance(command, str):
            command = command.decode("utf-8", "ignore")
        return "/usr/lib/e2xray/bin/xray" in command
    except (IOError, OSError, TypeError, ValueError):
        return False


def runtimeStatePresent():
    return any(os.path.exists(path) for path in RUNTIME_MARKERS)


def activeBackend():
    if not coreRunning():
        return ""
    try:
        with open(BACKEND_FILE, "r") as source:
            return source.readline().strip().upper()
    except (IOError, OSError):
        return ""


def activeProfileId():
    if not coreRunning():
        return ""
    try:
        with open(ACTIVE_PROFILE, "r") as source:
            return source.readline().strip()
    except (IOError, OSError):
        return ""


class E2XrayProfileList(MenuList):
    def __init__(self):
        MenuList.__init__(
            self,
            [],
            enableWrapAround=True,
            content=eListboxPythonMultiContent,
        )
        self.l.setFont(0, gFont("Regular", 24))
        self.l.setItemHeight(42)

    def buildEntry(self, profile):
        symbol = guiText(profile.get("_MARK", ""))
        name = guiText(profile.get("PROFILE_NAME", ""))
        return [
            profile,
            (
                eListboxPythonMultiContent.TYPE_TEXT,
                12,
                0,
                42,
                42,
                0,
                RT_HALIGN_LEFT | RT_VALIGN_CENTER,
                symbol,
                0x0000CC44,
                0x0000CC44,
            ),
            (
                eListboxPythonMultiContent.TYPE_TEXT,
                62,
                0,
                385,
                42,
                0,
                RT_HALIGN_LEFT | RT_VALIGN_CENTER,
                name,
                0x00FFFFFF,
                0x00FFFFFF,
            ),
            (
                eListboxPythonMultiContent.TYPE_TEXT,
                455,
                0,
                110,
                42,
                0,
                RT_HALIGN_RIGHT | RT_VALIGN_CENTER,
                guiText(profile.get("_PING", "")),
                0x00FFFFFF,
                0x00FFFFFF,
            ),
        ]

    def setProfiles(self, profiles, current_index=0):
        self.setList([self.buildEntry(profile) for profile in profiles])
        try:
            self.moveToIndex(current_index)
        except Exception:
            pass


class E2XrayMain(Screen):
    skin = """
    <screen name="E2XrayMain" position="center,center" size="760,520" title="e2xray">
        <widget name="network_label" position="85,28" size="235,42" font="Regular;26" />
        <widget name="network_lamp" position="330,30" size="38,38" font="Regular;32" />
        <widget name="network_msg" position="385,28" size="290,42" font="Regular;26" />
        <widget name="internet_label" position="85,78" size="235,42" font="Regular;26" />
        <widget name="internet_lamp" position="330,80" size="38,38" font="Regular;32" />
        <widget name="internet_msg" position="385,78" size="290,42" font="Regular;26" />
        <widget name="configuration_label" position="85,135" size="590,38" font="Regular;24" />
        <widget name="profiles" position="85,178" size="590,222" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="35,455" size="150,38" font="Regular;22" foregroundColor="red" halign="center" />
        <widget name="key_green" position="205,455" size="150,38" font="Regular;22" foregroundColor="green" halign="center" />
        <widget name="key_yellow" position="375,455" size="150,38" font="Regular;22" foregroundColor="yellow" halign="center" />
        <widget name="key_blue" position="545,455" size="180,38" font="Regular;22" foregroundColor="blue" halign="center" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.container = eConsoleAppContainer()
        self.network_container = eConsoleAppContainer()
        self.internet_container = eConsoleAppContainer()
        self.signal_connections = [
            connectSignal(self.container.appClosed, self.commandDone),
            connectSignal(self.container.dataAvail, self.commandOutput),
            connectSignal(self.network_container.appClosed, self.networkDone),
            connectSignal(self.network_container.dataAvail, self.networkOutput),
            connectSignal(self.internet_container.appClosed, self.internetDone),
            connectSignal(self.internet_container.dataAvail, self.internetOutput),
        ]
        self.output = ""
        self.network_output = ""
        self.network_busy = False
        self.internet_output = ""
        self.internet_busy = False
        self.current_action = None
        self.pending_ping_id = ""
        self.ping_results = {}
        self.network_state = "checking"
        self.internet_state = "checking"
        self["network_label"] = Label("")
        self["network_lamp"] = Label("●")
        self["network_msg"] = Label("")
        self["internet_label"] = Label("")
        self["internet_lamp"] = Label("●")
        self["internet_msg"] = Label("")
        self["configuration_label"] = Label("")
        self["profiles"] = E2XrayProfileList()
        self["key_red"] = Label("")
        self["key_green"] = Label("")
        self["key_yellow"] = Label("")
        self["key_blue"] = Label("")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "DirectionActions"],
            {
                "cancel": self.close,
                "ok": self.selectHighlighted,
                "up": self["profiles"].up,
                "down": self["profiles"].down,
                "green": self.start,
                "red": self.stop,
                "yellow": self.ping,
                "blue": self.settings,
            },
            -1,
        )
        self.onLayoutFinish.append(self.firstRun)

    def firstRun(self):
        self.reloadProfiles()
        self.refreshText()
        # Missing TUN is no longer a fatal GUI condition. The control layer
        # automatically falls back to TPROXY and then TCP REDIRECT when needed.
        self.runNetworkCheck()
        self.runInternetCheck()

    def refreshText(self):
        self["network_label"].setText(tr("network"))
        self["network_msg"].setText(tr(self.network_state))
        self["internet_label"].setText(tr("internet"))
        self["internet_msg"].setText(tr(self.internet_state))
        backend = activeBackend()
        self["configuration_label"].setText(
            "%s (%s)" % (tr("configurations"), backend)
            if backend
            else tr("configurations")
        )
        self["key_red"].setText(tr("stop"))
        self["key_green"].setText(tr("start"))
        self["key_yellow"].setText(tr("ping"))
        self["key_blue"].setText(tr("settings"))

    def commandOutput(self, data):
        try:
            if not isinstance(data, str):
                data = data.decode("utf-8", "ignore")
        except Exception:
            data = str(data)
        self.output += data

    def networkOutput(self, data):
        try:
            if not isinstance(data, str):
                data = data.decode("utf-8", "ignore")
        except Exception:
            data = str(data)
        self.network_output += data

    def networkDone(self, retval):
        output = self.network_output
        self.network_output = ""
        self.network_busy = False
        if "E2XRAY_LAN=ONLINE" in output:
            self.setNetwork("online", "green")
        else:
            self.setNetwork("offline", "red")

    def internetOutput(self, data):
        try:
            if not isinstance(data, str):
                data = data.decode("utf-8", "ignore")
        except Exception:
            data = str(data)
        self.internet_output += data

    def internetDone(self, retval):
        output = self.internet_output
        self.internet_output = ""
        self.internet_busy = False
        if "E2XRAY_NET=ONLINE" in output:
            self.setInternet("online", "green")
        else:
            self.setInternet("offline", "red")

    def commandDone(self, retval):
        output = self.output
        action = self.current_action
        refresh_connectivity = False
        self.output = ""
        self.current_action = None

        if action == "ping":
            if "E2XRAY_CONFIG_PING=NO_CONFIG" in output:
                self.session.open(
                    MessageBox,
                    tr("no_selected"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
            elif "E2XRAY_CONFIG_PING=OK" in output:
                profile_id = outputValue(output, "E2XRAY_CONFIG_PING_ID")
                latency = outputValue(output, "E2XRAY_CONFIG_PING_MS")
                if profile_id and latency:
                    self.ping_results[profile_id] = latency + "ms"
                    self.reloadProfiles(profile_id)
                else:
                    self.session.open(
                        MessageBox,
                        tr("ping_failed"),
                        MessageBox.TYPE_ERROR,
                        timeout=7,
                    )
            else:
                if self.pending_ping_id:
                    self.ping_results.pop(self.pending_ping_id, None)
                    self.reloadProfiles(self.pending_ping_id)
                self.session.open(MessageBox, tr("ping_failed"), MessageBox.TYPE_ERROR, timeout=7)
            self.pending_ping_id = ""
        elif action == "start":
            if "E2XRAY_NOOP=ALREADY_RUNNING" in output:
                backend = activeBackend()
                self.session.open(
                    MessageBox,
                    "%s (%s)" % (tr("started"), backend) if backend else tr("started"),
                    MessageBox.TYPE_INFO,
                    timeout=5,
                )
            elif "E2XRAY_NOOP=" in output:
                # Another state-changing command owns the control lock.
                pass
            elif retval == 0 and "E2XRAY_ACTION=STARTED" in output:
                backend = outputValue(output, "E2XRAY_BACKEND")
                self.session.open(
                    MessageBox,
                    "%s (%s)" % (tr("started"), backend) if backend else tr("started"),
                    MessageBox.TYPE_INFO,
                    timeout=5,
                )
                refresh_connectivity = True
            else:
                code = outputValue(output, "E2XRAY_ERROR")
                detail = outputValue(output, "E2XRAY_ERROR_DETAIL")
                self.session.open(
                    MessageBox,
                    errorText(code, detail),
                    MessageBox.TYPE_ERROR,
                    timeout=20,
                )
        elif action == "stop":
            if "E2XRAY_NOOP=" in output:
                # Already stopped/busy is a silent no-op by design.
                pass
            elif retval == 0 and "E2XRAY_ACTION=STOPPED" in output:
                self.session.open(
                    MessageBox,
                    tr("stopped"),
                    MessageBox.TYPE_INFO,
                    timeout=5,
                )
                refresh_connectivity = True
            else:
                self.session.open(
                    MessageBox,
                    tr("stop_failed"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
        if action in ("start", "stop"):
            self.reloadProfiles()
            self.refreshText()
        if refresh_connectivity:
            self.runNetworkCheck()
            self.runInternetCheck()

    def setNetwork(self, state, color):
        colors = {"green": "00cc44", "red": "ff3030", "yellow": "ffd000"}
        self.network_state = state
        self["network_lamp"].setText("●")
        try:
            self["network_lamp"].instance.setForegroundColor(parseColor("#" + colors[color]))
        except Exception:
            pass
        self["network_msg"].setText(tr(state))

    def setInternet(self, state, color):
        colors = {"green": "00cc44", "red": "ff3030", "yellow": "ffd000"}
        self.internet_state = state
        self["internet_lamp"].setText("●")
        try:
            self["internet_lamp"].instance.setForegroundColor(parseColor("#" + colors[color]))
        except Exception:
            pass
        self["internet_msg"].setText(tr(state))

    def runCtl(self, argument, action):
        # Only one control operation may be in flight at a time. This protects
        # Start/Stop/Ping from rapid repeated key presses and race conditions.
        if self.current_action is not None:
            return
        if not fileExists(CTL):
            self.session.open(MessageBox, tr("missing"), MessageBox.TYPE_ERROR, timeout=8)
            return
        self.output = ""
        self.current_action = action
        if self.container.execute("%s %s" % (CTL, argument)) != 0:
            self.current_action = None
            self.session.open(
                MessageBox,
                tr("execute_failed"),
                MessageBox.TYPE_ERROR,
                timeout=8,
            )

    def runNetworkCheck(self):
        if self.network_busy or not fileExists(CTL):
            return
        self.network_output = ""
        self.network_busy = True
        self.setNetwork("checking", "yellow")
        if self.network_container.execute("%s network" % CTL) != 0:
            self.network_busy = False
            self.setNetwork("offline", "red")

    def runInternetCheck(self):
        if self.internet_busy or not fileExists(CTL):
            return
        self.internet_output = ""
        self.internet_busy = True
        self.setInternet("checking", "yellow")
        if self.internet_container.execute("%s internet" % CTL) != 0:
            self.internet_busy = False
            self.setInternet("offline", "red")

    def reloadProfiles(self, preferred_id=None):
        try:
            profiles = read_profiles(USERCONF)
            selected_id = read_selection(SELECTION)
            known_ids = set(profile["PROFILE_ID"] for profile in profiles)
            if selected_id and selected_id not in known_ids:
                clear_selection(SELECTION)
                selected_id = ""
            if not selected_id:
                # Fresh install: config.txt already holds profiles but nothing
                # has been selected yet. Adopt the first one so Start works
                # straight away instead of reporting "No Configuration
                # Selected".
                adopted = ensure_selection(profiles, SELECTION)
                if adopted is not None:
                    selected_id = adopted["PROFILE_ID"]
        except (IOError, OSError, ValueError):
            profiles = []
            selected_id = ""

        active_id = activeProfileId()
        rows = []
        current_index = 0
        for index, profile in enumerate(profiles):
            row = dict(profile)
            if profile["PROFILE_ID"] == active_id:
                # The skin font on some Dreambox images has no Unicode check glyph.
                row["_MARK"] = "V"
            elif profile["PROFILE_ID"] == selected_id:
                row["_MARK"] = "X"
            else:
                row["_MARK"] = ""
            row["_PING"] = self.ping_results.get(profile["PROFILE_ID"], "")
            rows.append(row)
            target_id = preferred_id or selected_id
            if profile["PROFILE_ID"] == target_id:
                current_index = index

        if not rows:
            rows = [
                {
                    "PROFILE_ID": "",
                    "PROFILE_NAME": tr("no_config"),
                    "_MARK": "",
                    "_PING": "",
                }
            ]
        self["profiles"].setProfiles(rows, current_index)

    def currentProfile(self):
        profile = self["profiles"].getCurrent()
        if isinstance(profile, (list, tuple)) and profile:
            profile = profile[0]
        if not profile or not profile.get("PROFILE_ID"):
            return None
        return profile

    def selectedProfile(self):
        selected_id = read_selection(SELECTION)
        if not selected_id:
            self.session.open(
                MessageBox,
                tr("no_selected"),
                MessageBox.TYPE_ERROR,
                timeout=7,
            )
            return None
        try:
            profiles = read_profiles(USERCONF)
        except (IOError, OSError, ValueError):
            self.session.open(
                MessageBox,
                tr("no_config"),
                MessageBox.TYPE_ERROR,
                timeout=7,
            )
            return None
        for profile in profiles:
            if profile["PROFILE_ID"] == selected_id:
                return profile
        clear_selection(SELECTION)
        self.reloadProfiles()
        self.session.open(
            MessageBox,
            tr("no_selected"),
            MessageBox.TYPE_ERROR,
            timeout=7,
        )
        return None

    def selectHighlighted(self):
        if self.current_action is not None:
            return
        profile = self.currentProfile()
        if not profile:
            return
        active_id = activeProfileId()
        if active_id:
            self.session.open(
                MessageBox,
                tr("stop_before_change"),
                MessageBox.TYPE_ERROR,
                timeout=7,
            )
            self.reloadProfiles(active_id)
            return
        selected_id = read_selection(SELECTION)
        if selected_id == profile["PROFILE_ID"]:
            # Pressing OK on the already-selected profile is a no-op. Clearing
            # it would only produce a state in which Start refuses to run.
            return
        try:
            write_selection(SELECTION, profile["PROFILE_ID"])
        except (IOError, OSError, ValueError):
            self.session.open(
                MessageBox,
                tr("invalid_config"),
                MessageBox.TYPE_ERROR,
                timeout=7,
            )
            return
        self.reloadProfiles(profile["PROFILE_ID"])

    def start(self):
        if self.current_action is not None:
            return
        # Keep Start idempotent, but confirm the running state to the user.
        # This restores the "VPN Started" notification from earlier releases
        # without restarting Xray or disturbing the active tunnel.
        if coreRunning():
            backend = activeBackend()
            self.session.open(
                MessageBox,
                "%s (%s)" % (tr("started"), backend) if backend else tr("started"),
                MessageBox.TYPE_INFO,
                timeout=5,
            )
            return
        if self.selectedProfile():
            self.runCtl("start", "start")

    def stop(self):
        # Repeated Stop after a clean shutdown is silent. If Xray crashed but
        # left routes/DNS runtime state behind, allow Stop to perform recovery.
        if self.current_action is not None:
            return
        if not coreRunning() and not runtimeStatePresent():
            return
        self.runCtl("stop", "stop")

    def ping(self):
        if self.current_action is not None:
            return
        profile = self.selectedProfile()
        if profile:
            self.pending_ping_id = profile["PROFILE_ID"]
            self.runCtl("ping", "ping")

    def settings(self):
        if self.current_action is not None:
            return
        self.session.openWithCallback(self.settingsClosed, E2XraySettingsMenu)

    def settingsClosed(self, *args):
        self.reloadProfiles()
        self.refreshText()
        self.runNetworkCheck()
        self.runInternetCheck()


class E2XraySettingsMenu(Screen):
    skin = """
    <screen name="E2XraySettingsMenu" position="center,center" size="650,320" title="e2xray">
        <widget name="menu" position="30,35" size="590,205" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="35,260" size="170,38" font="Regular;22" foregroundColor="red" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.labels = [guiText(tr("language")), guiText(tr("about"))]
        self["menu"] = MenuList(self.labels)
        self["key_red"] = Label(tr("close"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "DirectionActions"],
            {
                "ok": self.openSelected,
                "cancel": self.close,
                "red": self.close,
                "up": self["menu"].up,
                "down": self["menu"].down,
            },
            -1,
        )

    def openSelected(self):
        # Dispatch by row index, never by label text: the label is translated
        # and comparing a unicode row against a UTF-8 byte label fails on
        # Python 2 for every non-Latin script.
        index = menuIndex(self["menu"])
        if index < 0:
            current = self["menu"].getCurrent()
            for position, label in enumerate(self.labels):
                if sameLabel(current, label):
                    index = position
                    break
        if index == 0:
            self.session.openWithCallback(self.refresh, E2XrayLanguage)
        elif index == 1:
            self.session.open(E2XrayAbout)

    def refresh(self, *args):
        self.labels = [guiText(tr("language")), guiText(tr("about"))]
        self["menu"].setList(self.labels)
        self["key_red"].setText(tr("close"))


class E2XrayLanguage(Screen, ConfigListScreen):
    skin = """
    <screen name="E2XrayLanguage" position="center,center" size="680,280" title="e2xray">
        <widget name="config" position="40,35" size="600,145" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="60,215" size="170,38" font="Regular;22" foregroundColor="red" />
        <widget name="key_green" position="450,215" size="170,38" font="Regular;22" foregroundColor="green" halign="right" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.list = [getConfigListEntry(tr("language"), config.plugins.e2xray.ui_language)]
        ConfigListScreen.__init__(self, self.list, session=session)
        try:
            self["config"].l.setSeperation(230)
        except Exception:
            pass
        self["key_red"] = Label(tr("cancel"))
        self["key_green"] = Label(tr("save"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {"cancel": self.cancel, "red": self.cancel, "green": self.save},
            -1,
        )

    def save(self):
        config.plugins.e2xray.ui_language.save()
        configfile.save()
        self.close(True)

    def cancel(self):
        config.plugins.e2xray.ui_language.cancel()
        self.close(False)


class E2XrayAbout(Screen):
    skin = """
    <screen name="E2XrayAbout" position="center,center" size="700,410" title="e2xray">
        <widget name="telegram_icon" position="65,55" size="44,44" alphatest="blend" />
        <widget name="telegram" position="130,57" size="500,42" font="Regular;25" />
        <widget name="youtube_icon" position="65,130" size="44,44" alphatest="blend" />
        <widget name="youtube" position="130,132" size="500,42" font="Regular;25" />
        <widget name="github_icon" position="65,205" size="44,44" alphatest="blend" />
        <widget name="github" position="130,207" size="500,42" font="Regular;25" />
        <widget name="version" position="65,290" size="570,42" font="Regular;24" halign="center" />
        <widget name="key_red" position="30,350" size="170,38" font="Regular;22" foregroundColor="red" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self["telegram_icon"] = Pixmap()
        self["youtube_icon"] = Pixmap()
        self["github_icon"] = Pixmap()
        self["telegram"] = Label("@Routekernel1")
        self["youtube"] = Label("Routekernel")
        self["github"] = Label("github.com/dreamboxone")
        self["version"] = Label("%s: %s" % (tr("version"), PLUGIN_VERSION))
        self["key_red"] = Label(tr("close"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {"cancel": self.close, "ok": self.close, "red": self.close},
            -1,
        )
        self.onLayoutFinish.append(self.loadIcons)

    def loadIcons(self):
        for widget, filename in (
            ("telegram_icon", "telegram.png"),
            ("youtube_icon", "youtube.png"),
            ("github_icon", "github.png"),
        ):
            try:
                self[widget].instance.setPixmapFromFile(BASE + "/" + filename)
            except Exception:
                pass


def main(session, **kwargs):
    session.open(E2XrayMain)


def menu(menuid, **kwargs):
    if menuid == "network":
        return [(PLUGIN_NAME, main, "e2xray", 50)]
    return []


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name=PLUGIN_NAME,
            description=PLUGIN_DESCRIPTION,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main,
        ),
        PluginDescriptor(
            name=PLUGIN_NAME,
            description=PLUGIN_DESCRIPTION,
            where=PluginDescriptor.WHERE_MENU,
            fnc=menu,
        ),
    ]
