from pathlib import Path

import faiss
import numpy as np
import pytest

from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline


@pytest.mark.parametrize("dirname", ["plain", "棗イロハ - UXAaArLBU43j"])
def test_load_index_returns_index_and_reconstructed_features(tmp_path: Path, dirname: str):
    """_load_index returns the FAISS index together with all stored vectors as a NumPy array."""
    vectors = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0]], dtype=np.float32)
    source = faiss.IndexFlatL2(2)
    source.add(vectors)
    index_dir = tmp_path / dirname
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "added.index"
    index_file.write_bytes(bytes(faiss.serialize_index(source)))

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


def test_load_index_streams_multi_chunk_index(tmp_path: Path):
    """_load_index streams indexes larger than BufferedIOReader's 1 MiB buffer without truncation."""
    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((300, 1024), dtype=np.float32)  # > 1.2 MiB
    source = faiss.IndexFlatL2(1024)
    source.add(vectors)
    index_dir = tmp_path / "棗イロハ - UXAaArLBU43j"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "large.index"
    index_file.write_bytes(bytes(faiss.serialize_index(source)))

    pipeline = RVCPipeline.__new__(RVCPipeline)
    index, big_npy = pipeline._load_index(index_file)

    assert index.ntotal == 300
    np.testing.assert_array_equal(big_npy, vectors)


def test_load_index_raises_for_corrupt_file(tmp_path: Path):
    """A corrupt index file wraps FAISS deserialization failures in RuntimeError."""
    corrupt_file = tmp_path / "corrupt.index"
    corrupt_file.write_bytes(b"not a valid faiss index")
    pipeline = RVCPipeline.__new__(RVCPipeline)

    with pytest.raises(RuntimeError, match="Failed to load index"):
        pipeline._load_index(corrupt_file)
