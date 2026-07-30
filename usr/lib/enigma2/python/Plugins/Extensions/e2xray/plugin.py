# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import os

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
from .proxy_config import as_text, parse_share_link

PLUGIN_NAME = "e2xray"
PLUGIN_DESCRIPTION = "Xray Client for Enigma2"
BASE = "/usr/lib/enigma2/python/Plugins/Extensions/e2xray"
CTL = BASE + "/e2xrayctl.sh"
USERCONF = "/root/config.txt"

config.plugins.e2xray = ConfigSubsection()
config.plugins.e2xray.ui_language = ConfigSelection(
    default="en",
    choices=[("en", "English"), ("fa", "فارسی"), ("ar", "العربية")],
)
config.plugins.e2xray.config_entry = ConfigText(default="", fixed_size=False)

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
        "about": "About",
        "save": "Save",
        "cancel": "Cancel",
        "close": "Close",
        "no_config": "No Config. Found",
        "invalid_config": "Invalid proxy configuration.",
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
        "about": "درباره",
        "save": "ذخیره",
        "cancel": "انصراف",
        "close": "خروج",
        "no_config": "کانفیگی پیدا نشد",
        "invalid_config": "کانفیگ پراکسی معتبر نیست.",
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
        "about": "حول",
        "save": "حفظ",
        "cancel": "إلغاء",
        "close": "إغلاق",
        "no_config": "لم يتم العثور على إعداد",
        "invalid_config": "إعداد البروكسي غير صالح.",
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


def writeShareLink(entry):
    with io.open(USERCONF, "w", encoding="utf-8") as output:
        output.write(as_text(entry) + u"\n")
    try:
        os.chmod(USERCONF, 0o600)
    except OSError:
        pass


def readShareLink():
    try:
        with io.open(USERCONF, "r", encoding="utf-8-sig") as source:
            for line in source:
                entry = line.strip()
                if entry and not entry.startswith("#"):
                    parse_share_link(entry)
                    return entry
    except (IOError, OSError, ValueError):
        pass
    return ""


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


class E2XrayConfigEntry(Screen, ConfigListScreen):
    skin = """
    <screen name="E2XrayConfigEntry" position="center,center" size="780,280" title="e2xray">
        <widget name="config" position="40,35" size="700,145" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="60,215" size="170,38" font="Regular;22" foregroundColor="red" />
        <widget name="key_green" position="550,215" size="170,38" font="Regular;22" foregroundColor="green" halign="right" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.entry = config.plugins.e2xray.config_entry
        self.entry.value = readShareLink()
        self.list = [getConfigListEntry(tr("config_entry"), self.entry)]
        self.active_setting = None
        ConfigListScreen.__init__(self, self.list, session=session)
        try:
            self["config"].l.setSeperation(210)
        except Exception:
            pass
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
        if setting.value:
            try:
                parse_share_link(setting.value)
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
            entry = self.entry.value.strip()
            if not entry:
                raise ValueError("empty")
            parse_share_link(entry)
            writeShareLink(entry)
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
        self.entry.cancel()
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
