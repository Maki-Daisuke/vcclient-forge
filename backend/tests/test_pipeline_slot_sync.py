from unittest.mock import MagicMock, patch

from vcclient.voice_changer import voice_changer_const
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.model_catalog import model_catalog_manager
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def test_set_pitch_estimator_type_passes_argument_to_manager():
    """Verify that RVCPipeline.set_pitch_estimator_type passes the target pitch_estimator_type

    to PitchEstimatorManager instead of the stale self.slot_info value.
    """
    initial_slot_info = RVCSlotInfo(
        slot_index=-1,
        model_id="test_model_99",
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.3,
    )

    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline._slot_info = initial_slot_info
    pipeline.slot_index = -1
    pipeline.model_id = "test_model_99"
    pipeline.gpu_device_id = -1
    pipeline.pitch_estimator_type = "rmvpe"

    with patch(
        "vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline.PitchEstimatorManager.get_pitch_estimator"
    ) as mock_get:
        mock_estimator = MagicMock()
        mock_get.return_value = mock_estimator

        # Switch to fcpe
        pipeline.set_pitch_estimator_type("fcpe")

        # Must be called with "fcpe", NOT "rmvpe"
        mock_get.assert_called_once_with("fcpe", -1)
        assert pipeline.pitch_estimator_type == "fcpe"
        assert pipeline.pitch_estimator == mock_estimator


def test_pipeline_slot_info_dynamic_sync(monkeypatch):
    """Verify that RVCPipeline.slot_info dynamically tracks updates in model_catalog cache."""
    initial_slot_info = RVCSlotInfo(
        slot_index=-1,
        model_id="test_model_99",
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.25,
    )

    monkeypatch.setattr(model_catalog_manager, "_cached_model_dir", voice_changer_const.ModelDir)
    monkeypatch.setattr(model_catalog_manager, "_cached_slot_infos", {"test_model_99": initial_slot_info})

    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline._slot_info = initial_slot_info
    pipeline.slot_index = -1
    pipeline.model_id = "test_model_99"

    assert pipeline.slot_info.index_ratio == 0.25

    # Simulate catalog update with a replaced RVCSlotInfo instance
    updated_slot_info = RVCSlotInfo(
        slot_index=-1,
        model_id="test_model_99",
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="fcpe",
        index_ratio=0.75,
    )
    monkeypatch.setattr(model_catalog_manager, "_cached_slot_infos", {"test_model_99": updated_slot_info})

    # pipeline.slot_info must dynamically reflect the new instance and values
    assert pipeline.slot_info.index_ratio == 0.75
    assert pipeline.slot_info.pitch_estimator == "fcpe"
