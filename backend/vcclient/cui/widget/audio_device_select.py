from __future__ import annotations

from pydantic import BaseModel
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.keys import Keys
from textual.screen import Screen
from textual.widgets import Button, Label, RadioButton, RadioSet, Select

from ...voice_changer.auido_device_manager.audio_device_manager import AudioDeviceManager
from ...voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from ...voice_changer.voice_chanager_const import AudioDevicePurpose, AudioSampleRates


class SelectedAudioDevice(BaseModel):
    device_id: int
    sample_rate: int


class AudioDeviceSelect(Screen):
    DEFAULT_CSS = """
        AudioDeviceSelect{
            layout: grid;
            grid-size: 2 8;
            .select_audio_device_title {
                background: blue;
                column-span: 2;
                width: 1fr;
            }
            .audio_device_list{
                border: solid $success;
                border_title_align: left;
                overflow_x: hidden;
                column-span: 2;
                row-span: 5;
                width: 1fr;
            }
            .sample-rate-area{
                padding: 0 10 0 10;
                border: none;
                overflow_x: hidden;
                column-span: 2;
                width: 1fr;
            }
            .button-area{
                align: center bottom;
            }
        }
    """

    BINDINGS = [(Keys.Escape, "cancelation", "cancel")]

    def __init__(self, purpose: AudioDevicePurpose):
        super().__init__()
        self.purpose = purpose
        self.device_list = AudioDeviceManager.get_instance().get_audio_device_list(self.purpose)
        self.temporal_configuration = self._get_current_configuration()

    def _get_current_configuration(self):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        if self.purpose == AudioDevicePurpose.audio_input:
            return SelectedAudioDevice(
                device_id=conf.audio_input_device_index, sample_rate=conf.audio_input_device_sample_rate
            )
        elif self.purpose == AudioDevicePurpose.audio_output:
            return SelectedAudioDevice(
                device_id=conf.audio_output_device_index, sample_rate=conf.audio_output_device_sample_rate
            )
        elif self.purpose == AudioDevicePurpose.audio_monitor:
            return SelectedAudioDevice(
                device_id=conf.audio_monitor_device_index, sample_rate=conf.audio_monitor_device_sample_rate
            )
        raise ValueError(f"Unknown purpose: {self.purpose}")

    def _reload_current_to_temporal_configuration(self):
        self.temporal_configuration = self._get_current_configuration()

    def compose(self) -> ComposeResult:
        yield Label(f"Select Audio Device: {self.purpose.value}", classes="select_audio_device_title")
        with ScrollableContainer(classes="audio_device_list"):
            with RadioSet(id="radio_set"):
                for dev in self.device_list:
                    yield RadioButton(
                        f"{dev.index}: {dev.name}",
                        value=dev.index == self.temporal_configuration.device_id,
                        id=f"dev_{dev.index}",
                    )
        with Container(classes="sample-rate-area"):
            yield Label("Sample Rate:")
            rates = [(str(r), r) for r in AudioSampleRates]
            yield Select(rates, value=self.temporal_configuration.sample_rate, id="sample_rate_select")
        with Horizontal(classes="button-area"):
            yield Button("OK", variant="primary", id="ok_button")
            yield Button("Cancel", id="cancel_button")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.pressed and event.pressed.id:
            dev_idx = int(event.pressed.id.replace("dev_", ""))
            self.temporal_configuration.device_id = dev_idx

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self.temporal_configuration.sample_rate = int(event.value)

    @on(Button.Pressed, "#cancel_button")
    def on_cancel_button_pressed(self, event: Button.Pressed) -> None:
        self.cancelation()

    @on(Button.Pressed, "#ok_button")
    def on_ok_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self.temporal_configuration)

    def initialize(self) -> None:
        self._reload_current_to_temporal_configuration()

    def cancelation(self) -> None:
        self.dismiss(None)

    def action_cancelation(self) -> None:
        self.cancelation()
