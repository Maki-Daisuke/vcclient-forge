from unittest.mock import MagicMock, patch

from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def test_set_pitch_estimator_type_passes_argument_to_manager():
    """Verify that RVCPipeline.set_pitch_estimator_type passes the target pitch_estimator_type

    to PitchEstimatorManager instead of the stale self.slot_info value.
    """
    initial_slot_info = RVCSlotInfo(
        slot_index=99,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.3,
    )

    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline._slot_info = initial_slot_info
    pipeline.slot_index = 99
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
    """Verify that RVCPipeline.slot_info dynamically tracks updates in SlotManager."""
    slot_mgr = SlotManager.get_instance()
    initial_slot_info = RVCSlotInfo(
        slot_index=99,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="rmvpe",
        index_ratio=0.25,
    )

    # Register in SlotManager using monkeypatch for test isolation
    monkeypatch.setattr(slot_mgr, "slot_infos", [initial_slot_info])

    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline._slot_info = initial_slot_info
    pipeline.slot_index = 99

    assert pipeline.slot_info.index_ratio == 0.25

    # Simulate slot update with a replaced RVCSlotInfo instance
    updated_slot_info = RVCSlotInfo(
        slot_index=99,
        voice_changer_type="RVC",
        model_file="dummy.onnx",
        pitch_estimator="fcpe",
        index_ratio=0.75,
    )
    monkeypatch.setattr(slot_mgr, "slot_infos", [updated_slot_info])

    # pipeline.slot_info must dynamically reflect the new instance and values
    assert pipeline.slot_info.index_ratio == 0.75
    assert pipeline.slot_info.pitch_estimator == "fcpe"
