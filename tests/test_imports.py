def test_import_server():
    from vcclient_dev.server.vcserver import VCServer

    assert VCServer is not None


def test_import_inferencers():
    from vcclient_dev.voice_changer.voice_change_manager.inferencer.rvc_inverencer_onnx_f0 import (
        RVCInferencerOnnxF0,
    )
    from vcclient_dev.voice_changer.voice_change_manager.inferencer.rvc_inverencer_onnx_nof0 import (
        RVCInferencerOnnxNoF0,
    )

    assert RVCInferencerOnnxF0 is not None
    assert RVCInferencerOnnxNoF0 is not None


def test_import_pitch_estimators():
    from vcclient_dev.voice_changer.voice_change_manager.pitch_estimator.onnxrmvpe_pitch_estimator import (
        RMVPEOnnxPitchEstimator,
    )

    assert RMVPEOnnxPitchEstimator is not None


def test_import_crossfade_processor():
    from vcclient_dev.voice_changer.voice_change_manager.crossfade_processor import (
        CrossfadeProcessor,
    )

    proc = CrossfadeProcessor()
    assert proc is not None


def test_import_cui():
    from vcclient_dev.cui.vcclient_cui import VCClientCUI

    assert VCClientCUI is not None
