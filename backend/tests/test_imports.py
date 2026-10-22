def test_import_server():
    from vcclient.server.vcserver import VCServer

    assert VCServer is not None


def test_import_inferencers():
    from vcclient.voice_changer.voice_change_manager.inferencer.rvc_inferencer_onnx_f0 import (
        RVCInferencerOnnxF0,
    )
    from vcclient.voice_changer.voice_change_manager.inferencer.rvc_inferencer_onnx_nof0 import (
        RVCInferencerOnnxNoF0,
    )

    assert RVCInferencerOnnxF0 is not None
    assert RVCInferencerOnnxNoF0 is not None


def test_import_pitch_estimators():
    from vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxfcpe_pitch_estimator import (
        FCPEOnnxPitchEstimator,
    )
    from vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxrmvpe_pitch_estimator import (
        RMVPEOnnxPitchEstimator,
    )

    assert RMVPEOnnxPitchEstimator is not None
    assert FCPEOnnxPitchEstimator is not None


def test_import_crossfade_processor():
    from vcclient.voice_changer.voice_change_manager.crossfade_processor import (
        CrossfadeProcessor,
    )

    proc = CrossfadeProcessor()
    assert proc is not None
