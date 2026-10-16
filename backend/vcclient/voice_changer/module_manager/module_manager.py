import hashlib
import logging
import math
from pathlib import Path
from threading import Thread
from typing import Callable

import requests

from ...const import LOGGER_NAME
from ...exception import ERROR_CODE_MODULE_NOT_FOUND, VCClientError
from ..data_types.data_types import ModuleInfo, ModuleStatus
from ..data_types.module_manager_data_types import ModuleDownloadStatus
from ..voice_chanager_const import ModuleDir

REGISTERD_MODULES: list[ModuleInfo] = [
    ModuleInfo(
        id="hubert_base.pt",
        display_name="hubert_base.pt",
        url="https://huggingface.co/wok000/vcclient_modules/resolve/main/contentvec/hubert_base.pt",
        save_to=ModuleDir / Path("contentvec/hubert_base.pt"),
        hash="f54b40fd2802423a5643779c4861af1e9ee9c1564dc9d32f54f20b5ffba7db96",
    ),
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
        hash="acbe8d2e28c15372bd82248ce07827514730a19073f34269fd3b8a6c42324310",
    ),
    ModuleInfo(
        id="applio_japanese_hubert_base.pt",
        display_name="applio_japanese_hubert_base.pt",
        url="https://huggingface.co/IAHispano/Applio/resolve/main/Resources/embedders/japanese_hubert_base.pt",
        save_to=ModuleDir / Path("applio/applio_japanese_hubert_base.pt"),
        hash="dade3cf824ae0d214f7de8b73e70bae7c101e81f12d93577c4760bf516db4063",
    ),
    ModuleInfo(
        id="applio_chinese_hubert_base.pt",
        display_name="applio_chinese_hubert_base.pt",
        url="https://huggingface.co/IAHispano/Applio/resolve/main/Resources/embedders/chinese_hubert_base.pt",
        save_to=ModuleDir / Path("applio/applio_chinese_hubert_base.pt"),
        hash="8cd5db6302ae2e79b5972cd02ae375a42a76170374d6e1952fa78d1fe4e4f756",
    ),
    ModuleInfo(
        id="applio_korean_hubert_base.pt",
        display_name="applio_korean_hubert_base.pt",
        url="https://huggingface.co/IAHispano/Applio/resolve/main/Resources/embedders/korean_hubert_base.pt",
        save_to=ModuleDir / Path("applio/applio_korean_hubert_base.pt"),
        hash="6b42c8453b96b203198c1c280a8821158ea3fa8dbbc2a6220cad1c1489c3e65e",
    ),
]

RVC_REQUIRED_MODULES = [
    "contentvec-f.onnx",
    "rinna_hubert_base-f.onnx",
    "rmvpe_20231006.onnx",
]

APPLIO_MODULES = ["applio_japanese_hubert_base.pt", "applio_chinese_hubert_base.pt", "applio_korean_hubert_base.pt"]


class ModuleManager:
    _instance = None

    module_status_list: list[ModuleStatus] = []

    @classmethod
    def get_instance(cls):

        if cls._instance is None:
            cls._instance = cls()

            return cls._instance

        return cls._instance

    def __init__(self):

        self.module_status_list = []

        self.threads = {}

        self.reload()

        logging.getLogger(LOGGER_NAME).info(f"""Initial module status: {self.module_status_list}""")

    def reload(self):

        self.module_status_list = []

        for module_info in REGISTERD_MODULES:
            module_status = ModuleStatus(info=module_info, downloaded=False, valid=False)

            if module_info.save_to.exists():
                module_status.downloaded = True

                if self._check_hash(module_info.id):
                    module_status.valid = True

            self.module_status_list.append(module_status)

    def get_modules(self):

        return self.module_status_list

    def _download(self, target_module=None, callback=None):

        target_module.save_to.parent.mkdir(parents=True, exist_ok=True)

        req = requests.get(target_module.url, stream=True, allow_redirects=True)

        content_length_header = req.headers.get("content-length")

        content_length = int(content_length_header) if content_length_header is not None else 1073741824

        chunk_size = 1048576

        chunk_num = math.ceil(content_length / chunk_size)

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
        try:
            self._check_hash(target_module.id)
            logging.getLogger(LOGGER_NAME).info(f"Downloading completed: {target_module.id}")
            callback(ModuleDownloadStatus(id=target_module.id, status="done", progress=1))
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Downloading error: {target_module.id}, {e}")
            callback(ModuleDownloadStatus(id=target_module.id, status="error", progress=1, error_message=str(e)))

    def _get_target_module(self, id: str):
        target_module = None
        for module in REGISTERD_MODULES:
            if module.id == id:
                target_module = module
                return target_module
        return target_module

    def download(self, id: str, callback: Callable[[ModuleDownloadStatus], None]):
        logging.getLogger(LOGGER_NAME).info(f"Downloading module: {id}")
        target_module = self._get_target_module(id)
        if target_module is None:
            logging.getLogger(LOGGER_NAME).error(f"No such module: {id}")
            callback(ModuleDownloadStatus(id=id, status="error", progress=1, error_message=f"module not found {id}"))
            return None

        for exist_trehad_id, exist_thread in list(self.threads.items()):
            if exist_thread is None or exist_thread.is_alive():
                continue
            exist_thread.join()
            self.threads.pop(exist_trehad_id)

        if id in self.threads:
            logging.getLogger(LOGGER_NAME).error(f"Already downloading: {id}")
            callback(
                ModuleDownloadStatus(
                    id=id, status="error", progress=1, error_message=f"module is already downloading {id}"
                )
            )
            return None

        self.threads[id] = None
        logging.getLogger(LOGGER_NAME).info(f"Start downloading: {id}")
        t = Thread(target=self._download, args=(target_module, callback))
        t.start()
        self.threads[id] = t

    def _check_hash(self, id: str):
        target_module = self._get_target_module(id)
        if target_module is None:
            raise VCClientError(ERROR_CODE_MODULE_NOT_FOUND, f"Module {id} not found")
        with open(target_module.save_to, "rb") as f:
            data = f.read()
            hash = hashlib.sha256(data).hexdigest()
            if hash != target_module.hash:
                logging.getLogger(LOGGER_NAME).error(f"hash is not valid: valid:{target_module.hash}, incoming:{hash}")
                return False
            return True

    def get_module_filepath(self, id: str):
        target_module = self._get_target_module(id)
        if target_module is None:
            return None
        return target_module.save_to

    def is_rvc_ready(self):
        for module_id in RVC_REQUIRED_MODULES:
            module_status = [x for x in self.module_status_list if x.info.id == module_id]
            if len(module_status) == 1:
                if not module_status[0].downloaded or not module_status[0].valid:
                    return False
            else:
                return False
        return True

    def download_rvc_modules(self, callback: Callable[[list[ModuleDownloadStatus]], None]):
        rvc_modules = [x for x in self.get_modules() if x.valid is False]
        status_dict = {
            x.info.id: ModuleDownloadStatus(id=x.info.id, status="processing", progress=0) for x in rvc_modules
        }

        def download_callback(status: ModuleDownloadStatus):
            status_dict[status.id] = status
            callback(list(status_dict.values()))

        for module in rvc_modules:
            self.download(module.info.id, download_callback)

        for threads in self.threads.values():
            if threads is not None:
                threads.join()
        print("module download fin!")

    def applio_modules_ready(self):
        applio_modules = [x for x in self.get_modules() if x.info.id in APPLIO_MODULES and x.valid is False]
        if len(applio_modules) == 0:
            return True
        return False

    def download_applio_modules(self, callback=None):

        applio_modules = [x for x in self.get_modules() if x.info.id in APPLIO_MODULES and x.valid is False]
        status_dict = {
            x.info.id: ModuleDownloadStatus(id=x.info.id, status="processing", progress=0) for x in applio_modules
        }

        def download_callback(status=None):

            status_dict[status.id] = status

            callback(list(status_dict.values()))

        for module in applio_modules:
            self.download(module.info.id, download_callback)

        for threads in self.threads.values():
            threads.join()

        print("module download fin!")
