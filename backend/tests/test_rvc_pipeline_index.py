from pathlib import Path

import faiss
import numpy as np
import pytest

from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


def test_load_index_returns_index_and_reconstructed_features(tmp_path: Path):
    """_load_index returns the FAISS index together with all stored vectors as a NumPy array."""
    vectors = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0]], dtype=np.float32)
    source = faiss.IndexFlatL2(2)
    source.add(vectors)
    index_file = tmp_path / "added.index"
    faiss.write_index(source, str(index_file))

    pipeline = RVCPipeline.__new__(RVCPipeline)
    index, big_npy = pipeline._load_index(index_file)

    assert isinstance(index, faiss.Index)
    assert index.ntotal == 3
    assert isinstance(big_npy, np.ndarray)
    assert big_npy.dtype == np.float32
    np.testing.assert_array_equal(big_npy, vectors)


def test_load_index_raises_for_missing_file(tmp_path: Path):
    """A missing index file raises instead of yielding a half-initialized (index, None) pair."""
    pipeline = RVCPipeline.__new__(RVCPipeline)

    with pytest.raises(RuntimeError):
        pipeline._load_index(tmp_path / "missing.index")
