import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vcclient.server import vcserver_rest_api_slot_manager as api
from vcclient.server.vcserver_rest_api import get_rest_api
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
from vcclient.voice_changer.voice_changer_const import SLOT_PARAM_FILE


@pytest.fixture
def upload_env(tmp_path: Path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)

    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", models_dir)
    monkeypatch.setattr(api, "ModelDir", models_dir)

    local = SimpleNamespace(
        lifecycle_lock=threading.Lock(),
        local_voice_changer_enabled=False,
        stream_running=False,
    )
    voice = SimpleNamespace(
        is_convert_chunk_bulk_started=lambda: False,
        vc_pipeline=None,
        vc_info=None,
    )
    monkeypatch.setattr(api.LocalVoiceChangerInterface, "get_instance", classmethod(lambda cls: local))
    monkeypatch.setattr(api.VoiceChanger, "_instance", voice)

    slot_manager = SlotManager()
    monkeypatch.setattr(SlotManager, "get_instance", classmethod(lambda cls: slot_manager))

    def fake_estimate(model_path: Path) -> RVCSlotInfo:
        return RVCSlotInfo(
            slot_index=0,
            voice_changer_type="RVC",
            name="estimated",
            model_file=Path(model_path.name),
            embedder="hubert_base_l12",
        )

    def fake_export(pth_file: Path, onnx_file: Path) -> None:
        onnx_file.write_bytes(b"exported:" + pth_file.read_bytes())

    monkeypatch.setattr(
        "vcclient.voice_changer.slot_manager.model_importer.model_importer.estimate_rvc_model",
        fake_estimate,
    )
    monkeypatch.setattr(
        "vcclient.voice_changer.slot_manager.model_importer.model_importer.export_pth_to_onnx",
        fake_export,
    )

    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        yield client, models_dir, local, voice, slot_manager


def _create_slot(models_dir: Path, slot_manager: SlotManager, slot_index: int = 0, *, with_icon: bool = True) -> Path:
    slot_dir = models_dir / str(slot_index)
    slot_dir.mkdir(parents=True, exist_ok=True)
    (slot_dir / "voice.onnx").write_bytes(b"onnx-data")
    icon_rel = None
    if with_icon:
        (slot_dir / "old_icon.png").write_bytes(b"old-icon")
        icon_rel = Path("old_icon.png")
    slot_info = RVCSlotInfo(
        slot_index=slot_index,
        voice_changer_type="RVC",
        name=f"Model{slot_index}",
        model_file=Path("voice.onnx"),
        icon_file=icon_rel,
    )
    (slot_dir / SLOT_PARAM_FILE).write_text(slot_info.model_dump_json(indent=4), encoding="utf-8")
    slot_manager.reload()
    return slot_dir


def test_post_slot_onnx_with_optional_index_and_icon(upload_env):
    client, models_dir, *_ = upload_env

    res = client.post(
        "/api/slot-manager/slots",
        data={"name": "  MyVoice  ", "voice_changer_type": "RVC"},
        files=[
            ("model_file", ("voice.onnx", b"onnx-binary-payload", "application/octet-stream")),
            ("index_file", ("voice.index", b"index-payload", "application/octet-stream")),
            ("icon_file", ("avatar.png", b"png-payload", "image/png")),
        ],
    )

    assert res.status_code == 200
    body = res.json()
    assert body["slot_index"] == 0
    assert body["name"] == "MyVoice"
    assert "terms_of_use_url" not in body
    assert body["model_file"].startswith("model_") and body["model_file"].endswith(".onnx")
    assert body["index_file"].startswith("index_") and body["index_file"].endswith(".index")
    assert body["icon_file"].startswith("icon_") and body["icon_file"].endswith(".png")

    slot_dir = models_dir / "0"
    assert (slot_dir / body["model_file"]).read_bytes() == b"onnx-binary-payload"
    assert (slot_dir / body["index_file"]).read_bytes() == b"index-payload"
    assert (slot_dir / body["icon_file"]).read_bytes() == b"png-payload"


def test_post_slot_pth_exports_onnx_and_applies_embedder(upload_env):
    client, models_dir, *_ = upload_env

    res = client.post(
        "/api/slot-manager/slots",
        data={"name": "PthVoice", "embedder": "hubert_base_japanese_l12"},
        files={"model_file": ("voice.pth", b"pth-bytes", "application/octet-stream")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["slot_index"] == 0
    assert body["model_file"].endswith(".onnx")
    assert body["embedder"] == "hubert_base_japanese_l12"
    assert (models_dir / "0" / body["model_file"]).read_bytes() == b"exported:pth-bytes"


@pytest.mark.parametrize(
    ("data", "files"),
    [
        ({"name": "   "}, {"model_file": ("v.onnx", b"123", "application/octet-stream")}),
        (
            {"name": "BadType", "voice_changer_type": "DDSP"},
            {"model_file": ("v.onnx", b"123", "application/octet-stream")},
        ),
        ({"name": "BadExt"}, {"model_file": ("v.txt", b"123", "text/plain")}),
        ({"name": "EmptyModel"}, {"model_file": ("v.onnx", b"", "application/octet-stream")}),
        (
            {"name": "BadIndex"},
            [
                ("model_file", ("v.onnx", b"123", "application/octet-stream")),
                ("index_file", ("bad.bin", b"123", "application/octet-stream")),
            ],
        ),
        (
            {"name": "BadIconMime"},
            [
                ("model_file", ("v.onnx", b"123", "application/octet-stream")),
                ("icon_file", ("icon.png", b"123", "text/plain")),
            ],
        ),
        (
            {"name": "EmptyIcon"},
            [
                ("model_file", ("v.onnx", b"123", "application/octet-stream")),
                ("icon_file", ("icon.png", b"", "image/png")),
            ],
        ),
    ],
)
def test_post_slot_rejects_invalid_inputs_without_creating_slot(upload_env, data, files):
    client, models_dir, *_ = upload_env

    res = client.post("/api/slot-manager/slots", data=data, files=files)

    assert res.status_code == 400
    assert list(models_dir.iterdir()) == []


def test_post_slot_validation_error_with_binary_multipart_payload(upload_env):
    client, models_dir, *_ = upload_env

    # name フィールド欠落 + 非UTF-8 バイナリを含む multipart リクエストで
    # ValidationErrorLoggingRoute が UnicodeDecodeError を起こさず 422 を返すこと
    res = client.post(
        "/api/slot-manager/slots",
        files={"model_file": ("v.onnx", b"\xff\xfe\x00\x81onnx", "application/octet-stream")},
    )

    assert res.status_code == 422
    assert list(models_dir.iterdir()) == []


def test_post_slot_rollback_leaves_no_partial_slot_on_importer_failure(upload_env, monkeypatch):
    client, models_dir, *_ = upload_env

    def failing_estimate(model_path: Path) -> RVCSlotInfo:
        raise RuntimeError("corrupt onnx")

    monkeypatch.setattr(
        "vcclient.voice_changer.slot_manager.model_importer.model_importer.estimate_rvc_model",
        failing_estimate,
    )

    res = client.post(
        "/api/slot-manager/slots",
        data={"name": "BrokenModel"},
        files={"model_file": ("broken.onnx", b"broken-bytes", "application/octet-stream")},
    )

    assert res.status_code == 422
    assert list(models_dir.iterdir()) == []


@pytest.mark.parametrize("state", ["local_voice_changer_enabled", "stream_running", "bulk"])
def test_post_and_patch_reject_when_audio_active(upload_env, monkeypatch, state):
    client, models_dir, local, voice, slot_manager = upload_env
    _create_slot(models_dir, slot_manager, 0)

    if state == "bulk":
        monkeypatch.setattr(voice, "is_convert_chunk_bulk_started", lambda: True)
    else:
        setattr(local, state, True)

    post_res = client.post(
        "/api/slot-manager/slots",
        data={"name": "Blocked"},
        files={"model_file": ("v.onnx", b"onnx", "application/octet-stream")},
    )
    patch_res = client.patch("/api/slot-manager/slots/0", data={"name": "BlockedRename"})

    assert post_res.status_code == 409
    assert patch_res.status_code == 409


def test_patch_slot_name_only_preserves_icon(upload_env):
    client, models_dir, _, _, slot_manager = upload_env
    slot_dir = _create_slot(models_dir, slot_manager, 0, with_icon=True)

    res = client.patch("/api/slot-manager/slots/0", data={"name": "  UpdatedName  "})

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "UpdatedName"
    assert body["icon_file"] == "old_icon.png"
    assert (slot_dir / "old_icon.png").read_bytes() == b"old-icon"


def test_patch_slot_icon_only_replaces_old_icon_and_preserves_name(upload_env):
    client, models_dir, _, _, slot_manager = upload_env
    slot_dir = _create_slot(models_dir, slot_manager, 0, with_icon=True)

    res = client.patch(
        "/api/slot-manager/slots/0",
        files={"icon_file": ("next.webp", b"webp-bytes", "image/webp")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Model0"
    assert body["icon_file"].startswith("icon_") and body["icon_file"].endswith(".webp")
    assert (slot_dir / body["icon_file"]).read_bytes() == b"webp-bytes"
    assert not (slot_dir / "old_icon.png").exists()


def test_patch_slot_atomic_name_and_icon_and_invalid_rollback(upload_env):
    client, models_dir, _, _, slot_manager = upload_env
    slot_dir = _create_slot(models_dir, slot_manager, 0, with_icon=True)

    bad_res = client.patch(
        "/api/slot-manager/slots/0",
        data={"name": "   "},
        files={"icon_file": ("next.png", b"new-png", "image/png")},
    )
    assert bad_res.status_code == 400
    assert (slot_dir / "old_icon.png").read_bytes() == b"old-icon"
    assert slot_manager.get_slot_info(0).name == "Model0"

    ok_res = client.patch(
        "/api/slot-manager/slots/0",
        data={"name": "BothUpdated"},
        files={"icon_file": ("next.png", b"new-png", "image/png")},
    )
    assert ok_res.status_code == 200
    body = ok_res.json()
    assert body["name"] == "BothUpdated"
    assert body["icon_file"].startswith("icon_") and body["icon_file"].endswith(".png")
    assert (slot_dir / body["icon_file"]).read_bytes() == b"new-png"
    assert not (slot_dir / "old_icon.png").exists()


def test_patch_slot_rejects_empty_payload_bad_icon_and_empty_slot(upload_env):
    client, models_dir, _, _, slot_manager = upload_env
    _create_slot(models_dir, slot_manager, 0, with_icon=False)

    assert client.patch("/api/slot-manager/slots/0").status_code == 400
    assert (
        client.patch(
            "/api/slot-manager/slots/0",
            files={"icon_file": ("bad.txt", b"123", "text/plain")},
        ).status_code
        == 400
    )
    assert client.patch("/api/slot-manager/slots/1", data={"name": "EmptySlot"}).status_code == 422


def test_legacy_chunked_uploader_and_set_icon_routes_removed():
    app = get_rest_api()
    with TestClient(app) as client:
        assert client.post("/api/uploader/upload_file_chunk").status_code == 404
        assert client.post("/api/uploader/concat_uploaded_file_chunk").status_code == 404
        assert client.post("/api/slot-manager/slots/operation/set_icon_file").status_code == 404
