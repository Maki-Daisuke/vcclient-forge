from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vcclient.exception import ERROR_CODE_MODULE_NOT_FOUND, VCClientError
from vcclient.voice_changer.data_types.data_types import ModuleInfo
from vcclient.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient.voice_changer.module_manager.module_manager import ModuleManager


def test_download_hash_mismatch_reports_error_and_removes_corrupt_file(tmp_path: Path, monkeypatch):
    """Verify that a hash mismatch in ModuleManager._download results in status='error'

    and the corrupt file is deleted from disk, rather than reporting status='done'.
    """
    manager = ModuleManager.__new__(ModuleManager)
    manager.threads = {}

    save_path = tmp_path / "test_module.bin"
    test_module = ModuleInfo(
        id="test_module_id",
        display_name="Test Module",
        url="http://example.com/test.bin",
        save_to=save_path,
        hash="valid_expected_hash",
    )

    monkeypatch.setattr(
        "vcclient.voice_changer.module_manager.module_manager.REGISTERED_MODULES",
        [test_module],
    )

    # Mock requests.get response
    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = "100"
    mock_resp.iter_content.return_value = [b"corrupted_or_incomplete_data"]

    statuses: list[ModuleDownloadStatus] = []

    def callback(status: ModuleDownloadStatus):
        statuses.append(status)

    with patch("requests.get", return_value=mock_resp):
        # Force _check_hash to return False (mismatch)
        with patch.object(manager, "_check_hash", return_value=False):
            manager._download(target_module=test_module, callback=callback)

    # Must have recorded validating and error statuses
    assert len(statuses) > 0
    final_status = statuses[-1]
    assert final_status.status == "error", f"Expected final status 'error', got '{final_status.status}'"
    assert "Hash validation failed" in str(final_status.error_message)

    # Ensure "done" was never reported
    assert not any(s.status == "done" for s in statuses), "'done' status should not be emitted on hash mismatch"

    # Corrupt file must be removed from disk
    assert not save_path.exists(), "Corrupt file must be deleted upon hash mismatch"


def test_download_hash_match_reports_done_and_keeps_file(tmp_path: Path, monkeypatch):
    """Verify that a successful hash match reports status='done' and keeps the file."""
    manager = ModuleManager.__new__(ModuleManager)
    manager.threads = {}

    save_path = tmp_path / "test_module_good.bin"
    test_module = ModuleInfo(
        id="test_module_good",
        display_name="Good Module",
        url="http://example.com/good.bin",
        save_to=save_path,
        hash="valid_expected_hash",
    )

    monkeypatch.setattr(
        "vcclient.voice_changer.module_manager.module_manager.REGISTERED_MODULES",
        [test_module],
    )

    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = "100"
    mock_resp.iter_content.return_value = [b"valid_complete_data"]

    statuses: list[ModuleDownloadStatus] = []

    def callback(status: ModuleDownloadStatus):
        statuses.append(status)

    with patch("requests.get", return_value=mock_resp):
        with patch.object(manager, "_check_hash", return_value=True):
            manager._download(target_module=test_module, callback=callback)

    assert len(statuses) > 0
    final_status = statuses[-1]
    assert final_status.status == "done", f"Expected final status 'done', got '{final_status.status}'"
    assert save_path.exists(), "Valid file should remain on disk"


def test_download_callback_failure_after_hash_match_keeps_file(tmp_path: Path, monkeypatch):
    """Verify that if completion notification fails after hash validation succeeds,

    the valid file is NOT deleted from disk.
    """
    manager = ModuleManager.__new__(ModuleManager)
    manager.threads = {}

    save_path = tmp_path / "test_module_callback_fail.bin"
    test_module = ModuleInfo(
        id="test_module_callback_fail",
        display_name="Callback Fail Module",
        url="http://example.com/callback_fail.bin",
        save_to=save_path,
        hash="valid_expected_hash",
    )

    monkeypatch.setattr(
        "vcclient.voice_changer.module_manager.module_manager.REGISTERED_MODULES",
        [test_module],
    )

    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = "100"
    mock_resp.iter_content.return_value = [b"valid_complete_data"]

    def failing_callback(status: ModuleDownloadStatus):
        if status.status == "done":
            raise RuntimeError("Simulated websocket/UI error during completion notification")

    with patch("requests.get", return_value=mock_resp):
        with patch.object(manager, "_check_hash", return_value=True):
            # This should handle the callback error gracefully without deleting the valid file
            manager._download(target_module=test_module, callback=failing_callback)

    assert save_path.exists(), "Valid file must be kept on disk even if completion callback raises an exception"


def test_get_module_filepath_returns_registered_path_and_rejects_unknown_id(tmp_path: Path, monkeypatch):
    """Registered IDs resolve to their path; an unregistered ID is a programming error, not None."""
    manager = ModuleManager.__new__(ModuleManager)
    save_path = tmp_path / "registered.onnx"
    module = ModuleInfo(
        id="registered.onnx",
        display_name="Registered",
        url="http://example.com/registered.onnx",
        save_to=save_path,
        hash="unused",
    )
    monkeypatch.setattr(
        "vcclient.voice_changer.module_manager.module_manager.REGISTERED_MODULES",
        [module],
    )

    assert manager.get_module_filepath("registered.onnx") == save_path

    with pytest.raises(VCClientError) as exc_info:
        manager.get_module_filepath("unregistered.onnx")
    assert exc_info.value.info.code == ERROR_CODE_MODULE_NOT_FOUND
