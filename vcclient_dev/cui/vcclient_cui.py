from __future__ import annotations

import logging
from pathlib import Path, PurePath
from typing import Callable, List

from rich.syntax import Syntax
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import ScrollableContainer
from textual.driver import Driver
from textual.widgets import Header, RichLog, TabbedContent, TabPane
from watchdog.events import FileSystemEvent

from ..const import APP_NAME, LOG_FILE, LOGGER_NAME, VERSION
from ..server.server_const import get_frontend_path
from ..voice_changer.voice_chanager_const import EventSource, ModelDir, SettingsDir
from ..voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from .utils.shortcut_setting import ShortcutList
from .utils.watchdog import VCClientFileEventHandler, VCClientFileWatcher
from .widget.custom_footer import CustomFooter
from .widget.main_panel import MainPanel


def load_shortcut_settings():
    shortcuts = [
        {"command": "ctrl+c", "function": "dummy", "description": "NOOP", "show": False},
        {"command": "q", "function": "quit_server", "description": "Quit", "show": True},
        {"command": "ctrl+r", "function": "reload_log", "description": "reload log", "show": True},
    ]
    shortcut_setting = ShortcutList(shortcuts=shortcuts)
    return [
        Binding(
            b.command,
            b.function,
            b.description,
            show=b.show,
        )
        for b in shortcut_setting.shortcuts
    ]


class VCClientCommands(Provider):
    async def search(self, query: str) -> Hits:
        app = self.app
        if isinstance(app, VCClientCUI):
            yield Hit(
                1,
                "quit",
                app.action_quit_server,
                help="quit",
            )


class VCClientCUI(App):
    BINDINGS = load_shortcut_settings()
    COMMANDS = {VCClientCommands}

    def __init__(
        self,
        driver_class: type[Driver] | None = None,
        css_path: str | PurePath | List[str | PurePath] | None = None,
        watch_css: bool = False,
        port: int | None = None,
        https: bool | None = None,
        terminate_callback: Callable | None = None,
    ):
        super().__init__(driver_class, css_path, watch_css)
        logger = logging.getLogger(LOGGER_NAME)
        logger.info("Starting VCClient CUI")
        logger.info(f"port: {port}, https: {https}")

        self.port = port
        self.https = https
        self.terminate_callback = terminate_callback

        def event_callback(source: EventSource, event: FileSystemEvent):
            pass

        self.w = VCClientFileWatcher(
            [Path(SettingsDir), Path(ModelDir)],
            VCClientFileEventHandler(event_callback),
        )

    def compose(self) -> ComposeResult:
        header = Header(show_clock=True)
        header.app.title = f"{APP_NAME} ver.{VERSION}"
        yield header
        yield CustomFooter()

        with TabbedContent(initial="main_tab", id="tab_container"):
            with TabPane("Main", id="main_tab"):
                yield ScrollableContainer(MainPanel(port=self.port, https=self.https))
            with TabPane("Log", id="log_tab"):
                yield RichLog(highlight=True, markup=True, id="log")
            with TabPane("licenses(python)", id="licenses_py_tab"):
                yield RichLog(highlight=True, markup=True, id="licenses_py")
            with TabPane("licenses(js)", id="licenses_js_tab"):
                yield RichLog(highlight=True, markup=True, id="licenses_js")

    def on_ready(self) -> None:
        """Called when the DOM is ready."""
        try:
            licenses_py = self.query_one("#licenses_py")
            license_py_path = Path(get_frontend_path()) / "licenses-py.json"
            if license_py_path.exists():
                with open(license_py_path, "r", encoding="utf-8") as f:
                    licenses = f.read()
                if isinstance(licenses_py, RichLog):
                    licenses_py.write(Syntax(licenses, "json", line_numbers=True))
        except Exception:
            pass

        try:
            licenses_js = self.query_one("#licenses_js")
            license_js_path = Path(get_frontend_path()) / "licenses-js.json"
            if license_js_path.exists():
                with open(license_js_path, "r", encoding="utf-8") as f:
                    licenses = f.read()
                if isinstance(licenses_js, RichLog):
                    licenses_js.write(Syntax(licenses, "json", line_numbers=True))
        except Exception:
            pass

    def action_reload_log(self) -> None:
        try:
            text_log = self.query_one("#log")
            if isinstance(text_log, RichLog):
                text_log.clear()
                if Path(LOG_FILE).exists():
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        logdata = f.read()
                    text_log.write(logdata)
        except Exception:
            pass

    def action_quit_server(self) -> None:
        assert self.terminate_callback is not None
        self.terminate_callback()
        vc = LocalVoiceChangerInterface.get_instance()
        vc.stop()
        if hasattr(self, "w") and self.w:
            self.w.stop()
        self.exit()
