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


class ModuleManager:
    _instance: ModuleManager | None = None
    module_status_list: list[ModuleStatus] = []
    threads: dict[str, Thread | None]

    @classmethod
    def get_instance(cls) -> ModuleManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.module_status_list = []
        self.threads = {}
        self.reload()
        logger.info("Initial module status: %s", self.module_status_list)

    def reload(self) -> None:
        self.module_status_list = []
        for module_info in REGISTERED_MODULES:
            module_status = ModuleStatus(info=module_info, downloaded=False, valid=False)
            if module_info.save_to.exists():
                module_status.downloaded = True
                if self._check_hash(module_info.id):
                    module_status.valid = True
            self.module_status_list.append(module_status)

    def get_modules(self) -> list[ModuleStatus]:
        return self.module_status_list

    def _download(self, target_module: ModuleInfo, callback: ModuleDownloadCallback) -> None:
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

            if not self._check_hash(target_module.id):
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

    def _get_target_module(self, id: str) -> ModuleInfo:
        for module in REGISTERED_MODULES:
            if module.id == id:
                return module
        raise VCClientError(ERROR_CODE_MODULE_NOT_FOUND, f"Module {id} is not registered")

    def download(self, id: str, callback: ModuleDownloadCallback) -> None:
        logger.info("Downloading module: %s", id)
        target_module = self._get_target_module(id)

        for exist_thread_id, exist_thread in list(self.threads.items()):
            if exist_thread is None or exist_thread.is_alive():
                continue
            exist_thread.join()
            self.threads.pop(exist_thread_id)

        if id in self.threads:
            logger.error("Already downloading: %s", id)
            callback(
                ModuleDownloadStatus(
                    id=id, status="error", progress=1, error_message=f"module is already downloading {id}"
                )
            )
            return None

        self.threads[id] = None
        logger.info("Start downloading: %s", id)
        t = Thread(target=self._download, args=(target_module, callback))
        t.start()
        self.threads[id] = t

    def _check_hash(self, id: str) -> bool:
        target_module = self._get_target_module(id)
        with open(target_module.save_to, "rb") as f:
            data = f.read()
            hash = hashlib.sha256(data).hexdigest()
            if hash != target_module.hash:
                logger.error("hash is not valid: valid:%s, incoming:%s", target_module.hash, hash)
                return False
            return True

    def get_module_filepath(self, id: str) -> Path:
        return self._get_target_module(id).save_to

    def is_rvc_ready(self) -> bool:
        for module_id in RVC_REQUIRED_MODULES:
            module_status = [x for x in self.module_status_list if x.info.id == module_id]
            if len(module_status) == 1:
                if not module_status[0].downloaded or not module_status[0].valid:
                    return False
            else:
                return False
        return True

    def download_rvc_modules(self, callback: ModuleDownloadListCallback) -> None:
        rvc_modules = [x for x in self.get_modules() if x.info.id in RVC_REQUIRED_MODULES and x.valid is False]
        status_dict = {
            x.info.id: ModuleDownloadStatus(id=x.info.id, status="processing", progress=0) for x in rvc_modules
        }
        lock = Lock()

        def download_callback(status: ModuleDownloadStatus) -> None:
            with lock:
                status_dict[status.id] = status
                callback(list(status_dict.values()))

        for module in rvc_modules:
            self.download(module.info.id, download_callback)

        for threads in self.threads.values():
            if threads is not None:
                threads.join()
        self.reload()
