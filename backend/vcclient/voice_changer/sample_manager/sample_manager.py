import math
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import Lock, Thread

import requests

from vcclient.logger import logger

from ..configuration_manager.configuration_manager import ConfigurationManager
from ..data_types.data_types import RVCSampleInfo
from ..data_types.sample_manager_data_types import SampleDownloadStatus
from ..model_catalog import create_model

__all__ = [
    "download_initial_samples",
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
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_kurage/kikoto_kurage.png",
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
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/kikoto_mahiro/kikoto_mahiro.png",
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
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tokina_shigure/tokina_shigure.png",
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
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/amitaro/amitaro.png",
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
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/rvc_v2_alpha/tsukuyomi-chan/tsukuyomi-chan.png",
        sample_rate=40000,
        f0=True,
        inferencer_type="onnxRVC",
    ),
]


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


def download_initial_samples(callback: Callable[[list[SampleDownloadStatus]], None] | None = None) -> None:
    status_dict = {x.id: SampleDownloadStatus(id=x.id, status="processing", progress=0) for x in _SAMPLES}
    lock = Lock()

    def download_callback(status: SampleDownloadStatus) -> None:
        with lock:
            status_dict[status.id] = status
            if callback is not None:
                callback(list(status_dict.values()))

    with tempfile.TemporaryDirectory() as tmpdir:
        download_dir = Path(tmpdir)
        threads: dict[str, Thread] = {}
        for sample in _SAMPLES:
            t = Thread(target=_download, args=(download_dir, sample, download_callback, True))
            t.start()
            threads[sample.id] = t

        for id, thread in threads.items():
            thread.join()
            logger.debug("Sample download status: %s done.", id)

        logger.debug("Sample download done.")

        first_model_id: str | None = None
        for sample in _SAMPLES:
            model_path = download_dir / sample.model_url.split("/")[-1]
            icon_path = download_dir / sample.icon_url.split("/")[-1] if sample.icon_url is not None else None
            created, _ = create_model(
                name=sample.name,
                model_path=model_path,
                index_path=None,
                icon_path=icon_path,
            )
            if first_model_id is None:
                first_model_id = created.id

        if first_model_id is not None:
            cm = ConfigurationManager._instance
            if cm is not None and cm.voice_changer_configuration.model_id is None:
                cm.voice_changer_configuration.model_id = first_model_id
                cm.voice_changer_configuration.current_slot_index = -1
