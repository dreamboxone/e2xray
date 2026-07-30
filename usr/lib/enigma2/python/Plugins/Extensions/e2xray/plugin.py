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
    RT_VALIGN_CENTER,
    eConsoleAppContainer,
    eListboxPythonMultiContent,
    gFont,
)
from skin import parseColor
from . import PLUGIN_VERSION
from .proxy_config import (
    read_profiles,
    read_selection,
    select_profile,
    write_selection,
)

PLUGIN_NAME = "e2xray"
PLUGIN_DESCRIPTION = "Xray Client for Enigma2"
BASE = "/usr/lib/enigma2/python/Plugins/Extensions/e2xray"
CTL = BASE + "/e2xrayctl.sh"
USERCONF = "/root/config.txt"
SELECTION = "/etc/e2xray/selected"
PIDFILE = "/var/run/e2xray/xray.pid"
ACTIVE_PROFILE = "/var/run/e2xray/active_profile"

config.plugins.e2xray = ConfigSubsection()
config.plugins.e2xray.ui_language = ConfigSelection(
    default="en",
    choices=[("en", "English"), ("fa", "فارسی"), ("ar", "العربية")],
)

TEXT = {
    "en": {
        "internet": "Internet status",
        "checking": "Checking",
        "online": "Online",
        "offline": "Offline",
        "national": "National internet",
        "start": "Start",
        "stop": "Stop",
        "started": "Configuration started.",
        "stopped": "Proxy stopped.",
        "start_failed": "Could not start the configuration.",
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
        "invalid_config": "Invalid proxy configuration.",
        "stop_before_change": "Stop e2xray before changing configuration.",
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
        "started": "کانفیگ استارت شد",
        "stopped": "فیلترشکن متوقف شد",
        "start_failed": "کانفیگ استارت نشد",
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
        "invalid_config": "کانفیگ پراکسی معتبر نیست.",
        "stop_before_change": "پیش از تغییر کانفیگ، e2xray را متوقف کنید.",
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
        "started": "تم تشغيل الاتصال",
        "stopped": "تم إيقاف البروكسي",
        "start_failed": "تعذر تشغيل الاتصال",
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
        "invalid_config": "إعداد البروكسي غير صالح.",
        "stop_before_change": "أوقف e2xray قبل تغيير الاتصال.",
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


def connectSignal(signal, callback):
    if hasattr(signal, "connect"):
        return signal.connect(callback)
    if hasattr(signal, "get"):
        signal.get().append(callback)
        return None
    signal.append(callback)
    return None


def coreRunning():
    try:
        with open(PIDFILE, "r") as source:
            pid = int(source.readline().strip())
        os.kill(pid, 0)
        return True
    except (IOError, OSError, TypeError, ValueError):
        return False


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
                505,
                42,
                0,
                RT_HALIGN_LEFT | RT_VALIGN_CENTER,
                name,
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
        <widget name="internet_label" position="85,40" size="235,42" font="Regular;26" />
        <widget name="lamp" position="330,42" size="38,38" font="Regular;32" />
        <widget name="internet_msg" position="385,40" size="290,42" font="Regular;26" />
        <widget name="configuration_label" position="85,105" size="590,38" font="Regular;24" />
        <widget name="profiles" position="85,148" size="590,252" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="35,455" size="150,38" font="Regular;22" foregroundColor="red" halign="center" />
        <widget name="key_green" position="205,455" size="150,38" font="Regular;22" foregroundColor="green" halign="center" />
        <widget name="key_yellow" position="375,455" size="150,38" font="Regular;22" foregroundColor="yellow" halign="center" />
        <widget name="key_blue" position="545,455" size="180,38" font="Regular;22" foregroundColor="blue" halign="center" />
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
        self.runCtl("internet", "internet")

    def refreshText(self):
        self["internet_label"].setText(tr("internet"))
        self["internet_msg"].setText(tr(self.internet_state))
        self["configuration_label"].setText(tr("configurations"))
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
        refresh_internet = False
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
        elif action == "start":
            if "E2XRAY_ERROR=NO_CONFIG" in output:
                self.session.open(
                    MessageBox,
                    tr("no_config"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
            elif retval == 0:
                self.session.open(
                    MessageBox,
                    tr("started"),
                    MessageBox.TYPE_INFO,
                    timeout=5,
                )
                refresh_internet = True
            else:
                self.session.open(
                    MessageBox,
                    tr("start_failed"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
        elif action == "stop":
            if retval == 0:
                self.session.open(
                    MessageBox,
                    tr("stopped"),
                    MessageBox.TYPE_INFO,
                    timeout=5,
                )
                refresh_internet = True
            else:
                self.session.open(
                    MessageBox,
                    tr("stop_failed"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
        if action in ("start", "stop"):
            self.reloadProfiles()
        if refresh_internet:
            self.runCtl("internet", "internet")

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

    def reloadProfiles(self, preferred_id=None):
        try:
            profiles = read_profiles(USERCONF)
            selected = select_profile(profiles, SELECTION)
            if read_selection(SELECTION) != selected["PROFILE_ID"]:
                write_selection(SELECTION, selected["PROFILE_ID"])
        except (IOError, OSError, ValueError):
            profiles = []
            selected = None

        active_id = activeProfileId()
        selected_id = selected["PROFILE_ID"] if selected else ""
        rows = []
        current_index = 0
        for index, profile in enumerate(profiles):
            row = dict(profile)
            if profile["PROFILE_ID"] == active_id:
                row["_MARK"] = u"✓"
            elif profile["PROFILE_ID"] == selected_id:
                row["_MARK"] = "X"
            else:
                row["_MARK"] = ""
            rows.append(row)
            target_id = preferred_id or selected_id
            if profile["PROFILE_ID"] == target_id:
                current_index = index

        if not rows:
            rows = [{"PROFILE_ID": "", "PROFILE_NAME": tr("no_config"), "_MARK": ""}]
        self["profiles"].setProfiles(rows, current_index)

    def currentProfile(self):
        profile = self["profiles"].getCurrent()
        if isinstance(profile, (list, tuple)) and profile:
            profile = profile[0]
        if not profile or not profile.get("PROFILE_ID"):
            return None
        return profile

    def chooseProfile(self, show_error=True):
        profile = self.currentProfile()
        if not profile:
            if show_error:
                self.session.open(
                    MessageBox,
                    tr("no_config"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
            return False
        active_id = activeProfileId()
        if active_id and active_id != profile["PROFILE_ID"]:
            if show_error:
                self.session.open(
                    MessageBox,
                    tr("stop_before_change"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
            self.reloadProfiles(active_id)
            return False
        try:
            write_selection(SELECTION, profile["PROFILE_ID"])
        except (IOError, OSError, ValueError):
            if show_error:
                self.session.open(
                    MessageBox,
                    tr("invalid_config"),
                    MessageBox.TYPE_ERROR,
                    timeout=7,
                )
            return False
        self.reloadProfiles(profile["PROFILE_ID"])
        return True

    def selectHighlighted(self):
        self.chooseProfile()

    def start(self):
        if self.chooseProfile():
            self.runCtl("start", "start")

    def stop(self):
        self.runCtl("stop", "stop")

    def ping(self):
        if self.chooseProfile():
            self.runCtl("ping", "ping")

    def settings(self):
        self.session.openWithCallback(self.settingsClosed, E2XraySettingsMenu)

    def settingsClosed(self, *args):
        self.reloadProfiles()
        self.refreshText()
        self.runCtl("internet", "internet")


class E2XraySettingsMenu(Screen):
    skin = """
    <screen name="E2XraySettingsMenu" position="center,center" size="650,320" title="e2xray">
        <widget name="menu" position="30,35" size="590,205" scrollbarMode="showOnDemand" />
        <widget name="key_red" position="35,260" size="170,38" font="Regular;22" foregroundColor="red" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.labels = [tr("language"), tr("about")]
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
        current = self["menu"].getCurrent()
        if current == self.labels[0]:
            self.session.openWithCallback(self.refresh, E2XrayLanguage)
        elif current == self.labels[1]:
            self.session.open(E2XrayAbout)

    def refresh(self, *args):
        self.labels = [tr("language"), tr("about")]
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
