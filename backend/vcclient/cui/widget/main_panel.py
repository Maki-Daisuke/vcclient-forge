from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Static

from vcclient.utils.resolve_url import resolve_base_url
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


class MainPanel(Static):
    DEFAULT_CSS = "\n    MainPanel{\n        .main-control{\n            height:auto;\n            border: solid #ddffdd;\n            border-title-color: $success;\n            .row{\n                height: 1;\n                .name{\n                    width:1fr;\n                    min-width:10;\n                    height: auto;\n                    height: 1;\n                    margin-left:1;\n                    color:#aaffaa;\n                }\n                .sub-name{\n                    width:1fr;\n                    min-width:10;\n                    height: auto;\n                    height: 1;\n                    margin-left:1;\n                    # color:blue;\n                    color:#00aa00;\n                }\n                .value{\n                    width:3fr;\n                    height: 1;\n                    margin-left:1;\n                }\n                .value-note{\n                    width:3fr;\n                    height: 1;\n                    margin-left:1;\n                    color:#0000aa;\n                }\n            }\n        }\n\n        .field-name{\n            width:1fr;\n            margin-right:1;\n        }\n        .field-input{\n            width:2fr;\n            margin-right:1;\n            content-align: left middle;\n        }\n        .field-audio-device{\n            width:2fr;\n            margin-right:1;\n            content-align: left middle;\n        }\n        .field-audio-slider{\n            width:4fr;\n            margin-right:1;\n            content-align: left middle;\n        }\n        .field-noise-gate-slider{\n            width:2fr;\n            margin-right:1;\n            content-align: left middle;\n        }\n\n        .field-button{\n            width:5;\n            margin-right:1;\n        }\n        .field-button.active{\n            background: $success;\n        }\n\n        .field-noise-suppression-button{\n            width:10;\n            min-width:5;\n            margin-right:1;\n        }\n\n        .clickable{\n            color: $warning;\n            link-color: dodgerblue 90%;\n            # link-background: dodgerblue;\n            # link-style: bold italic underline\n            link-style: underline;\n        }\n        .hidden{\n            display: none;\n        }\n    }\n    "

    def __init__(self, name=None, id=None, classes=None, disabled=None, port=None, https=None):
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.port = port
        self.https = https
        self.performance_elapsed_time_value = Label("-", classes="value")
        self.performance_input_size_value = Label("-", classes="value")
        self.performance_output_size_value = Label("-", classes="value")
        self.performance_input_volume_db_value = Label("-", classes="value")
        self.performance_output_volume_db_value = Label("-", classes="value")

        def on_performance_change(performance_data=None):
            self.performance_elapsed_time_value.update(f"""{performance_data.elapsed_time}""")
            self.performance_input_size_value.update(
                f"""{performance_data.input_size} / {performance_data.input_sec}"""
            )
            self.performance_output_size_value.update(
                f"""{performance_data.output_size} / {performance_data.output_sec}"""
            )
            self.performance_input_volume_db_value.update(f"""{performance_data.input_volume_db}""")
            self.performance_output_volume_db_value.update(f"""{performance_data.output_volume_db}""")

        VoiceChanger.get_instance().set_performance_listener(on_performance_change)

    def compose(self):
        base_url = resolve_base_url(self.https, self.port)
        launcher = Vertical(
            Horizontal(Label("Application", classes="name"), Label(f"""{base_url}""", classes="value"), classes="row"),
            Horizontal(
                Label("Log(rich)", classes="name"),
                Label(f"""{base_url}/?app_mode=LogViewer""", classes="value"),
                classes="row",
            ),
            Horizontal(
                Label("Log(plain)", classes="name"),
                Label(f"""{base_url}/vcclient.log""", classes="value"),
                classes="row",
            ),
            Horizontal(Label("API", classes="name"), Label(f"""{base_url}/docs""", classes="value"), classes="row"),
            Horizontal(
                Label("", classes="name"),
                Label("Note: API may be subject to change in the future.", classes="value-note"),
                classes="row",
            ),
            classes="main-control",
        )
        launcher.border_title = "URLs"
        yield launcher

        performance = Vertical(
            Horizontal(Label("Elapsed Time(sec)", classes="name"), self.performance_elapsed_time_value, classes="row"),
            Horizontal(
                Label("Data / Sec", classes="name"),
                Label("in", classes="sub-name"),
                self.performance_input_size_value,
                Label("out", classes="sub-name"),
                self.performance_output_size_value,
                classes="row",
            ),
            Horizontal(
                Label("Vol(db)", classes="name"),
                Label("in", classes="sub-name"),
                self.performance_input_volume_db_value,
                Label("out", classes="sub-name"),
                self.performance_output_volume_db_value,
                classes="row",
            ),
            classes="main-control",
        )
        performance.border_title = "Performance"
        yield performance
