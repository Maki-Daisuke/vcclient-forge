import hashlib
import math
from collections.abc import Callable
from pathlib import Path
from threading import Lock, Thread

import requests

from vcclient.logger import logger

from ...exception import ERROR_CODE_MODULE_NOT_FOUND, VCClientError
from ..data_types.data_types import ModuleInfo, ModuleStatus
from ..data_types.module_manager_data_types import ModuleDownloadStatus
from ..voice_changer_const import ModuleDir

ModuleDownloadCallback = Callable[[ModuleDownloadStatus], None]
ModuleDownloadListCallback = Callable[[list[ModuleDownloadStatus]], None]

__all__ = [
    "ModuleDownloadCallback",
    "ModuleDownloadListCallback",
    "REGISTERED_MODULES",
    "RVC_REQUIRED_MODULES",
    "download_module",
    "download_rvc_modules",
    "get_module_filepath",
    "get_modules",
    "is_rvc_ready",
    "reload_modules",
]

REGISTERED_MODULES: list[ModuleInfo] = [
    ModuleInfo(
        id="contentvec-f.onnx",
        display_name="contentvec-f.onnx",
        url="https://huggingface.co/wok000/vcclient_modules/resolve/main/contentvec/contentvec-f.onnx",
        save_to=ModuleDir / Path("contentvec/contentvec-f.onnx"),
        hash="4b31ed3d95a568fab7952de923ff7f7d3d17128ea6fce69f665509d24c3156db",
    ),
    ModuleInfo(
        id="rinna_hubert_base-f.onnx",
        display_name="rinna_hubert_base-f.onnx",
        url="https://huggingface.co/wok000/vcclient_modules/resolve/main/rinna_hubert/rinna_hubert_base-f.onnx",
        save_to=ModuleDir / Path("rinna_hubert/rinna_hubert_base-f.onnx"),
        hash="d00e262757fa1550faac53fa6140dad16ca75603a36ecfead468920a9f744a16",
    ),
    ModuleInfo(
        id="rmvpe_20231006.onnx",
        display_name="rmvpe_20231006.onnx",
        url="https://huggingface.co/wok000/vcclient_modules/resolve/main/rmvpe/rmvpe_20231006.onnx",
        save_to=ModuleDir / Path("rmvpe/rmvpe_20231006.onnx"),
        hash="84f0586308e36157f75b77c8591bf636d6719c0c4ba95f8faf3df479e7566219",
    ),
    ModuleInfo(
        id="fcpe.onnx",
        display_name="fcpe.onnx",
        url="https://huggingface.co/gzivdo/fcpe-onnx/resolve/main/fcpe.onnx",
        save_to=ModuleDir / Path("fcpe/fcpe.onnx"),
        hash="b7e4f3871b10641869b7ac5a2d56ed94deb37552c0336d77e17ad6e66760adf0",
    ),
]

RVC_REQUIRED_MODULES = [
    "contentvec-f.onnx",
    "rinna_hubert_base-f.onnx",
    "rmvpe_20231006.onnx",
    "fcpe.onnx",
]

_module_status_list: list[ModuleStatus] = []
_download_threads: dict[str, Thread | None] = {}
_status_initialized: bool = False


def _get_target_module(id: str) -> ModuleInfo:
    for module in REGISTERED_MODULES:
        if module.id == id:
            return module
    raise VCClientError(ERROR_CODE_MODULE_NOT_FOUND, f"Module {id} is not registered")


def _check_hash(id: str) -> bool:
    target_module = _get_target_module(id)
    with open(target_module.save_to, "rb") as f:
        data = f.read()
        h = hashlib.sha256(data).hexdigest()
        if h != target_module.hash:
            logger.error("hash is not valid: valid:%s, incoming:%s", target_module.hash, h)
            return False
        return True


def get_module_filepath(id: str) -> Path:
    return _get_target_module(id).save_to


def reload_modules() -> None:
    global _module_status_list, _status_initialized
    _module_status_list = []
    for module_info in REGISTERED_MODULES:
        module_status = ModuleStatus(info=module_info, downloaded=False, valid=False)
        if module_info.save_to.exists():
            module_status.downloaded = True
            if _check_hash(module_info.id):
                module_status.valid = True
        _module_status_list.append(module_status)
    _status_initialized = True
    logger.info("Module status: %s", _module_status_list)


def get_modules() -> list[ModuleStatus]:
    global _status_initialized
    if not _status_initialized:
        reload_modules()
    return _module_status_list


def is_rvc_ready() -> bool:
    current_modules = get_modules()
    for module_id in RVC_REQUIRED_MODULES:
        status_match = [x for x in current_modules if x.info.id == module_id]
        if len(status_match) == 1:
            if not status_match[0].downloaded or not status_match[0].valid:
                return False
        else:
            return False
    return True


def _download(target_module: ModuleInfo, callback: ModuleDownloadCallback) -> None:
    target_module.save_to.parent.mkdir(parents=True, exist_ok=True)
    req = requests.get(target_module.url, stream=True, allow_redirects=True, timeout=(10.0, 60.0))
    content_length_header = req.headers.get("content-length")
    content_length = int(content_length_header) if content_length_header is not None else 1073741824
    chunk_size = 1048576
    chunk_num = math.ceil(content_length / chunk_size)

    try:
        with open(target_module.save_to, "wb") as f:
            for i, chunk in enumerate(req.iter_content(chunk_size=chunk_size)):
                f.write(chunk)
                callback(
                    ModuleDownloadStatus(
                        id=target_module.id, status="processing", progress=min(1, round((i + 1) / chunk_num, 2))
                    )
                )

        callback(
            ModuleDownloadStatus(
                id=target_module.id, status="validating", progress=min(1, round((i + 1) / chunk_num, 2))
            )
        )

        if not _check_hash(target_module.id):
            if target_module.save_to.exists():
                target_module.save_to.unlink(missing_ok=True)
            raise RuntimeError(f"Hash validation failed for module: {target_module.id}")
    except Exception as e:
        if target_module.save_to.exists():
            target_module.save_to.unlink(missing_ok=True)
        logger.error("Downloading error: %s, %s", target_module.id, e)
        callback(ModuleDownloadStatus(id=target_module.id, status="error", progress=1, error_message=str(e)))
        return

    logger.info("Downloading completed: %s", target_module.id)
    try:
        callback(ModuleDownloadStatus(id=target_module.id, status="done", progress=1))
    except Exception as e:
        logger.error("Failed to send completion callback for %s: %s", target_module.id, e)


def download_module(id: str, callback: ModuleDownloadCallback) -> None:
    logger.info("Downloading module: %s", id)
    target_module = _get_target_module(id)

    for exist_thread_id, exist_thread in list(_download_threads.items()):
        if exist_thread is None or exist_thread.is_alive():
            continue
        exist_thread.join()
        _download_threads.pop(exist_thread_id)

    if id in _download_threads:
        logger.error("Already downloading: %s", id)
        callback(
            ModuleDownloadStatus(id=id, status="error", progress=1, error_message=f"module is already downloading {id}")
        )
        return None

    _download_threads[id] = None
    logger.info("Start downloading: %s", id)
    t = Thread(target=_download, args=(target_module, callback))
    t.start()
    _download_threads[id] = t


def download_rvc_modules(callback: ModuleDownloadListCallback) -> None:
    rvc_modules = [x for x in get_modules() if x.info.id in RVC_REQUIRED_MODULES and x.valid is False]
    status_dict = {x.info.id: ModuleDownloadStatus(id=x.info.id, status="processing", progress=0) for x in rvc_modules}
    lock = Lock()

    def download_callback(status: ModuleDownloadStatus) -> None:
        with lock:
            status_dict[status.id] = status
            callback(list(status_dict.values()))

    for module in rvc_modules:
        download_module(module.info.id, download_callback)

    for threads in _download_threads.values():
        if threads is not None:
            threads.join()
    reload_modules()
