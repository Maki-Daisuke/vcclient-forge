from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from vcclient.device import DeviceConfig
from vcclient.server.api_common import set_active_model_id_getter
from vcclient.server.vcserver_rest_api import get_rest_api
from vcclient.voice_changer import voice_changer_const
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.model_catalog import model_catalog_manager, sanitize_model_dirname
from vcclient.voice_changer.settings_manager import settings_manager
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


@pytest.fixture
def domain_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, Path, Path]]:
    model_dir = tmp_path / "model_dir"
    model_dir.mkdir()
    config_file = tmp_path / "settings" / "vc_conf.json"

    monkeypatch.setattr(voice_changer_const, "ModelDir", model_dir)
    monkeypatch.setattr(voice_changer_const, "ConfigFile", config_file)
    set_active_model_id_getter(None)

    def fake_estimate(model_path: Path) -> RVCSlotInfo:
        return RVCSlotInfo(
            slot_index=-1,
            voice_changer_type="RVC",
            name="",
            model_file=Path(model_path.name),
            is_onnx=True,
            inferencer_type="onnxRVC",
            sample_rate=40000,
            is_f0=True,
            embedder="hubert_base_l12",
            pitch_estimator="rmvpe",
            version="v2",
            chunk_sec=0.5,
            pitch_shift=0,
            index_ratio=0.0,
        )

    def fake_export(pth_path: Path, onnx_path: Path) -> None:
        onnx_path.write_bytes(b"exported:" + pth_path.read_bytes())

    monkeypatch.setattr(model_catalog_manager, "estimate_rvc_model", fake_estimate)
    monkeypatch.setattr(model_catalog_manager, "export_pth_to_onnx", fake_export)
    monkeypatch.setattr(
        settings_manager,
        "get_device_catalog",
        lambda: [
            DeviceConfig(id=0, canonical_id="cpu", provider="cpu", device_type="CPU", name="CPU"),
            DeviceConfig(id=1, canonical_id="cuda:0", provider="cuda", device_type="GPU", name="GPU"),
        ],
    )

    try:
        with TestClient(get_rest_api()) as client:
            yield client, model_dir, config_file
    finally:
        set_active_model_id_getter(None)


def _upload_model(
    client: TestClient,
    *,
    name: str,
    model_name: str = "voice.onnx",
    model_bytes: bytes = b"onnx-payload",
    index_bytes: bytes | None = None,
    icon_bytes: bytes | None = None,
    embedder: str | None = None,
):
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("model_file", (model_name, model_bytes, "application/octet-stream")),
    ]
    if index_bytes is not None:
        files.append(("index_file", ("voice.index", index_bytes, "application/octet-stream")))
    if icon_bytes is not None:
        files.append(("icon_file", ("avatar.png", icon_bytes, "image/png")))
    data = {"name": name}
    if embedder is not None:
        data["embedder"] = embedder
    return client.post("/api/models", data=data, files=files)


def test_sanitize_model_dirname() -> None:
    assert sanitize_model_dirname('  My<Voice>:Test*?"/\\|  ') == "My_Voice_Test_"
    assert sanitize_model_dirname("CON") == "Model"
    assert sanitize_model_dirname("...  ...") == "Model"
    assert len(sanitize_model_dirname("A" * 100)) == 64


def test_legacy_slot_and_config_migration(domain_env: tuple[TestClient, Path, Path]) -> None:
    client, model_dir, config_file = domain_env

    slot0 = model_dir / "0"
    slot0.mkdir()
    (slot0 / "voice0.onnx").write_bytes(b"onnx-0")
    (slot0 / "portrait.png").write_bytes(b"png-0")
    (slot0 / "params.json").write_text(
        json.dumps(
            {
                "slot_index": 0,
                "voice_changer_type": "RVC",
                "name": "Alpha",
                "model_file": "voice0.onnx",
                "icon_file": "C:\\old\\portrait.png",
                "is_onnx": True,
                "sample_rate": 40000,
                "is_f0": True,
                "embedder": "contentvec",
                "pitch_shift": 3,
                "index_ratio": 0.4,
            }
        ),
        encoding="utf-8",
    )

    # Empty slot placeholder should be left untouched without failing migration.
    (model_dir / "1").mkdir()

    slot2 = model_dir / "2"
    slot2.mkdir()
    (slot2 / "voice2.pth").write_bytes(b"pth-2")
    (slot2 / "voice2.index").write_bytes(b"index-2")
    (slot2 / "params.json").write_text(
        json.dumps(
            {
                "slot_index": 2,
                "voice_changer_type": "RVC",
                "name": "Beta:V2",
                "model_file": "voice2.pth",
                "index_file": "voice2.index",
                "is_onnx": False,
                "inferencer_type": "pyTorchRVC",
                "sample_rate": 40000,
                "is_f0": True,
            }
        ),
        encoding="utf-8",
    )

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(
            {
                "current_slot_index": 2,
                "voice_changer_input_mode": "server",
                "gpu_device_id_int": 1,
                "wasapi_exclude_emabled": True,
                "audio_input_device_gain": 1.5,
                "audio_output_device_gain": 0.75,
            }
        ),
        encoding="utf-8",
    )

    models_res = client.get("/api/models")
    assert models_res.status_code == 200
    models = models_res.json()
    assert [m["name"] for m in models] == ["Alpha", "Beta:V2"]

    first, second = models
    assert first["embedder"] == "hubert_base_l12"
    assert first["has_icon"] is True
    assert first["icon_revision"] == 1
    assert first["pitch_shift"] == 3
    assert second["has_index"] is True
    assert second["has_icon"] is False

    assert not slot0.exists()
    assert not slot2.exists()
    assert (model_dir / "1").exists()
    assert (model_dir / f"Alpha - {first['id']}").is_dir()
    migrated_second_dir = model_dir / f"Beta_V2 - {second['id']}"
    assert migrated_second_dir.is_dir()
    assert (migrated_second_dir / "voice2.onnx").is_file()

    catalog = json.loads((model_dir / "catalog.json").read_text(encoding="utf-8"))
    assert catalog == {"order": [first["id"], second["id"]]}

    settings_res = client.get("/api/settings")
    assert settings_res.status_code == 200
    settings_body = settings_res.json()
    assert settings_body["model_id"] == second["id"]
    assert settings_body["input_mode"] == "server"
    assert settings_body["compute_device_id"] == 1
    assert settings_body["wasapi_exclusive_enabled"] is True
    assert settings_body["input_gain"] == 1.5
    assert settings_body["output_gain"] == 0.75


def test_model_crud_rename_order_and_active_guards(domain_env: tuple[TestClient, Path, Path]) -> None:
    client, model_dir, _ = domain_env

    bad_upload = _upload_model(client, name="   ")
    assert bad_upload.status_code == 422
    assert bad_upload.json()["code"] == "validation_error"

    res1 = _upload_model(
        client,
        name="  First<Model>  ",
        index_bytes=b"idx",
        icon_bytes=b"png-bytes",
    )
    assert res1.status_code == 201
    assert "ETag" in res1.headers
    model1 = res1.json()
    id1 = model1["id"]
    assert model1["name"] == "First<Model>"
    assert model1["has_index"] is True
    assert model1["has_icon"] is True
    assert model1["icon_revision"] == 1
    assert (model_dir / f"First_Model_ - {id1}").is_dir()

    res2 = _upload_model(
        client,
        name="Second",
        model_name="second.pth",
        model_bytes=b"raw-pth",
        embedder="hubert_base_japanese_l12",
    )
    assert res2.status_code == 201
    model2 = res2.json()
    id2 = model2["id"]
    assert model2["embedder"] == "hubert_base_japanese_l12"
    dir2 = model_dir / f"Second - {id2}"
    assert (dir2 / "second.onnx").is_file() or any(p.suffix == ".onnx" for p in dir2.iterdir())
    assert not any(p.suffix == ".pth" for p in dir2.iterdir())

    missing_res = client.get("/api/models/nonexistent123")
    assert missing_res.status_code == 404
    assert missing_res.json()["code"] == "model_not_found"

    # Parameter updates work even when active; rename and delete fail with 409 model_in_use.
    set_active_model_id_getter(lambda: id1)

    param_put = client.put(
        f"/api/models/{id1}",
        json={"pitch_shift": 5, "index_ratio": 0.6, "chunk_sec": 0.25, "pitch_estimator": "fcpe"},
    )
    assert param_put.status_code == 200
    assert param_put.json()["pitch_shift"] == 5
    assert param_put.json()["pitch_estimator"] == "fcpe"
    etag1 = param_put.headers["ETag"]

    rename_blocked = client.put(f"/api/models/{id1}", json={"name": "RenamedWhileActive"})
    assert rename_blocked.status_code == 409
    assert rename_blocked.json()["code"] == "model_in_use"

    delete_blocked = client.delete(f"/api/models/{id1}")
    assert delete_blocked.status_code == 409
    assert delete_blocked.json()["code"] == "model_in_use"

    # Reordering only touches catalog.json and succeeds while session is active.
    order_res = client.put("/api/models/order", json={"model_ids": [id2, id1]})
    assert order_res.status_code == 200
    order_etag = order_res.headers["ETag"]
    assert order_res.json() == {"model_ids": [id2, id1]}
    assert [m["id"] for m in client.get("/api/models").json()] == [id2, id1]

    bad_order = client.put("/api/models/order", json={"model_ids": [id1]})
    assert bad_order.status_code == 409
    assert bad_order.json()["code"] == "catalog_mismatch"

    stale_order = client.put(
        "/api/models/order",
        json={"model_ids": [id1, id2]},
        headers={"If-Match": '"stale-etag"'},
    )
    assert stale_order.status_code == 409
    assert stale_order.json()["code"] == "etag_mismatch"

    ok_order = client.put(
        "/api/models/order",
        json={"model_ids": [id1, id2]},
        headers={"If-Match": order_etag},
    )
    assert ok_order.status_code == 200

    # Clear active model so rename and delete are permitted.
    set_active_model_id_getter(None)

    stale_put = client.put(
        f"/api/models/{id1}",
        json={"name": "NewName"},
        headers={"If-Match": '"wrong-etag"'},
    )
    assert stale_put.status_code == 409
    assert stale_put.json()["code"] == "etag_mismatch"

    renamed_res = client.put(
        f"/api/models/{id1}",
        json={"name": "RenamedModel"},
        headers={"If-Match": etag1},
    )
    assert renamed_res.status_code == 200
    assert renamed_res.json()["name"] == "RenamedModel"
    assert not (model_dir / f"First_Model_ - {id1}").exists()
    assert (model_dir / f"RenamedModel - {id1}").is_dir()

    # Point settings.model_id at id1, then delete id1 and confirm it is cleared.
    settings_put = client.put("/api/settings", json={"model_id": id1})
    assert settings_put.status_code == 200

    del_res = client.delete(f"/api/models/{id1}", headers={"If-Match": renamed_res.headers["ETag"]})
    assert del_res.status_code == 204
    assert not (model_dir / f"RenamedModel - {id1}").exists()
    assert client.get(f"/api/models/{id1}").status_code == 404
    assert [m["id"] for m in client.get("/api/models").json()] == [id2]
    assert client.get("/api/settings").json()["model_id"] is None


def test_model_icon_lifecycle(domain_env: tuple[TestClient, Path, Path]) -> None:
    client, model_dir, _ = domain_env

    create_res = _upload_model(client, name="IconVoice")
    assert create_res.status_code == 201
    model = create_res.json()
    model_id = model["id"]
    etag = create_res.headers["ETag"]
    assert model["has_icon"] is False
    assert model["icon_revision"] == 0

    missing_icon = client.get(f"/api/models/{model_id}/icon")
    assert missing_icon.status_code == 404
    assert missing_icon.json()["code"] == "icon_not_found"

    # Raw image/* PUT
    put_raw = client.put(
        f"/api/models/{model_id}/icon",
        content=b"png-raw-1",
        headers={"Content-Type": "image/png", "If-Match": etag},
    )
    assert put_raw.status_code == 200
    assert put_raw.json()["has_icon"] is True
    assert put_raw.json()["icon_revision"] == 1

    get_icon = client.get(f"/api/models/{model_id}/icon")
    assert get_icon.status_code == 200
    assert get_icon.content == b"png-raw-1"
    assert get_icon.headers.get("content-type") == "image/png"

    # Multipart PUT replaces previous icon file on disk and increments revision.
    put_multi = client.put(
        f"/api/models/{model_id}/icon",
        files={"icon_file": ("next.webp", b"webp-raw-2", "image/webp")},
        headers={"If-Match": put_raw.headers["ETag"]},
    )
    assert put_multi.status_code == 200
    assert put_multi.json()["icon_revision"] == 2
    model_folder = model_dir / f"IconVoice - {model_id}"
    assert len([p for p in model_folder.iterdir() if p.suffix in (".png", ".webp")]) == 1

    get_icon_2 = client.get(f"/api/models/{model_id}/icon")
    assert get_icon_2.status_code == 200
    assert get_icon_2.content == b"webp-raw-2"

    del_icon = client.delete(
        f"/api/models/{model_id}/icon",
        headers={"If-Match": put_multi.headers["ETag"]},
    )
    assert del_icon.status_code == 200
    assert del_icon.json()["has_icon"] is False
    assert del_icon.json()["icon_revision"] == 3
    assert client.get(f"/api/models/{model_id}/icon").status_code == 404

    # Deleting again is idempotent.
    del_again = client.delete(f"/api/models/{model_id}/icon")
    assert del_again.status_code == 200
    assert del_again.json()["icon_revision"] == 3


def test_settings_validation_etag_and_no_side_effects(
    domain_env: tuple[TestClient, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, config_file = domain_env

    pipeline_spy = MagicMock()
    monkeypatch.setattr(VoiceChanger, "check_and_update_pipeline", pipeline_spy)

    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    initial = get_res.json()
    etag = get_res.headers["ETag"]
    assert initial["input_mode"] == "client"

    stale = client.put("/api/settings", json={**initial, "input_gain": 3.0}, headers={"If-Match": '"stale"'})
    assert stale.status_code == 409
    assert stale.json()["code"] == "etag_mismatch"

    bad_device = client.put("/api/settings", json={**initial, "compute_device_id": 99})
    assert bad_device.status_code == 422
    assert bad_device.json()["code"] == "invalid_compute_device"

    bad_cutoff_order = client.put(
        "/api/settings",
        json={**initial, "high_pass_filter_cutoff": 5000, "low_pass_filter_cutoff": 4000},
    )
    assert bad_cutoff_order.status_code == 422
    assert bad_cutoff_order.json()["code"] == "invalid_filter_cutoff"

    bad_nyquist = client.put(
        "/api/settings",
        json={
            **initial,
            "audio_input_device_sample_rate": 16000,
            "enable_low_pass_filter": True,
            "low_pass_filter_cutoff": 9000,
        },
    )
    assert bad_nyquist.status_code == 422
    assert bad_nyquist.json()["code"] == "invalid_filter_cutoff"

    ok_res = client.put(
        "/api/settings",
        json={**initial, "input_gain": 1.25, "noise_gate": -45.0, "wasapi_exclusive_enabled": True},
        headers={"If-Match": etag},
    )
    assert ok_res.status_code == 200
    assert ok_res.headers["ETag"] != etag
    assert ok_res.json()["input_gain"] == 1.25
    assert ok_res.json()["noise_gate"] == -45.0
    assert ok_res.json()["wasapi_exclusive_enabled"] is True
    assert config_file.is_file()
    pipeline_spy.assert_not_called()


def test_voice_changer_uses_model_catalog_nanoid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from fastapi.testclient import TestClient
    from onnx import TensorProto, helper

    from vcclient.server import api_common
    from vcclient.voice_changer import voice_changer_const
    from vcclient.voice_changer.configuration_manager import configuration_manager as configuration_manager_mod
    from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
    from vcclient.voice_changer.data_types.voice_changer_data_types import (
        EmbedderInfo,
        PitchEstimatorInfo,
        RVCInferencerInfo,
    )
    from vcclient.voice_changer.model_catalog import model_catalog_manager
    from vcclient.voice_changer.voice_change_manager.embedders.embedder_manager import EmbedderManager
    from vcclient.voice_changer.voice_change_manager.inferencer.inferencer_manager import InferencerManager
    from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import (
        LocalVoiceChangerInterface,
    )
    from vcclient.voice_changer.voice_change_manager.pitch_estimator.pitch_estimator_manager import (
        PitchEstimatorManager,
    )
    from vcclient.voice_changer.voice_change_manager.vc_pipelines import rvc_pipeline as rvc_pipeline_mod
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
    from vcclient.voice_changer.voice_changer_const import PitchEstimatorType

    model_dir = tmp_path / "model_dir"
    model_dir.mkdir(parents=True, exist_ok=True)
    config_file = tmp_path / "vc_conf.json"

    monkeypatch.setattr(voice_changer_const, "ModelDir", model_dir)
    monkeypatch.setattr(voice_changer_const, "ConfigFile", config_file)
    monkeypatch.setattr(configuration_manager_mod, "ConfigFile", config_file)
    if hasattr(rvc_pipeline_mod, "ModelDir"):
        monkeypatch.setattr(rvc_pipeline_mod, "ModelDir", model_dir)
    monkeypatch.setattr(ConfigurationManager, "_instance", None)
    monkeypatch.setattr(VoiceChanger, "_instance", None)
    monkeypatch.setattr(LocalVoiceChangerInterface, "_instance", None)
    monkeypatch.setattr(api_common, "_active_model_id_getter", None)
    monkeypatch.setattr(model_catalog_manager, "_cached_model_dir", None)
    monkeypatch.setattr(model_catalog_manager, "_cached_slot_infos", {})

    captured_model_paths: list[Path] = []
    warmup_calls: list[int] = []

    class _FakeEmbedder:
        def get_info(self) -> EmbedderInfo:
            return EmbedderInfo(embedder_type="hubert_base_l9fp", model_file=Path("contentvec-f.onnx"), device_id=0)

    class _FakePitchEstimator:
        def __init__(self, pitch_estimator_type: PitchEstimatorType) -> None:
            self._type: PitchEstimatorType = pitch_estimator_type

        def get_info(self) -> PitchEstimatorInfo:
            return PitchEstimatorInfo(pitch_estimator_type=self._type, model_file=None, device_id=0)

    class _FakeInferencer:
        def __init__(self, model_path: Path) -> None:
            self._model_path = model_path

        def get_info(self) -> RVCInferencerInfo:
            return RVCInferencerInfo(inferencer_type="onnxRVC", model_file=self._model_path, device_id=0)

    monkeypatch.setattr(EmbedderManager, "get_embedder", classmethod(lambda cls, *args, **kwargs: _FakeEmbedder()))
    monkeypatch.setattr(
        PitchEstimatorManager,
        "get_pitch_estimator",
        classmethod(lambda cls, pitch_estimator_type, *args, **kwargs: _FakePitchEstimator(pitch_estimator_type)),
    )

    def _fake_get_inferencer(
        cls: type[InferencerManager],
        inferencer_type: str,
        model_path: Path,
        *args: object,
        **kwargs: object,
    ) -> _FakeInferencer:
        captured_model_paths.append(model_path)
        return _FakeInferencer(model_path)

    monkeypatch.setattr(InferencerManager, "get_inferencer", classmethod(_fake_get_inferencer))
    monkeypatch.setattr(rvc_pipeline_mod.RVCPipeline, "warmup", lambda self: warmup_calls.append(1))

    def _make_rvc_onnx_bytes() -> bytes:
        graph = helper.make_graph(
            [helper.make_node("Identity", ["x"], ["y"])],
            "test_rvc",
            [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])],
        )
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
        meta = model.metadata_props.add()
        meta.key = "metadata"
        meta.value = json.dumps(
            {
                "version": "3.0",
                "f0": 1,
                "samplingRate": 40000,
                "embedder": "hubert_base_l9fp",
            }
        )
        return model.SerializeToString()

    onnx_bytes = _make_rvc_onnx_bytes()
    client = TestClient(get_rest_api())

    create_1 = client.post(
        "/api/models",
        data={"name": "Model One"},
        files={"model_file": ("one.onnx", onnx_bytes, "application/octet-stream")},
    )
    assert create_1.status_code == 201, create_1.text
    id1 = create_1.json()["id"]

    create_2 = client.post(
        "/api/models",
        data={"name": "Model Two"},
        files={"model_file": ("two.onnx", onnx_bytes, "application/octet-stream")},
    )
    assert create_2.status_code == 201, create_2.text
    id2 = create_2.json()["id"]

    base_conf = client.get("/api/configuration-manager/configuration").json()
    conf_res = client.put("/api/configuration-manager/configuration", json={**base_conf, "model_id": id1})
    assert conf_res.status_code == 200, conf_res.text

    vc = VoiceChanger.get_instance()
    vc_info = vc.get_voice_changer_information()
    assert vc_info.model_id == id1
    assert vc.vc_pipeline is not None
    assert getattr(vc.vc_pipeline, "model_id", None) == id1
    assert len(captured_model_paths) == 1
    assert captured_model_paths[0].is_file(), f"Missing model path: {captured_model_paths[0]}"
    assert id1 in str(captured_model_paths[0].parent)

    # Live parameter updates flow through lock-free model_catalog cache without recreating pipeline
    patch_live = client.put(f"/api/models/{id1}", json={"pitch_shift": 5, "index_ratio": 0.65})
    assert patch_live.status_code == 200, patch_live.text
    assert vc.vc_pipeline.slot_info.pitch_shift == 5
    assert vc.vc_pipeline.slot_info.index_ratio == 0.65
    assert len(captured_model_paths) == 1

    # Changing chunk_sec while stopped refreshes pipeline shape/warmup
    warmup_before = len(warmup_calls)
    paths_before_chunk = len(captured_model_paths)
    patch_chunk = client.put(f"/api/models/{id1}", json={"chunk_sec": 0.8})
    assert patch_chunk.status_code == 200, patch_chunk.text
    assert len(warmup_calls) > warmup_before

    # Switching configuration to second NanoID loads second model
    switch_res = client.put("/api/configuration-manager/configuration", json={**base_conf, "model_id": id2})
    assert switch_res.status_code == 200, switch_res.text
    vc_info_2 = vc.get_voice_changer_information()
    assert vc_info_2.model_id == id2
    assert len(captured_model_paths) > paths_before_chunk
    assert captured_model_paths[-1].is_file(), f"Missing model path: {captured_model_paths[-1]}"
    assert id2 in str(captured_model_paths[-1].parent)

    # Deleting the currently loaded model while stopped clears configuration and pipeline
    del_res = client.delete(f"/api/models/{id2}")
    assert del_res.status_code == 204, del_res.text
    assert ConfigurationManager.get_instance().voice_changer_configuration.model_id is None
    assert vc.vc_pipeline is None


def test_user_settings_and_voice_changer_configuration_roundtrip_and_delete_preserves_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from onnx import TensorProto, helper

    from vcclient.server import api_common
    from vcclient.voice_changer import voice_changer_const
    from vcclient.voice_changer.configuration_manager import configuration_manager as configuration_manager_mod
    from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
    from vcclient.voice_changer.data_types.data_types import VoiceChangerConfiguration
    from vcclient.voice_changer.model_catalog import model_catalog_manager
    from vcclient.voice_changer.settings_manager import UserSettings
    from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import (
        LocalVoiceChangerInterface,
    )
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

    # 1. Bidirectional round-trip conversion between UserSettings and VoiceChangerConfiguration
    user_settings = UserSettings(
        model_id="test_model_id",
        input_mode="server",
        compute_device_id=3,
        input_gain=7.0,
        output_gain=1.5,
        wasapi_exclusive_enabled=True,
    )
    for conf in (
        VoiceChangerConfiguration.model_validate(user_settings.model_dump()),
        VoiceChangerConfiguration.model_validate_json(user_settings.model_dump_json()),
    ):
        assert conf.model_id == "test_model_id"
        assert conf.voice_changer_input_mode == "server"
        assert conf.gpu_device_id_int == 3
        assert conf.audio_input_device_gain == 7.0
        assert conf.audio_output_device_gain == 1.5
        assert conf.wasapi_exclusive_enabled is True

    vc_conf = VoiceChangerConfiguration(
        model_id="test_model_id",
        voice_changer_input_mode="server",
        gpu_device_id_int=3,
        audio_input_device_gain=7.0,
        audio_output_device_gain=1.5,
        wasapi_exclusive_enabled=True,
    )
    for rt_settings in (
        UserSettings.model_validate(vc_conf.model_dump()),
        UserSettings.model_validate_json(vc_conf.model_dump_json()),
    ):
        assert rt_settings.model_id == "test_model_id"
        assert rt_settings.input_mode == "server"
        assert rt_settings.compute_device_id == 3
        assert rt_settings.input_gain == 7.0
        assert rt_settings.output_gain == 1.5
        assert rt_settings.wasapi_exclusive_enabled is True

    # 2. Deleting selected model preserves existing VoiceChangerConfiguration fields and keys on reload
    model_dir = tmp_path / "model_dir"
    model_dir.mkdir(parents=True, exist_ok=True)
    config_file = tmp_path / "vc_conf.json"

    monkeypatch.setattr(voice_changer_const, "ModelDir", model_dir)
    monkeypatch.setattr(voice_changer_const, "ConfigFile", config_file)
    monkeypatch.setattr(configuration_manager_mod, "ConfigFile", config_file)
    monkeypatch.setattr(
        configuration_manager_mod,
        "get_device",
        lambda dev_id: SimpleNamespace(id=dev_id if 0 <= dev_id <= 3 else 0),
    )
    monkeypatch.setattr(ConfigurationManager, "_instance", None)
    monkeypatch.setattr(VoiceChanger, "_instance", None)
    monkeypatch.setattr(LocalVoiceChangerInterface, "_instance", None)
    monkeypatch.setattr(api_common, "_active_model_id_getter", None)
    monkeypatch.setattr(model_catalog_manager, "_cached_model_dir", None)
    monkeypatch.setattr(model_catalog_manager, "_cached_slot_infos", {})

    graph = helper.make_graph(
        [helper.make_node("Identity", ["x"], ["y"])],
        "test_rvc",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    meta = model.metadata_props.add()
    meta.key = "metadata"
    meta.value = json.dumps(
        {
            "version": "3.0",
            "f0": 1,
            "samplingRate": 40000,
            "embedder": "hubert_base_l9fp",
        }
    )

    client = TestClient(get_rest_api())
    create_res = client.post(
        "/api/models",
        data={"name": "Model Preserve"},
        files={"model_file": ("preserve.onnx", model.SerializeToString(), "application/octet-stream")},
    )
    assert create_res.status_code == 201, create_res.text
    created_id = create_res.json()["id"]

    persisted_conf = VoiceChangerConfiguration(
        current_slot_index=2,
        model_id=created_id,
        voice_changer_input_mode="server",
        gpu_device_id_int=3,
        audio_input_device_gain=7.0,
        audio_output_device_gain=1.5,
        wasapi_exclusive_enabled=True,
    )
    config_file.write_text(persisted_conf.model_dump_json(indent=4), encoding="utf-8")

    del_res = client.delete(f"/api/models/{created_id}")
    assert del_res.status_code == 204, del_res.text

    raw_after = json.loads(config_file.read_text(encoding="utf-8"))
    assert raw_after["model_id"] is None
    assert raw_after["current_slot_index"] == -1
    assert raw_after["voice_changer_input_mode"] == "server"
    assert raw_after["gpu_device_id_int"] == 3
    assert raw_after["audio_input_device_gain"] == 7.0
    assert raw_after["audio_output_device_gain"] == 1.5
    assert raw_after["wasapi_exclusive_enabled"] is True

    ConfigurationManager._instance = None
    reloaded = ConfigurationManager.get_instance().get_voice_changer_configuration()
    assert reloaded.model_id is None
    assert reloaded.voice_changer_input_mode == "server"
    assert reloaded.gpu_device_id_int == 3
    assert reloaded.audio_input_device_gain == 7.0
    assert reloaded.audio_output_device_gain == 1.5
    assert reloaded.wasapi_exclusive_enabled is True
