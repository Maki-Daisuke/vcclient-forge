import logging

from tqdm import tqdm

from vcclient.const import LOG_FILE, LOGGER_NAME
from vcclient.logger import setup_logger
from vcclient.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient.voice_changer.data_types.sample_manager_data_types import SampleDownloadStatus
from vcclient.voice_changer.module_manager.module_manager import ModuleManager
from vcclient.voice_changer.sample_manager.sample_manager import SampleManager
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager

setup_logger(LOGGER_NAME, LOG_FILE)


def _check_and_download_rvc_modules() -> None:
    module_manager = ModuleManager.get_instance()
    if module_manager.is_rvc_ready() is False:
        logging.getLogger(LOGGER_NAME).info("RVC is not ready. Downloading RVC modules.")
        print("RVC is not ready. Downloading RVC modules.")

        pbar_dict_module: dict[str, tqdm] = {}

        def download_callback(status: list[ModuleDownloadStatus]) -> None:
            position = 0
            for s in status:
                if s.id not in pbar_dict_module:
                    pbar_dict_module[s.id] = tqdm(
                        total=100, unit="%", desc=f"Downloading {s.id[:10]}", leave=False, position=position
                    )
                    position += 1
                pbar = pbar_dict_module[s.id]
                pbar.n = int(s.progress * 100)
                pbar.refresh()
                if s.status == "done":
                    pbar.close()

        module_manager.download_rvc_modules(download_callback)
        logging.getLogger(LOGGER_NAME).info("RVC is not ready. Downloading RVC modules. Done.")
        print("\n\nRVC is not ready. Downloading RVC modules. Done.")


def _check_and_convert_legacy_pth_models() -> None:
    slot_manager = SlotManager.get_instance()
    legacy_slots = slot_manager.find_legacy_pth_slots()
    if not legacy_slots:
        return

    logging.getLogger(LOGGER_NAME).info(f"Found {len(legacy_slots)} legacy .pth model(s). Converting to ONNX...")
    print(f"\nFound {len(legacy_slots)} legacy .pth model(s). Converting to ONNX...")

    pbar = tqdm(total=len(legacy_slots), desc="Converting models to ONNX", unit="model")
    try:
        for slot_index, pth_path in legacy_slots:
            pbar.set_postfix_str(f"Slot {slot_index}: {pth_path.stem[:15]}")
            try:
                slot_manager.convert_legacy_slot_to_onnx(slot_index, pth_path)
            except Exception as e:
                logging.getLogger(LOGGER_NAME).error(f"Failed to convert slot {slot_index} ({pth_path}): {e}")
                print(f"\nWarning: Failed to convert slot {slot_index} ({pth_path.name}): {e}")
            pbar.update(1)
    finally:
        pbar.close()

    slot_manager.reload()
    logging.getLogger(LOGGER_NAME).info("Legacy .pth models conversion done.")
    print("Legacy .pth models conversion done.\n")


def _cehck_and_download_initial_samples() -> None:
    slot_manager = SlotManager.get_instance()
    valid_slot_infos = [x for x in slot_manager.get_slot_infos() if x.voice_changer_type is not None]
    if len(valid_slot_infos) == 0:
        logging.getLogger(LOGGER_NAME).info("Sample is not ready. Downloading initial samples.")
        print("Sample is not ready. Downloading initial samples.")

        sample_manager = SampleManager.get_instance()
        pbar_dict_sample: dict[str, tqdm] = {}

        def download_callback(status: list[SampleDownloadStatus]) -> None:
            position = 0
            for s in status:
                if s.id not in pbar_dict_sample:
                    pbar_dict_sample[s.id] = tqdm(
                        total=100, unit="%", desc=f"Downloading {s.id[:10]}", leave=False, position=position
                    )
                    position += 1
                pbar = pbar_dict_sample[s.id]
                pbar.n = int(s.progress * 100)
                pbar.refresh()
                if s.status == "done":
                    pbar.close()

        sample_manager.download_initial_samples(download_callback)
        logging.getLogger(LOGGER_NAME).info("Sample is not ready. Downloading initial samples. Done.")
        print("\n\nSample is not ready. Downloading initial samples. Done.")
