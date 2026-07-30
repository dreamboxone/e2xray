# -*- coding: utf-8 -*-
from __future__ import print_function

try:
    from urllib.parse import parse_qs, unquote, urlsplit
except ImportError:
    from urlparse import parse_qs, urlsplit
    from urllib import unquote

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.config import (
    ConfigSelection,
    ConfigSubsection,
    ConfigText,
    config,
    configfile,
    getConfigListEntry,
)
from Tools.Directories import fileExists
from enigma import eConsoleAppContainer
from skin import parseColor
from . import PLUGIN_VERSION

PLUGIN_NAME = "e2xray"
PLUGIN_DESCRIPTION = "Xray Client for Enigma2"
BASE = "/usr/lib/enigma2/python/Plugins/Extensions/e2xray"
CTL = BASE + "/e2xrayctl.sh"
USERCONF = "/etc/e2xray/server.conf"

config.plugins.e2xray = ConfigSubsection()
config.plugins.e2xray.ui_language = ConfigSelection(
    default="en",
    choices=[("en", "English"), ("fa", "فارسی"), ("ar", "العربية")],
)
config.plugins.e2xray.config_entry = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.server = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.port = ConfigText(default="443", fixed_size=False)
config.plugins.e2xray.uuid = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.sni = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.public_key = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.short_id = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.fingerprint = ConfigText(default="chrome", fixed_size=False)
config.plugins.e2xray.security = ConfigSelection(
    default="reality",
    choices=[("reality", "Reality"), ("tls", "TLS"), ("none", "None")],
)
config.plugins.e2xray.network = ConfigSelection(
    default="tcp",
    choices=[("tcp", "TCP"), ("ws", "WebSocket"), ("grpc", "gRPC")],
)
config.plugins.e2xray.path = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.host = ConfigText(default="", fixed_size=False)
config.plugins.e2xray.flow = ConfigText(default="", fixed_size=False)

TEXT = {
    "en": {
        "internet": "Internet status",
        "checking": "Checking",
        "online": "Online",
        "offline": "Offline",
        "national": "National internet",
        "start": "Start",
        "stop": "Stop",
        "ping": "Ping",
        "settings": "Settings",
        "language": "Language",
        "config_entry": "Config. Entry",
        "server": "Server",
        "port": "Port",
        "uuid": "UUID",
        "sni": "SNI",
        "public_key": "Public key",
        "short_id": "Short ID",
        "fingerprint": "Fingerprint",
        "security": "Security",
        "network": "Network",
        "transport_path": "Path",
        "host": "Host",
        "flow": "Flow",
        "about": "About",
        "save": "Save",
        "cancel": "Cancel",
        "close": "Close",
        "no_config": "No Config. Found",
        "invalid_config": "Invalid VLESS configuration.",
        "unsupported_config": "Only VLESS links are supported.",
        "config_saved": "Configuration saved.",
        "ping_ok": "Configuration server is reachable.",
        "ping_failed": "Configuration server is not reachable.",
        "missing": "e2xray control file was not found.",
        "save_error": "Could not save configuration: %s",
        "version": "Plugin version",
    },
    "fa": {
        "internet": "وضعیت اینترنت",
        "checking": "در حال بررسی",
        "online": "آنلاین",
        "offline": "آفلاین",
        "national": "اینترنت ملی",
        "start": "شروع",
        "stop": "توقف",
        "ping": "پینگ",
        "settings": "تنظیمات",
        "language": "زبان",
        "config_entry": "ورود کانفیگ",
        "server": "سرور",
        "port": "پورت",
        "uuid": "UUID",
        "sni": "SNI",
        "public_key": "کلید عمومی",
        "short_id": "شناسه کوتاه",
        "fingerprint": "اثر انگشت",
        "security": "امنیت",
        "network": "شبکه",
        "transport_path": "مسیر",
        "host": "میزبان",
        "flow": "Flow",
        "about": "درباره",
        "save": "ذخیره",
        "cancel": "انصراف",
        "close": "خروج",
        "no_config": "کانفیگی پیدا نشد",
        "invalid_config": "کانفیگ VLESS معتبر نیست.",
        "unsupported_config": "فقط لینک VLESS پشتیبانی می‌شود.",
        "config_saved": "کانفیگ ذخیره شد.",
        "ping_ok": "سرور کانفیگ در دسترس است.",
        "ping_failed": "سرور کانفیگ در دسترس نیست.",
        "missing": "فایل کنترل e2xray پیدا نشد.",
        "save_error": "کانفیگ ذخیره نشد: %s",
        "version": "نسخه پلاگین",
    },
    "ar": {
        "internet": "حالة الإنترنت",
        "checking": "جار الفحص",
        "online": "متصل",
        "offline": "غير متصل",
        "national": "إنترنت محلي",
        "start": "تشغيل",
        "stop": "إيقاف",
        "ping": "اختبار",
        "settings": "الإعدادات",
        "language": "اللغة",
        "config_entry": "إدخال الإعداد",
        "server": "الخادم",
        "port": "المنفذ",
        "uuid": "UUID",
        "sni": "SNI",
        "public_key": "المفتاح العام",
        "short_id": "المعرف القصير",
        "fingerprint": "البصمة",
        "security": "الأمان",
        "network": "الشبكة",
        "transport_path": "المسار",
        "host": "المضيف",
        "flow": "Flow",
        "about": "حول",
        "save": "حفظ",
        "cancel": "إلغاء",
        "close": "إغلاق",
        "no_config": "لم يتم العثور على إعداد",
        "invalid_config": "إعداد VLESS غير صالح.",
        "unsupported_config": "روابط VLESS فقط مدعومة.",
        "config_saved": "تم حفظ الإعداد.",
        "ping_ok": "خادم الإعداد متاح.",
        "ping_failed": "خادم الإعداد غير متاح.",
        "missing": "لم يتم العثور على ملف التحكم e2xray.",
        "save_error": "تعذر حفظ الإعداد: %s",
        "version": "إصدار الإضافة",
    },
}


def tr(key):
    language = config.plugins.e2xray.ui_language.value
    return TEXT.get(language, TEXT["en"]).get(key, key)


def connectSignal(signal, callback):
    if hasattr(signal, "connect"):
        return signal.connect(callback)
    if hasattr(signal, "get"):
        signal.get().append(callback)
        return None
    signal.append(callback)
    return None


def queryValue(values, key, default=""):
    result = values.get(key, [])
    if not result:
        return default
    return unquote(result[0])


def parseVlessEntry(value):
    entry = value.strip()
    if not entry:
        raise ValueError("empty")
    if not entry.lower().startswith("vless://"):
        raise TypeError("unsupported")

    parsed = urlsplit(entry)
    uuid = unquote(parsed.username or "")
    address = parsed.hostname or ""
    try:
        port = parsed.port or 443
    except ValueError:
        raise ValueError("port")
    query = parse_qs(parsed.query)
    security = queryValue(query, "security", "none").lower()
    network = queryValue(query, "type", "tcp").lower()

    if not uuid or not address or port < 1 or port > 65535:
        raise ValueError("required")
    if security not in ("none", "tls", "reality"):
        raise ValueError("security")
    if network not in ("tcp", "ws", "grpc"):
        raise ValueError("network")

    values = {
        "SERVER_ADDRESS": address,
        "SERVER_PORT": str(port),
        "UUID": uuid,
        "SNI": queryValue(query, "sni", queryValue(query, "serverName", address)),
        "PUBLIC_KEY": queryValue(query, "pbk", queryValue(query, "publicKey", "")),
        "SHORT_ID": queryValue(query, "sid", queryValue(query, "shortId", "")),
        "FINGERPRINT": queryValue(query, "fp", "chrome"),
        "SECURITY": security,
        "NETWORK": network,
        "TRANSPORT_PATH": queryValue(
            query, "path", queryValue(query, "serviceName", "")
        ),
        "HOST": queryValue(query, "host", ""),
        "FLOW": queryValue(query, "flow", ""),
    }
    for item in values.values():
        if "\n" in item or "\r" in item or '"' in item:
            raise ValueError("characters")
    return values


def shellQuote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def writeServerConf(values):
    order = [
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
    ]
    lines = ["# Written by e2xray."]
    for key in order:
        lines.append("%s=%s" % (key, shellQuote(values.get(key, ""))))
    output = open(USERCONF, "w")
    try:
        output.write("\n".join(lines) + "\n")
    finally:
        output.close()


def configSettingMap():
    return {
        "SERVER_ADDRESS": config.plugins.e2xray.server,
        "SERVER_PORT": config.plugins.e2xray.port,
        "UUID": config.plugins.e2xray.uuid,
        "SNI": config.plugins.e2xray.sni,
        "PUBLIC_KEY": config.plugins.e2xray.public_key,
        "SHORT_ID": config.plugins.e2xray.short_id,
        "FINGERPRINT": config.plugins.e2xray.fingerprint,
        "SECURITY": config.plugins.e2xray.security,
        "NETWORK": config.plugins.e2xray.network,
        "TRANSPORT_PATH": config.plugins.e2xray.path,
        "HOST": config.plugins.e2xray.host,
        "FLOW": config.plugins.e2xray.flow,
    }


def applyParsedConfig(values):
    for key, setting in configSettingMap().items():
        setting.value = values[key]


def manualConfigValues():
    values = {}
    for key, setting in configSettingMap().items():
        values[key] = str(setting.value).strip()

    try:
        port = int(values["SERVER_PORT"])
    except ValueError:
        raise ValueError("port")
    if (
        not values["SERVER_ADDRESS"]
        or not values["UUID"]
        or port < 1
        or port > 65535
    ):
        raise ValueError("required")
    if values["SECURITY"] not in ("none", "tls", "reality"):
        raise ValueError("security")
    if values["NETWORK"] not in ("tcp", "ws", "grpc"):
        raise ValueError("network")
    for item in values.values():
        if "\n" in item or "\r" in item or '"' in item:
            raise ValueError("characters")
    values["SERVER_PORT"] = str(port)
    return values


def saveParsedConfig(values):
    applyParsedConfig(values)
    for setting in configSettingMap().values():
        setting.save()
    writeServerConf(values)


class E2XrayMain(Screen):
    skin = """
    <screen name="E2XrayMain" position="center,center" size="760,330" title="e2xray">
        <widget name="internet_label" position="85,55" size="235,42" font="Regular;26" />
        <widget name="lamp" position="330,57" size="38,38" font="Regular;32" />
        <widget name="internet_msg" position="385,55" size="290,42" font="Regular;26" />
        <widget name="key_red" position="35,265" size="150,38" font="Regular;22" foregroundColor="red" halign="center" />
        <widget name="key_green" position="205,265" size="150,38" font="Regular;22" foregroundColor="green" halign="center" />
        <widget name="key_yellow" position="375,265" size="150,38" font="Regular;22" foregroundColor="yellow" halign="center" />
        <widget name="key_blue" position="545,265" size="180,38" font="Regular;22" foregroundColor="blue" halign="center" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.container = eConsoleAppContainer()
        self.signal_connections = [
            connectSignal(self.container.appClosed, self.commandDone),
            connectSignal(self.container.dataAvail, self.commandOutput),
        ]
        self.output = ""
        self.current_action = None
        self.internet_state = "checking"
        self["internet_label"] = Label("")
        self["lamp"] = Label("●")
        self["internet_msg"] = Label("")
        self["key_red"] = Label("")
        self["key_green"] = Label("")
        self["key_yellow"] = Label("")
        self["key_blue"] = Label("")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {
                "cancel": self.close,
                "green": self.start,
                "red": self.stop,
                "yellow": self.ping,
                "blue": self.settings,
            },
            -1,
        )
        self.onLayoutFinish.append(self.firstRun)

    def firstRun(self):
        self.refreshText()
        self.runCtl("internet", "internet")

    def refreshText(self):
        self["internet_label"].setText(tr("internet"))
        self["internet_msg"].setText(tr(self.internet_state))
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

    def commandDone(self, retval):
        output = self.output
        action = self.current_action
        self.output = ""
        self.current_action = None

        if "E2XRAY_NET=ONLINE" in output:
            self.setInternet("online", "green")
        elif "E2XRAY_NET=NATIONAL" in output:
            self.setInternet("national", "yellow")
        elif "E2XRAY_NET=OFFLINE" in output:
            self.setInternet("offline", "red")

        if action == "ping":
            if "E2XRAY_CONFIG_PING=NO_CONFIG" in output:
                self.session.open(MessageBox, tr("no_config"), MessageBox.TYPE_ERROR, timeout=7)
            elif "E2XRAY_CONFIG_PING=OK" in output:
                self.session.open(MessageBox, tr("ping_ok"), MessageBox.TYPE_INFO, timeout=7)
            else:
                self.session.open(MessageBox, tr("ping_failed"), MessageBox.TYPE_ERROR, timeout=7)
        elif action == "start" and "E2XRAY_ERROR=NO_CONFIG" in output:
            self.session.open(MessageBox, tr("no_config"), MessageBox.TYPE_ERROR, timeout=7)

    def setInternet(self, state, color):
        colors = {"green": "00cc44", "yellow": "ffd000", "red": "ff3030"}
        self.internet_state = state
        self["lamp"].setText("●")
        try:
            self["lamp"].instance.setForegroundColor(parseColor("#" + colors[color]))
        except Exception:
            pass
        self["internet_msg"].setText(tr(state))

    def runCtl(self, argument, action):
        if not fileExists(CTL):
            self.session.open(MessageBox, tr("missing"), MessageBox.TYPE_ERROR, timeout=8)
            return
        self.output = ""
        self.current_action = action
        self.container.execute("%s %s" % (CTL, argument))

    def start(self):
        self.runCtl("start", "start")

    def stop(self):
        self.runCtl("stop", "stop")

    def ping(self):
        self.runCtl("ping", "ping")

    def settings(self):
        self.session.openWithCallback(self.settingsClosed, E2XraySettingsMenu)

    def settingsClosed(self, *args):
        self.refreshText()
        self.runCtl("internet", "internet")


class E2XraySettingsMenu(Screen):
    skin = """
    <screen name="E2XraySettingsMenu" position="center,center" size="650,390" title="e2xray">
        <widget name="menu" position="30,35" size="590,270" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="35,330" size="170,38" font="Regular;22" foregroundColor="red" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.labels = [tr("language"), tr("config_entry"), tr("about")]
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
                "left": self["menu"].pageUp,
                "right": self["menu"].pageDown,
            },
            -1,
        )

    def openSelected(self):
        current = self["menu"].getCurrent()
        if current == self.labels[0]:
            self.session.openWithCallback(self.refresh, E2XrayLanguage)
        elif current == self.labels[1]:
            self.session.open(E2XrayConfigEntry)
        elif current == self.labels[2]:
            self.session.open(E2XrayAbout)

    def refresh(self, *args):
        self.labels = [tr("language"), tr("config_entry"), tr("about")]
        self["menu"].setList(self.labels)
        self["key_red"].setText(tr("close"))


class E2XrayLanguage(Screen, ConfigListScreen):
    skin = """
    <screen name="E2XrayLanguage" position="center,center" size="680,280" title="e2xray">
        <widget name="config" position="60,35" size="440,145" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="60,215" size="170,38" font="Regular;22" foregroundColor="red" />
        <widget name="key_green" position="450,215" size="170,38" font="Regular;22" foregroundColor="green" halign="right" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.list = [getConfigListEntry(tr("language"), config.plugins.e2xray.ui_language)]
        ConfigListScreen.__init__(self, self.list, session=session)
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


class E2XrayConfigEntry(Screen, ConfigListScreen):
    skin = """
    <screen name="E2XrayConfigEntry" position="center,center" size="780,640" title="e2xray">
        <widget name="config" position="55,30" size="650,510" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="60,575" size="170,38" font="Regular;22" foregroundColor="red" />
        <widget name="key_green" position="550,575" size="170,38" font="Regular;22" foregroundColor="green" halign="right" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.entry = config.plugins.e2xray.config_entry
        self.settings = [
            self.entry,
            config.plugins.e2xray.server,
            config.plugins.e2xray.port,
            config.plugins.e2xray.uuid,
            config.plugins.e2xray.sni,
            config.plugins.e2xray.public_key,
            config.plugins.e2xray.short_id,
            config.plugins.e2xray.fingerprint,
            config.plugins.e2xray.security,
            config.plugins.e2xray.network,
            config.plugins.e2xray.path,
            config.plugins.e2xray.host,
            config.plugins.e2xray.flow,
        ]
        self.list = [
            getConfigListEntry(tr("config_entry"), self.entry),
            getConfigListEntry(tr("server"), config.plugins.e2xray.server),
            getConfigListEntry(tr("port"), config.plugins.e2xray.port),
            getConfigListEntry(tr("uuid"), config.plugins.e2xray.uuid),
            getConfigListEntry(tr("sni"), config.plugins.e2xray.sni),
            getConfigListEntry(tr("public_key"), config.plugins.e2xray.public_key),
            getConfigListEntry(tr("short_id"), config.plugins.e2xray.short_id),
            getConfigListEntry(tr("fingerprint"), config.plugins.e2xray.fingerprint),
            getConfigListEntry(tr("security"), config.plugins.e2xray.security),
            getConfigListEntry(tr("network"), config.plugins.e2xray.network),
            getConfigListEntry(tr("transport_path"), config.plugins.e2xray.path),
            getConfigListEntry(tr("host"), config.plugins.e2xray.host),
            getConfigListEntry(tr("flow"), config.plugins.e2xray.flow),
        ]
        self.active_setting = None
        ConfigListScreen.__init__(self, self.list, session=session)
        self["key_red"] = Label(tr("cancel"))
        self["key_green"] = Label(tr("save"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {
                "cancel": self.cancel,
                "red": self.cancel,
                "green": self.save,
                "ok": self.openKeyboard,
            },
            -1,
        )

    def openKeyboard(self):
        current = self["config"].getCurrent()
        if not current or len(current) < 2:
            return
        setting = current[1]
        if not isinstance(setting, ConfigText):
            return
        self.active_setting = setting
        self.session.openWithCallback(
            self.keyboardClosed,
            VirtualKeyBoard,
            title=current[0],
            text=setting.value,
        )

    def keyboardClosed(self, value):
        setting = self.active_setting
        self.active_setting = None
        if value is None or setting is None:
            return
        setting.value = value.strip()
        if setting is self.entry and setting.value:
            try:
                applyParsedConfig(parseVlessEntry(setting.value))
            except TypeError:
                self.session.open(
                    MessageBox,
                    tr("unsupported_config"),
                    MessageBox.TYPE_ERROR,
                    timeout=8,
                )
            except ValueError:
                self.session.open(
                    MessageBox,
                    tr("invalid_config"),
                    MessageBox.TYPE_ERROR,
                    timeout=8,
                )
        try:
            self["config"].invalidateCurrent()
        except Exception:
            pass

    def save(self):
        try:
            values = manualConfigValues()
            saveParsedConfig(values)
            self.entry.save()
            configfile.save()
        except ValueError:
            self.session.open(MessageBox, tr("invalid_config"), MessageBox.TYPE_ERROR, timeout=8)
            return
        except Exception as error:
            self.session.open(
                MessageBox,
                tr("save_error") % error,
                MessageBox.TYPE_ERROR,
                timeout=8,
            )
            return
        self.session.openWithCallback(
            self.savedMessageClosed,
            MessageBox,
            tr("config_saved"),
            MessageBox.TYPE_INFO,
            timeout=5,
        )

    def savedMessageClosed(self, *args):
        self.close(True)

    def cancel(self):
        for setting in self.settings:
            setting.cancel()
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
