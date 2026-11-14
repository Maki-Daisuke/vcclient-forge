import io
import sys
from unittest.mock import MagicMock

import pytest

from vcclient import initializer
from vcclient.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient.voice_changer.data_types.sample_manager_data_types import SampleDownloadStatus


@pytest.mark.parametrize("kind", ["modules", "samples"])
def test_download_progress_supports_cp932_stdout(kind, monkeypatch):
    output = io.BytesIO()
    stdout = io.TextIOWrapper(output, encoding="cp932", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", stdout)

    if kind == "modules":
        monkeypatch.setattr(initializer, "is_rvc_ready", lambda: False)
        monkeypatch.setattr(
            initializer,
            "download_rvc_modules",
            lambda callback: callback([ModuleDownloadStatus(id="test.onnx", status="done", progress=1.0)]),
        )
        initializer._check_and_download_rvc_modules()
    else:
        slot_manager = MagicMock()
        slot_manager.get_slot_infos.return_value = []
        monkeypatch.setattr(initializer.SlotManager, "get_instance", lambda: slot_manager)
        monkeypatch.setattr(
            initializer,
            "download_initial_samples",
            lambda callback: callback([SampleDownloadStatus(id="test_o", status="done", progress=1.0)]),
        )
        initializer._check_and_download_initial_samples()

    assert "test" in output.getvalue().decode("cp932")
    assert "100% [OK]" in output.getvalue().decode("cp932")


def test_download_progress_renders_and_updates_individual_rows(capsys):
    render = initializer._download_progress(lambda name: name)
    render(
        [
            SampleDownloadStatus(id="first", status="processing", progress=0.5),
            SampleDownloadStatus(id="second", status="processing", progress=0.25),
        ]
    )
    initial = capsys.readouterr().out
    assert "first" in initial and " 50%" in initial
    assert "second" in initial and " 25%" in initial

    render(
        [
            SampleDownloadStatus(id="first", status="done", progress=1.0),
            SampleDownloadStatus(id="second", status="error", progress=1.0),
        ]
    )
    updated = capsys.readouterr().out
    assert updated.startswith("\x1b[2A")
    assert "100% [OK]" in updated
    assert "100% [ERROR]" in updated


def test_download_progress_displays_long_model_name(capsys):
    render = initializer._download_progress(lambda name: name)
    render([SampleDownloadStatus(id="a-very-long-model-name", status="validating", progress=1.0)])
    line = capsys.readouterr().out.removeprefix("\r\x1b[2K").rstrip("\n")
    assert "a-very-long-model-name" in line
    assert "[====================]" in line
    assert line.endswith("100% [VERIFY]")
