import numpy as np

from vcclient.voice_changer.voice_change_manager.crossfade_processor import CrossfadeProcessor


def test_crossfade_processor_zero_size_does_not_raise():
    """Verify that crossfade_size=0 does not raise ValueError: v cannot be empty in convolve,

    and returns the expected output size.
    """
    processor = CrossfadeProcessor()
    output_audio_size = 480
    audio_buffer = np.linspace(-1.0, 1.0, 1000, dtype=np.float32)

    # Calling apply with crossfade_size=0 (previously raised ValueError in np.convolve)
    result = processor.apply(
        audio_with_overlap_buffer=audio_buffer,
        output_audio_size=output_audio_size,
        crossfade_size=0,
        crossfade_offset=0.0,
        crossfade_end=1.0,
        sola_search_frame=100,
    )

    assert isinstance(result, np.ndarray)
    assert result.shape == (output_audio_size,)
    assert not np.isnan(result).any()
    # When crossfade is zero, it should safely slice the trailing output_audio_size samples
    assert np.allclose(result, audio_buffer[-output_audio_size:])


def test_crossfade_processor_negative_size():
    """Verify that negative crossfade_size is safely handled without raising."""
    processor = CrossfadeProcessor()
    output_audio_size = 256
    audio_buffer = np.ones(500, dtype=np.float32)

    result = processor.apply(
        audio_with_overlap_buffer=audio_buffer,
        output_audio_size=output_audio_size,
        crossfade_size=-10,
        crossfade_offset=0.0,
        crossfade_end=1.0,
        sola_search_frame=50,
    )

    assert result.shape == (output_audio_size,)
    assert not np.isnan(result).any()


def test_crossfade_processor_normal_positive_crossfade():
    """Verify that positive crossfade_size executes crossfade as expected."""
    processor = CrossfadeProcessor()
    output_audio_size = 480
    crossfade_size = 48
    sola_search_frame = 24
    audio_buffer = np.sin(np.linspace(0, 10, 1000, dtype=np.float32))

    result = processor.apply(
        audio_with_overlap_buffer=audio_buffer,
        output_audio_size=output_audio_size,
        crossfade_size=crossfade_size,
        crossfade_offset=0.0,
        crossfade_end=1.0,
        sola_search_frame=sola_search_frame,
    )

    assert result.shape == (output_audio_size,)
    assert not np.isnan(result).any()
