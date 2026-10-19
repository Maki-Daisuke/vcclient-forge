from io import StringIO
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from vcclient.utils.desktop_control import start_desktop_control, watch_desktop_input


@pytest.mark.parametrize("commands", ["shutdown\n", "", "unknown\nshutdown\n", "unknown\n"])
def test_desktop_control_requests_shutdown(commands: str) -> None:
    requests: list[bool] = []
    watch_desktop_input(StringIO(commands), lambda: requests.append(True))
    assert requests == [True]


def test_desktop_control_runs_on_daemon_thread() -> None:
    requested = Event()
    thread = start_desktop_control(StringIO("shutdown\n"), requested.set)
    thread.join(timeout=1)
    assert requested.is_set()
    assert thread.daemon
    assert not thread.is_alive()


@pytest.mark.parametrize("started, alive", [(True, True), (False, False), (False, True)])
def test_desktop_readiness_requires_own_running_server(
    monkeypatch: pytest.MonkeyPatch, started: bool, alive: bool
) -> None:
    import main as entrypoint

    monkeypatch.setattr(entrypoint.AppStatus, "_instance", SimpleNamespace(end_flag=False))
    server = SimpleNamespace(server=SimpleNamespace(started=started), server_thread=Mock())
    server.server_thread.is_alive.return_value = alive
    if started:
        entrypoint.wait_for_desktop_server(server, timeout=0)
    elif alive:
        with pytest.raises(TimeoutError):
            entrypoint.wait_for_desktop_server(server, timeout=0)
    else:
        with pytest.raises(RuntimeError, match="port"):
            entrypoint.wait_for_desktop_server(server, timeout=0)


def test_desktop_readiness_can_be_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    import main as entrypoint

    monkeypatch.setattr(entrypoint.AppStatus, "_instance", SimpleNamespace(end_flag=True))
    server = SimpleNamespace(server=SimpleNamespace(started=False), server_thread=Mock())
    with pytest.raises(RuntimeError, match="cancelled"):
        entrypoint.wait_for_desktop_server(server)


@pytest.mark.parametrize("monitor_index", [-1, 2])
def test_desktop_shutdown_closes_active_audio_streams(monkeypatch: pytest.MonkeyPatch, monitor_index: int) -> None:
    from vcclient.voice_changer.voice_change_manager import local_voice_changer_interface as audio

    app_status = SimpleNamespace(end_flag=False)
    configuration = SimpleNamespace(
        audio_input_device_index=0, audio_output_device_index=1, audio_monitor_device_index=monitor_index
    )
    manager = Mock()
    manager.get_voice_changer_configuration.return_value = configuration
    monkeypatch.setattr(audio.ConfigurationManager, "_instance", manager)
    monkeypatch.setattr(audio.AppStatus, "_instance", app_status)
    stream = MagicMock()
    stream.__enter__.return_value = SimpleNamespace(samplerate=48000, channels=1, dtype="float32")
    monkeypatch.setattr(audio.sd, "InputStream", Mock(return_value=stream))
    monkeypatch.setattr(audio.sd, "OutputStream", Mock(return_value=stream))

    def request_shutdown(interval: float) -> None:
        assert not app_status.end_flag, "Audio loop ignored the shutdown request"
        app_status.end_flag = True

    monkeypatch.setattr(audio.time, "sleep", request_shutdown)
    interface = audio.LocalVoiceChangerInterface()
    interface.local_voice_changer_enabled = True
    for direction in ("input", "output", "monitor"):
        monkeypatch.setattr(interface, f"audio_{direction}_device_sample_rate", 48000, raising=False)
        monkeypatch.setattr(interface, f"{direction}_block_size", 480, raising=False)
        monkeypatch.setattr(interface, f"{direction}_extra_settings", None, raising=False)

    interface.launch_converter()

    assert interface.local_voice_changer_enabled
    assert stream.__exit__.call_count == (2 if monitor_index == -1 else 3)
