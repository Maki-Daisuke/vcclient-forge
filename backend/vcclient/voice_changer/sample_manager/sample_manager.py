import math
from collections.abc import Callable
from pathlib import Path
from threading import Lock, Thread

import requests

from vcclient.logger import logger

from ...exception import ERROR_CODE_SAMPLE_NOT_FOUND, VCClientError
from ...server.server_const import UPLOAD_DIR
from ..data_types.data_types import RVCSampleInfo
from ..data_types.sample_manager_data_types import SampleDownloadParam, SampleDownloadStatus
from ..data_types.slot_manager_data_types import RVCModelImportParam
from ..slot_manager.slot_manager import SlotManager

__all__ = [
    "SampleDownloadParam",
    "download_initial_samples",
    "download_sample",
    "get_samples",
]

_SAMPLES: list[RVCSampleInfo] = [
    RVCSampleInfo(
        id="KikotoKurage_o",
        voice_changer_type="RVC",
        lang="ja-JP",
        tag=["v2", "onnx"],
        name="黄琴海月(onnx)",
        model_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_kurage/kikoto_kurage_v2_40k_e100_float.onnx",
        index_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_kurage/added_IVF5181_Flat_nprobe_1_v2.index.bin",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/raw/main/rvc_v2_alpha/kikoto_kurage/terms_of_use.txt",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_kurage/kikoto_kurage.png",
        credit="黄琴海月",
        description="",
        sample_rate=40000,
        f0=True,
        inferencer_type="onnxRVC",
    ),
    RVCSampleInfo(
        id="KikotoMahiro_o",
        voice_changer_type="RVC",
        lang="ja-JP",
        tag=["v2", "onnx"],
        name="黄琴まひろ(onnx)",
        model_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_mahiro/kikoto_mahiro_v2_40k_float.onnx",
        index_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_mahiro/added_IVF6881_Flat_nprobe_1_v2.index.bin",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/raw/main/rvc_v2_alpha/kikoto_mahiro/terms_of_use.txt",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_mahiro/kikoto_mahiro.png",
        credit="黄琴まひろ",
        description="",
        sample_rate=40000,
        f0=True,
        inferencer_type="onnxRVC",
    ),
    RVCSampleInfo(
        id="TokinaShigure_o",
        voice_changer_type="RVC",
        lang="ja-JP",
        tag=["v2", "onnx"],
        name="刻鳴時雨(onnx)",
        model_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tokina_shigure/tokina_shigure_v2_40k_e100_float.onnx",
        index_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tokina_shigure/added_IVF2736_Flat_nprobe_1_v2.index.bin",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/raw/main/rvc_v2_alpha/tokina_shigure/terms_of_use.txt",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tokina_shigure/tokina_shigure.png",
        credit="刻鳴時雨",
        description="",
        sample_rate=40000,
        f0=True,
        inferencer_type="onnxRVC",
    ),
    RVCSampleInfo(
        id="Amitaro_o",
        voice_changer_type="RVC",
        lang="ja-JP",
        tag=["v2", "onnx"],
        name="あみたろ(onnx)",
        model_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/amitaro/amitaro_v2_40k_e100_float.onnx",
        index_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/amitaro/added_IVF3139_Flat_nprobe_1_v2.index.bin",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/raw/main/rvc_v2_alpha/amitaro/terms_of_use.txt",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/amitaro/amitaro.png",
        credit="あみたろ",
        description="",
        sample_rate=40000,
        f0=True,
        inferencer_type="onnxRVC",
    ),
    RVCSampleInfo(
        id="Tsukuyomi-chan_o",
        voice_changer_type="RVC",
        lang="ja-JP",
        tag=["v2", "onnx"],
        name="つくよみちゃん(onnx)",
        model_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tsukuyomi-chan/tsukuyomi_v2_40k_e100_float.onnx",
        index_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tsukuyomi-chan/added_IVF7852_Flat_nprobe_1_v2.index.bin",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/raw/main/rvc_v2_alpha/tsukuyomi-chan/terms_of_use.txt",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tsukuyomi-chan/tsukuyomi-chan.png",
        credit="つくよみちゃん",
        description="",
        sample_rate=40000,
        f0=True,
        inferencer_type="onnxRVC",
    ),
]


def get_samples() -> list[RVCSampleInfo]:
    return list(_SAMPLES)


def _download(
    upload_dir: Path,
    target_sample: RVCSampleInfo,
    callback: Callable[[SampleDownloadStatus], None],
    rvc_skip_index: bool = False,
) -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    download_urls = [target_sample.model_url]
    if target_sample.index_url is not None and rvc_skip_index is False:
        download_urls.append(target_sample.index_url)
    if target_sample.icon_url is not None:
        download_urls.append(target_sample.icon_url)

    for url_index, url in enumerate(download_urls):
        req = requests.get(url, stream=True, allow_redirects=True, timeout=(10.0, 60.0))
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

    callback(SampleDownloadStatus(id=target_sample.id, status="done", progress=1.0))


def download_sample(upload_dir: Path, param: SampleDownloadParam) -> None:
    slot_manager = SlotManager.get_instance()
    slot_manager.reserve_slot_for_sample(param.slot_index)
    samples = [x for x in _SAMPLES if x.id == param.sample_id]
    if len(samples) != 1:
        raise VCClientError(ERROR_CODE_SAMPLE_NOT_FOUND, f"Sample {param.sample_id} not found.")
    sample = samples[0]

    def callback(status: SampleDownloadStatus) -> None:
        logger.debug("Download status: %s", status)
        slot_manager.update_slot_for_sample(param.slot_index, status.progress)

    _download(upload_dir, sample, callback)

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


def download_initial_samples(callback: Callable[[list[SampleDownloadStatus]], None] | None = None) -> None:
    status_dict = {x.id: SampleDownloadStatus(id=x.id, status="processing", progress=0) for x in _SAMPLES}
    lock = Lock()

    def download_callback(status: SampleDownloadStatus) -> None:
        with lock:
            status_dict[status.id] = status
            if callback is not None:
                callback(list(status_dict.values()))

    threads: dict[str, Thread] = {}
    for sample in _SAMPLES:
        t = Thread(target=_download, args=(UPLOAD_DIR, sample, download_callback, True))
        t.start()
        threads[sample.id] = t

    for id, thread in threads.items():
        thread.join()
        logger.debug("Sample download status: %s done.", id)

    logger.debug("Sample download done.")

    for i, sample in enumerate(_SAMPLES):
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
