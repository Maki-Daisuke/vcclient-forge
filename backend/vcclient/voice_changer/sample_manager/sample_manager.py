import logging
import math
import platform
from pathlib import Path
from threading import Thread
from typing import Callable

import requests

from vcclient.voice_changer.voice_chanager_const import BEATRICE_V2_ALPHA_SLOT_INDEX, BEATRICE_V2_BETA_SLOT_INDEX

from ...const import LOGGER_NAME
from ...exception import ERROR_CODE_SAMPLE_NOT_FOUND, VCClientError
from ...server.server_const import UPLOAD_DIR
from ..data_types.data_types import BeatriceV2SampleInfo, RVCSampleInfo, SampleInfoMember
from ..data_types.sample_manager_data_types import SampleDownloadParam, SampleDownloadStatus
from ..data_types.slot_manager_data_types import BeatriceV2ModelImportParam, RVCModelImportParam
from ..slot_manager.slot_manager import SlotManager
from .sample_beatricev2 import SAMPLE_BEATRICE_V2_ALPHA
from .sample_rvc_onnx import SAMPLE_RVC_ONNX


class SampleManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.sample_list = []
        self.reload()

    def reload(self):
        self.sample_list = []
        self.sample_list.extend(SAMPLE_RVC_ONNX)
        self.sample_list.extend(SAMPLE_BEATRICE_V2_ALPHA)

    def get_samples(self):
        return self.sample_list

    def _download(
        self,
        upload_dir: Path,
        target_sample: SampleInfoMember,
        callback: Callable[[SampleDownloadStatus], None],
        rvc_skip_index: bool = False,
    ):
        upload_dir.mkdir(parents=True, exist_ok=True)
        if target_sample.voice_changer_type == "RVC":
            assert isinstance(target_sample, RVCSampleInfo)
            download_urls = []
            download_urls.append(target_sample.model_url)
            if target_sample.index_url is not None and rvc_skip_index is False:
                download_urls.append(target_sample.index_url)
            if target_sample.icon_url is not None:
                download_urls.append(target_sample.icon_url)

            for url_index, url in enumerate(download_urls):
                req = requests.get(url, stream=True, allow_redirects=True)
                content_length_header = req.headers.get("content-length")
                if content_length_header is not None:
                    content_length = int(content_length_header)
                else:
                    content_length = 1073741824

                chunk_size = 1048576
                chunk_num = math.ceil(content_length / chunk_size)
                save_to = upload_dir / url.split("/")[-1]

                with open(save_to, "wb") as f:
                    for i, chunk in enumerate(req.iter_content(chunk_size=chunk_size)):
                        f.write(chunk)
                        file_progress = min(1, round((i + 1) / chunk_num, 2))
                        progress = round((file_progress / len(download_urls)) + (1 / len(download_urls) * url_index), 2)
                        callback(SampleDownloadStatus(id=target_sample.id, status="processing", progress=progress))

        elif target_sample.voice_changer_type == "Beatrice_v2":
            assert isinstance(target_sample, BeatriceV2SampleInfo)
            download_urls = []
            download_urls.append(target_sample.zip_url)
            if target_sample.icon_url is not None:
                download_urls.append(target_sample.icon_url)

            for url_index, url in enumerate(download_urls):
                req = requests.get(url, stream=True, allow_redirects=True)
                content_length_header = req.headers.get("content-length")
                if content_length_header is not None:
                    content_length = int(content_length_header)
                else:
                    content_length = 1073741824

                chunk_size = 1048576
                chunk_num = math.ceil(content_length / chunk_size)
                save_to = upload_dir / url.split("/")[-1]

                with open(save_to, "wb") as f:
                    for i, chunk in enumerate(req.iter_content(chunk_size=chunk_size)):
                        f.write(chunk)
                        file_progress = min(1, round((i + 1) / chunk_num, 2))
                        progress = round((file_progress / len(download_urls)) + (1 / len(download_urls) * url_index), 2)
                        callback(SampleDownloadStatus(id=target_sample.id, status="processing", progress=progress))

    def download(self, upload_dir: Path, param: SampleDownloadParam):
        slot_manager = SlotManager.get_instance()
        slot_manager.reserve_slot_for_sample(param.slot_index)
        samples = [x for x in self.sample_list if x.id == param.sample_id]
        if len(samples) != 1:
            raise VCClientError(ERROR_CODE_SAMPLE_NOT_FOUND, f"Sample {param.sample_id} not found.")
        sample = samples[0]

        def callback(status: SampleDownloadStatus):
            logging.getLogger(LOGGER_NAME).debug(f"Download status: {status}")
            slot_manager.update_slot_for_sample(param.slot_index, status.progress)

        self._download(upload_dir, sample, callback)

        if sample.voice_changer_type == "RVC":
            assert isinstance(sample, RVCSampleInfo)
            import_params = RVCModelImportParam(
                slot_index=param.slot_index,
                name=sample.name,
                terms_of_use_url=sample.terms_of_use_url,
                model_file=upload_dir / sample.model_url.split("/")[-1],
                index_file=upload_dir / sample.index_url.split("/")[-1] if sample.index_url is not None else None,
                icon_file=upload_dir / sample.icon_url.split("/")[-1] if sample.icon_url is not None else None,
            )
            slot_manager.release_slot_from_reseved_for_sample(param.slot_index)
            slot_manager.set_new_slot(import_params)

    def download_initial_samples(self, callback: Callable[[list[SampleDownloadStatus]], None] = None):
        if platform.system() == "Windows":
            INITIAL_SAMPLES = [
                "KikotoKurage_o",
                "KikotoMahiro_o",
                "TokinaShigure_o",
                "Amitaro_o",
                "Tsukuyomi-chan_o",
                "beatriceV2Alpha",
                "beatriceV2Beta",
            ]
        elif platform.system() == "Linux":
            INITIAL_SAMPLES = [
                "KikotoKurage_o",
                "KikotoMahiro_o",
                "TokinaShigure_o",
                "Amitaro_o",
                "Tsukuyomi-chan_o",
                "beatriceV2Alpha",
                "beatriceV2Beta",
            ]
        elif platform.system() == "Darwin":
            INITIAL_SAMPLES = ["Amitaro_t", "Tsukuyomi-chan_o", "beatriceV2Beta"]
        else:
            logging.getLogger(LOGGER_NAME).error(f"Unknown platform:{platform.system()}")
            INITIAL_SAMPLES = [
                "KikotoKurage_o",
                "KikotoMahiro_o",
                "TokinaShigure_o",
                "Amitaro_o",
                "Tsukuyomi-chan_o",
                "beatriceV2Alpha",
            ]

        initial_samples = [x for x in self.sample_list if x.id in INITIAL_SAMPLES]
        status_dict = {x.id: SampleDownloadStatus(id=x.id, status="processing", progress=0) for x in initial_samples}

        def download_callback(status: SampleDownloadStatus):
            status_dict[status.id] = status
            if callback is not None:
                callback(list(status_dict.values()))

        self.threads = {}
        for sample in initial_samples:
            t = Thread(target=self._download, args=(UPLOAD_DIR, sample, download_callback, True))
            t.start()
            self.threads[sample.id] = t

        for id, thread in self.threads.items():
            thread.join()
            logging.getLogger(LOGGER_NAME).debug(f"Sample download status: {id} done.")

        logging.getLogger(LOGGER_NAME).debug("Sample download done.")

        for i, sample in enumerate(initial_samples):
            if sample.voice_changer_type == "RVC":
                assert isinstance(sample, RVCSampleInfo)
                import_params = RVCModelImportParam(
                    slot_index=i,
                    name=sample.name,
                    terms_of_use_url=sample.terms_of_use_url,
                    model_file=UPLOAD_DIR / sample.model_url.split("/")[-1],
                    index_file=None,
                    icon_file=UPLOAD_DIR / sample.icon_url.split("/")[-1] if sample.icon_url is not None else None,
                )
                slot_manager = SlotManager.get_instance()
                slot_manager.set_new_slot(import_params, remove_src=True)
            elif sample.voice_changer_type == "Beatrice_v2":
                assert isinstance(sample, BeatriceV2SampleInfo)
                if sample.id == "beatriceV2Alpha":
                    import_params = BeatriceV2ModelImportParam(
                        slot_index=BEATRICE_V2_ALPHA_SLOT_INDEX,
                        name=sample.name,
                        terms_of_use_url=sample.terms_of_use_url,
                        icon_file=UPLOAD_DIR / sample.icon_url.split("/")[-1] if sample.icon_url is not None else None,
                        zip_file=UPLOAD_DIR / sample.zip_url.split("/")[-1],
                    )
                elif sample.id == "beatriceV2Beta":
                    import_params = BeatriceV2ModelImportParam(
                        slot_index=BEATRICE_V2_BETA_SLOT_INDEX,
                        name=sample.name,
                        terms_of_use_url=sample.terms_of_use_url,
                        icon_file=UPLOAD_DIR / sample.icon_url.split("/")[-1] if sample.icon_url is not None else None,
                        zip_file=UPLOAD_DIR / sample.zip_url.split("/")[-1],
                    )
                else:
                    raise VCClientError(ERROR_CODE_SAMPLE_NOT_FOUND, f"Sample {sample.id} not found.")
                slot_manager = SlotManager.get_instance()
                slot_manager.set_new_slot(import_params, remove_src=True)
