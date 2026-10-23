import time

from tqdm import tqdm

from vcclient.logger import logger
from vcclient.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient.voice_changer.data_types.sample_manager_data_types import SampleDownloadStatus
from vcclient.voice_changer.module_manager.module_manager import ModuleManager
from vcclient.voice_changer.sample_manager.sample_manager import SampleManager
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager


def _check_and_download_rvc_modules() -> None:
    module_manager = ModuleManager.get_instance()
    if module_manager.is_rvc_ready() is False:
        logger.info("RVC is not ready. Downloading RVC modules.")
        print("RVC is not ready. Downloading RVC modules (parallel)...", flush=True)

        last_update = [0.0]

        def download_callback(status: list[ModuleDownloadStatus]) -> None:
            if not status:
                return
            now = time.monotonic()
            all_done = all(s.status == "done" for s in status)
            if not all_done and (now - last_update[0]) < 0.1:
                return
            last_update[0] = now

            total_progress = sum(s.progress for s in status) / len(status)
            total_pct = int(total_progress * 100)

            items = []
            for s in status:
                label = s.id.replace(".onnx", "").replace("-f", "")
                pct = int(s.progress * 100)
                if s.status == "done":
                    items.append(f"{label}: Done")
                elif s.status == "error":
                    items.append(f"{label}: Err")
                else:
                    items.append(f"{label}: {pct:>2}%")

            summary = " | ".join(items)
            print(f"\rDownloading RVC modules [{total_pct:>3}%]: {summary}", end="", flush=True)

        module_manager.download_rvc_modules(download_callback)
        logger.info("RVC is not ready. Downloading RVC modules. Done.")
        print("\nRVC is not ready. Downloading RVC modules. Done.\n", flush=True)


def _check_and_convert_legacy_pth_models() -> None:
    slot_manager = SlotManager.get_instance()
    legacy_slots = slot_manager.find_legacy_pth_slots()
    if not legacy_slots:
        return

    logger.info("Found %d legacy .pth model(s). Converting to ONNX...", len(legacy_slots))
    print(f"\nFound {len(legacy_slots)} legacy .pth model(s). Converting to ONNX...")

    pbar = tqdm(total=len(legacy_slots), desc="Converting models to ONNX", unit="model")
    try:
        for slot_index, pth_path in legacy_slots:
            pbar.set_postfix_str(f"Slot {slot_index}: {pth_path.stem[:15]}")
            try:
                slot_manager.convert_legacy_slot_to_onnx(slot_index, pth_path)
            except Exception as e:
                logger.error("Failed to convert slot %s (%s): %s", slot_index, pth_path, e)
                print(f"\nWarning: Failed to convert slot {slot_index} ({pth_path.name}): {e}")
            pbar.update(1)
    finally:
        pbar.close()

    slot_manager.reload()
    logger.info("Legacy .pth models conversion done.")
    print("Legacy .pth models conversion done.\n")


def _check_and_download_initial_samples() -> None:
    slot_manager = SlotManager.get_instance()
    valid_slot_infos = [x for x in slot_manager.get_slot_infos() if x.voice_changer_type is not None]
    if len(valid_slot_infos) == 0:
        logger.info("Sample is not ready. Downloading initial samples.")
        print("Sample is not ready. Downloading initial samples (parallel)...", flush=True)

        sample_manager = SampleManager.get_instance()
        last_update = [0.0]

        def download_callback(status: list[SampleDownloadStatus]) -> None:
            if not status:
                return
            now = time.monotonic()
            all_done = all(s.status == "done" for s in status)
            if not all_done and (now - last_update[0]) < 0.1:
                return
            last_update[0] = now

            total_progress = sum(s.progress for s in status) / len(status)
            total_pct = int(total_progress * 100)

            items = []
            for s in status:
                label = s.id.replace("_o", "")
                pct = int(s.progress * 100)
                if s.status == "done":
                    items.append(f"{label}: Done")
                else:
                    items.append(f"{label}: {pct:>2}%")

            summary = " | ".join(items)
            print(f"\rDownloading initial samples [{total_pct:>3}%]: {summary}", end="", flush=True)

        sample_manager.download_initial_samples(download_callback)
        logger.info("Sample is not ready. Downloading initial samples. Done.")
        print("\nSample is not ready. Downloading initial samples. Done.\n", flush=True)
