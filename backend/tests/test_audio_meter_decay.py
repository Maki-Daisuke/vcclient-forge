import numpy as np
import pytest

from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface


@pytest.mark.parametrize(
    ("samples", "previous", "expected"),
    [
        ([0.0, 0.0], 1.0, 0.5),
        ([0.0, 0.0], 0.5, 0.25),
        ([0.8, -0.8], 0.2, 0.8),
        ([0.2, -0.2], 1.0, 0.5),
        ([], 0.5, 0.5),
    ],
)
def test_audio_meter_follows_signal_with_faster_decay(samples, previous, expected):
    interface = LocalVoiceChangerInterface.__new__(LocalVoiceChangerInterface)
    assert interface.calc_vol(np.array(samples), previous) == pytest.approx(expected)
