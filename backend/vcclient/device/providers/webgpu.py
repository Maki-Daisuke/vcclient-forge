from __future__ import annotations

import ctypes
import ctypes.util
import functools
import os
import platform
from typing import Any

import onnxruntime

from vcclient.logger import logger

from ..data_types import DeviceConfig

# Vulkan constants (standardized ABI from vulkan_core.h)
_VK_SUCCESS = 0
_VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
_VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
_VK_MEMORY_HEAP_DEVICE_LOCAL_BIT = 0x00000001

_VK_PHYSICAL_DEVICE_TYPE_OTHER = 0
_VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU = 1
_VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU = 2
_VK_PHYSICAL_DEVICE_TYPE_VIRTUAL_GPU = 3
_VK_PHYSICAL_DEVICE_TYPE_CPU = 4

_VK_DEVICE_TYPE_NAMES: dict[int, str] = {
    _VK_PHYSICAL_DEVICE_TYPE_OTHER: "OTHER",
    _VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU: "INTEGRATED_GPU",
    _VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU: "DISCRETE_GPU",
    _VK_PHYSICAL_DEVICE_TYPE_VIRTUAL_GPU: "VIRTUAL_GPU",
    _VK_PHYSICAL_DEVICE_TYPE_CPU: "CPU",
}

# Mirrors Dawn high-performance adapter ordering (discrete -> integrated -> virtual -> other -> cpu)
_DAWN_HIGH_PERF_RANK: dict[int, int] = {
    _VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU: 0,
    _VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU: 1,
    _VK_PHYSICAL_DEVICE_TYPE_VIRTUAL_GPU: 2,
    _VK_PHYSICAL_DEVICE_TYPE_OTHER: 3,
    _VK_PHYSICAL_DEVICE_TYPE_CPU: 4,
}

_webgpu_runtime_initialized = False


class _VkApplicationInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("pApplicationName", ctypes.c_char_p),
        ("applicationVersion", ctypes.c_uint32),
        ("pEngineName", ctypes.c_char_p),
        ("engineVersion", ctypes.c_uint32),
        ("apiVersion", ctypes.c_uint32),
    ]


class _VkInstanceCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.POINTER(_VkApplicationInfo)),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
    ]


class _VkPhysicalDeviceProperties(ctypes.Structure):
    _fields_ = [
        ("apiVersion", ctypes.c_uint32),
        ("driverVersion", ctypes.c_uint32),
        ("vendorID", ctypes.c_uint32),
        ("deviceID", ctypes.c_uint32),
        ("deviceType", ctypes.c_uint32),
        ("deviceName", ctypes.c_char * 256),
        ("pipelineCacheUUID", ctypes.c_uint8 * 16),
        # Pad over VkPhysicalDeviceLimits and VkPhysicalDeviceSparseProperties without spelling every limit field.
        ("_tail", ctypes.c_uint8 * 2048),
    ]


class _VkMemoryType(ctypes.Structure):
    _fields_ = [
        ("propertyFlags", ctypes.c_uint32),
        ("heapIndex", ctypes.c_uint32),
    ]


class _VkMemoryHeap(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint64),
        ("flags", ctypes.c_uint32),
    ]


class _VkPhysicalDeviceMemoryProperties(ctypes.Structure):
    _fields_ = [
        ("memoryTypeCount", ctypes.c_uint32),
        ("memoryTypes", _VkMemoryType * 32),
        ("memoryHeapCount", ctypes.c_uint32),
        ("memoryHeaps", _VkMemoryHeap * 16),
    ]


def setup_webgpu_runtime() -> None:
    """Register the WebGPU Execution Provider plugin library if installed."""
    global _webgpu_runtime_initialized
    if _webgpu_runtime_initialized:
        return
    _webgpu_runtime_initialized = True

    try:
        import onnxruntime_ep_webgpu as webgpu_ep

        if hasattr(onnxruntime, "register_execution_provider_library"):
            lib_path = webgpu_ep.get_library_path()
            ep_name = webgpu_ep.get_ep_name()
            onnxruntime.register_execution_provider_library(ep_name, lib_path)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Failed to register WebGPU EP library: %s", e)


def is_webgpu_available() -> bool:
    """Check if WebGpuExecutionProvider is registered and available."""
    setup_webgpu_runtime()
    return find_webgpu_ep_device() is not None


def find_webgpu_ep_device() -> Any | None:
    """Return the registered WebGpuExecutionProvider OrtEpDevice if available."""
    if not hasattr(onnxruntime, "get_ep_devices"):
        return None
    try:
        for d in onnxruntime.get_ep_devices():
            if getattr(d, "ep_name", "") == "WebGpuExecutionProvider":
                return d
    except Exception as e:
        logger.debug("Failed to inspect WebGPU ep_devices: %s", e)
    return None


@functools.cache
def enumerate_vulkan_physical_devices() -> list[dict[str, Any]]:
    """Query Vulkan physical devices via libvulkan.so.1 without spawning external CLI tools."""
    lib_name = ctypes.util.find_library("vulkan") or "libvulkan.so.1"
    try:
        vk = ctypes.CDLL(lib_name)
    except OSError as e:
        logger.debug("Failed to load Vulkan loader (%s): %s", lib_name, e)
        return []

    vk.vkCreateInstance.argtypes = [
        ctypes.POINTER(_VkInstanceCreateInfo),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    vk.vkCreateInstance.restype = ctypes.c_int32
    vk.vkDestroyInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vk.vkDestroyInstance.restype = None
    vk.vkEnumeratePhysicalDevices.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    vk.vkEnumeratePhysicalDevices.restype = ctypes.c_int32
    vk.vkGetPhysicalDeviceProperties.argtypes = [ctypes.c_void_p, ctypes.POINTER(_VkPhysicalDeviceProperties)]
    vk.vkGetPhysicalDeviceProperties.restype = None
    vk.vkGetPhysicalDeviceMemoryProperties.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_VkPhysicalDeviceMemoryProperties),
    ]
    vk.vkGetPhysicalDeviceMemoryProperties.restype = None

    app_info = _VkApplicationInfo(sType=_VK_STRUCTURE_TYPE_APPLICATION_INFO, apiVersion=(1 << 22))
    create_info = _VkInstanceCreateInfo(
        sType=_VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        pApplicationInfo=ctypes.pointer(app_info),
    )
    instance = ctypes.c_void_p()
    if (
        vk.vkCreateInstance(ctypes.byref(create_info), None, ctypes.byref(instance)) != _VK_SUCCESS
        or not instance.value
    ):
        return []

    devices: list[dict[str, Any]] = []
    try:
        count = ctypes.c_uint32(0)
        if vk.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None) != _VK_SUCCESS or count.value == 0:
            return []

        handles = (ctypes.c_void_p * count.value)()
        if vk.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), handles) != _VK_SUCCESS:
            return []

        for idx in range(count.value):
            props = _VkPhysicalDeviceProperties()
            vk.vkGetPhysicalDeviceProperties(handles[idx], ctypes.byref(props))
            mem = _VkPhysicalDeviceMemoryProperties()
            vk.vkGetPhysicalDeviceMemoryProperties(handles[idx], ctypes.byref(mem))
            heap_count = min(int(mem.memoryHeapCount), 16)
            vram_bytes = sum(
                int(mem.memoryHeaps[h].size)
                for h in range(heap_count)
                if mem.memoryHeaps[h].flags & _VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
            )
            devices.append(
                {
                    "loader_index": idx,
                    "name": props.deviceName.decode("utf-8", errors="replace").strip(),
                    "vk_device_type": int(props.deviceType),
                    "vendor_id": int(props.vendorID),
                    "vk_device_id": int(props.deviceID),
                    "vram_bytes": vram_bytes,
                }
            )
    finally:
        vk.vkDestroyInstance(instance, None)
    return devices


def is_vulkan_discrete_gpu(vendor_id: int, device_id: int) -> bool:
    """Return whether Vulkan reports the PCI vendor/device pair as a discrete GPU."""
    return any(
        d["vendor_id"] == vendor_id
        and d["vk_device_id"] == device_id
        and d["vk_device_type"] == _VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
        for d in enumerate_vulkan_physical_devices()
    )


def detect_webgpu_devices() -> list[DeviceConfig]:
    """Detect available Linux Vulkan GPUs usable via WebGpuExecutionProvider."""
    if platform.system() != "Linux":
        return []
    if not is_webgpu_available():
        return []

    raw_devices = enumerate_vulkan_physical_devices()
    if not raw_devices:
        return []

    # Sort identically to Dawn's high-performance ordering before assigning adapterIndex,
    # then drop CPU software renderers (e.g. llvmpipe) unless explicitly opted in for testing.
    sorted_devices = sorted(
        raw_devices,
        key=lambda d: (_DAWN_HIGH_PERF_RANK.get(d["vk_device_type"], 99), d["loader_index"]),
    )
    allow_software = os.environ.get("VCCLIENT_WEBGPU_ALLOW_SOFTWARE") == "1"

    configs: list[DeviceConfig] = []
    for adapter_index, dev in enumerate(sorted_devices):
        vk_type = dev["vk_device_type"]
        if vk_type == _VK_PHYSICAL_DEVICE_TYPE_CPU and not allow_software:
            continue
        raw_name = dev["name"] or f"Vulkan GPU #{adapter_index}"
        name = raw_name if raw_name.startswith("[WebGPU]") else f"[WebGPU] {raw_name}"
        configs.append(
            DeviceConfig(
                id=0,
                canonical_id=f"webgpu:{adapter_index}",
                provider="webgpu",
                device_index=adapter_index,
                device_type="GPU",
                name=name,
                adapter_ram=dev["vram_bytes"],
                metadata={
                    "adapter_index": adapter_index,
                    "discrete": vk_type == _VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU,
                    "vulkan_device_type": _VK_DEVICE_TYPE_NAMES.get(vk_type, "UNKNOWN"),
                    "vendor_id": f"0x{dev['vendor_id']:04x}",
                    "vk_device_id": f"0x{dev['vk_device_id']:04x}",
                },
            )
        )
    return configs


def configure_webgpu_session_options(
    so: onnxruntime.SessionOptions,
    device: DeviceConfig,
) -> None:
    """Bind WebGpuExecutionProvider and target adapterIndex on SessionOptions."""
    if hasattr(onnxruntime, "get_ep_devices") and hasattr(so, "add_provider_for_devices"):
        target_dev = find_webgpu_ep_device()
        if target_dev is not None:
            opts = {
                "adapterIndex": str(device.device_index),
                "powerPreference": "high-performance",
            }
            so.add_provider_for_devices([target_dev], opts)
            logger.info("Bound WebGPU EP device: %s (adapterIndex=%s)", device.name, device.device_index)
