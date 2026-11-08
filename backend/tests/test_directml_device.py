from vcclient.voice_changer.voice_change_manager.device_manager.providers.directml import (
    _filter_directml_devices,
    _parse_vram_string,
    resolve_directml_provider,
)


def test_parse_vram_string():
    test_cases = [
        ("128 MB", 128 * 1024 * 1024),
        ("24138 MB", 24138 * 1024 * 1024),
        ("16 GB", 16 * 1024 * 1024 * 1024),
        ("0 B", 0),
        ("", 0),
        (None, 0),
    ]
    for raw, expected in test_cases:
        assert _parse_vram_string(raw) == expected


def test_filter_directml_devices_deduplication():
    # Case 1: 1 physical discrete GPU + 2 virtual compute nodes (the user's setup)
    raw_setup = [
        {
            "Description": "NVIDIA GeForce RTX 4090",
            "Discrete": "1",
            "DxgiAdapterNumber": "0",
            "DxgiHighPerformanceIndex": "0",
            "DxgiVideoMemory": "24138 MB",
            "LUID": "75725",
        },
        {
            "Description": "NVIDIA GeForce RTX 4090",
            "DxgiAdapterNumber": "1",
            "DxgiHighPerformanceIndex": "3",
            "DxgiVideoMemory": "24138 MB",
            "LUID": "359505787",
        },
        {
            "Description": "NVIDIA GeForce RTX 4090",
            "DxgiAdapterNumber": "2",
            "DxgiHighPerformanceIndex": "2",
            "DxgiVideoMemory": "24138 MB",
            "LUID": "139991",
        },
    ]
    filtered = _filter_directml_devices(raw_setup)
    assert len(filtered) == 1
    assert filtered[0]["DxgiAdapterNumber"] == "0"
    assert filtered[0]["LUID"] == "75725"

    # Case 2: Multi-GPU setup (2 distinct physical GPUs with different LUIDs)
    multi_gpu_setup = [
        {
            "Description": "NVIDIA GeForce RTX 4090",
            "Discrete": "1",
            "DxgiAdapterNumber": "0",
            "DxgiHighPerformanceIndex": "0",
            "LUID": "11111",
        },
        {
            "Description": "NVIDIA GeForce RTX 4090",
            "Discrete": "1",
            "DxgiAdapterNumber": "1",
            "DxgiHighPerformanceIndex": "1",
            "LUID": "22222",
        },
    ]
    filtered_multi = _filter_directml_devices(multi_gpu_setup)
    assert len(filtered_multi) == 2
    assert {it["LUID"] for it in filtered_multi} == {"11111", "22222"}

    # Case 3: Integrated GPU without Discrete flag
    igpu_setup = [
        {
            "Description": "AMD Radeon(TM) Graphics",
            "DxgiAdapterNumber": "1",
            "DxgiHighPerformanceIndex": "1",
            "LUID": "33333",
        },
        {
            "Description": "AMD Radeon(TM) Graphics",
            "DxgiAdapterNumber": "2",
            "DxgiHighPerformanceIndex": "2",
            "LUID": "44444",
        },
    ]
    filtered_igpu = _filter_directml_devices(igpu_setup)
    assert len(filtered_igpu) == 1
    assert filtered_igpu[0]["DxgiAdapterNumber"] == "1"


def test_resolve_directml_provider():
    # DirectML available
    res = resolve_directml_provider(0, ["DmlExecutionProvider", "CPUExecutionProvider"])
    assert res is not None
    providers, opts = res
    assert providers == ["DmlExecutionProvider"]
    assert opts == [{"device_id": 0}]

    # DirectML not available
    res_none = resolve_directml_provider(0, ["CPUExecutionProvider"])
    assert res_none is None
