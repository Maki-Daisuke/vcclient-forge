import json
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from vcclient.server import vcserver_rest_api_slot_manager as api


@pytest.fixture
def environment(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    for index in (0, 2):
        path = models / str(index)
        path.mkdir()
        (path / "params.json").write_text(json.dumps({"slot_index": index}), encoding="utf-8")
        (path / "model.onnx").write_bytes(str(index).encode())
    config_path = tmp_path / "configuration.json"
    config_path.write_text(json.dumps({"current_slot_index": 2}), encoding="utf-8")
    configuration = SimpleNamespace(current_slot_index=2)
    manager = SimpleNamespace(
        get_slot_infos=lambda: [SimpleNamespace(slot_index=i, voice_changer_type="RVC") for i in (0, 2)],
        reload=lambda: None,
    )
    pipeline = Mock(spec=api.RVCPipeline)
    pipeline.slot_index = 2
    voice = SimpleNamespace(
        vc_pipeline=pipeline,
        vc_info=SimpleNamespace(slot_index=2, voice_changer_type="RVC", pitch_estimator_type="rmvpe"),
        is_convert_chunk_bulk_started=lambda: False,
    )
    local = SimpleNamespace(lifecycle_lock=RLock(), local_voice_changer_enabled=False, stream_running=False)
    monkeypatch.setattr(api, "ModelDir", models)
    monkeypatch.setattr(api, "ConfigFile", config_path)
    monkeypatch.setattr(api.SlotManager, "get_instance", lambda: manager)
    monkeypatch.setattr(
        api.ConfigurationManager,
        "get_instance",
        lambda: SimpleNamespace(get_voice_changer_configuration=lambda: configuration),
    )
    monkeypatch.setattr(api.VoiceChanger, "_instance", voice)
    monkeypatch.setattr(api.LocalVoiceChangerInterface, "get_instance", lambda: local)
    return models, configuration, voice, local


def test_reorder_preserves_selected_model(environment):
    models, configuration, voice, _ = environment
    result = api.RestAPISlotManager().organize_models(api.OrganizeModelsParam(order=[2, 0]))
    assert result == {"current_slot_index": 0}
    assert (models / "0" / "model.onnx").read_bytes() == b"2"
    assert configuration.current_slot_index == voice.vc_info.slot_index == voice.vc_pipeline.slot_index == 0


def test_reorder_http_route(environment):
    models, configuration, _, _ = environment
    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.post(
            "/api/slot-manager/operation/organize",
            json={"order": [2, 0]},
        )
    assert response.status_code == 200
    assert response.json() == {"current_slot_index": 0}
    assert configuration.current_slot_index == 0
    assert (models / "0" / "model.onnx").read_bytes() == b"2"


def test_reorder_cannot_delete_a_model(environment):
    models, configuration, _, _ = environment
    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.post(
            "/api/slot-manager/operation/organize",
            json={"order": [0], "delete_selected": True},
        )
    assert response.status_code == 409
    assert configuration.current_slot_index == 2
    assert sorted(path.name for path in models.iterdir()) == ["0", "2"]


@pytest.mark.parametrize("deleted", [0, 2])
def test_delete_model_by_index_compacts_and_updates_selection(environment, deleted):
    models, configuration, voice, _ = environment
    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.delete(f"/api/slot-manager/slots/{deleted}")
    assert response.status_code == 200
    expected = -1 if deleted == 2 else 0
    assert response.json() == {"current_slot_index": expected}
    assert configuration.current_slot_index == voice.vc_info.slot_index == expected
    assert (models / "0" / "model.onnx").read_bytes() == (b"0" if deleted == 2 else b"2")
    if deleted == 2:
        assert voice.vc_pipeline is None
    else:
        assert voice.vc_pipeline.slot_index == 0


def test_delete_missing_model_preserves_existing_models(environment):
    models, configuration, _, _ = environment
    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.delete("/api/slot-manager/slots/1")
    assert response.status_code == 404
    assert configuration.current_slot_index == 2
    assert sorted(path.name for path in models.iterdir()) == ["0", "2"]


def test_delete_missing_model_returns_http_exception_code_not_unsupported(environment):
    from vcclient.server.vcserver_rest_api import register_api_exception_handlers

    models, configuration, _, _ = environment
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.delete("/api/slot-manager/slots/1")
    assert response.status_code == 404
    detail = json.loads(response.json()["detail"])
    assert detail["code"] == "ERR_HTTP_EXCEPTION"
    assert detail["message"] == "Model does not exist"
    assert configuration.current_slot_index == 2
    assert sorted(path.name for path in models.iterdir()) == ["0", "2"]


def test_delete_selected_model_succeeds_without_loading_pipeline_when_uninitialized(environment, monkeypatch):
    models, configuration, _, _ = environment
    monkeypatch.setattr(api.VoiceChanger, "_instance", None)

    def fail_if_called():
        raise AssertionError("VoiceChanger.get_instance must not load pipelines during organize/delete")

    monkeypatch.setattr(api.VoiceChanger, "get_instance", fail_if_called)
    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.delete("/api/slot-manager/slots/2")
    assert response.status_code == 200
    assert response.json() == {"current_slot_index": -1}
    assert configuration.current_slot_index == -1
    assert sorted(path.name for path in models.iterdir()) == ["0"]


@pytest.mark.parametrize("state", ["local_voice_changer_enabled", "stream_running", "bulk"])
def test_delete_rejects_while_audio_active_or_still_stopping(environment, monkeypatch, state):
    models, configuration, voice, local = environment
    if state == "bulk":
        monkeypatch.setattr(voice, "is_convert_chunk_bulk_started", lambda: True)
    else:
        setattr(local, state, True)
    app = FastAPI()
    app.include_router(api.RestAPISlotManager().router)
    with TestClient(app) as client:
        response = client.delete("/api/slot-manager/slots/0")
    assert response.status_code == 409
    assert configuration.current_slot_index == 2
    assert sorted(path.name for path in models.iterdir()) == ["0", "2"]


@pytest.mark.parametrize("field", ["local_voice_changer_enabled", "stream_running"])
def test_rejects_while_audio_active_or_still_stopping(environment, field):
    models, configuration, _, local = environment
    setattr(local, field, True)
    with pytest.raises(HTTPException) as error:
        api.RestAPISlotManager().organize_models(api.OrganizeModelsParam(order=[2, 0]))
    assert error.value.status_code == 409
    assert configuration.current_slot_index == 2
    assert sorted(path.name for path in models.iterdir()) == ["0", "2"]
