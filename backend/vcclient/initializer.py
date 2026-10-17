import logging

from tqdm import tqdm

from vcclient.const import LOG_FILE, LOGGER_NAME
from vcclient.logger import setup_logger
from vcclient.voice_changer.module_manager.module_manager import ModuleManager
from vcclient.voice_changer.sample_manager.sample_manager import SampleManager
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager

setup_logger(LOGGER_NAME, LOG_FILE)


def _check_and_download_rvc_modules():
    module_manager = ModuleManager.get_instance()
    if module_manager.is_rvc_ready() is False:
        logging.getLogger(LOGGER_NAME).info("RVC is not ready. Downloading RVC modules.")
        print("RVC is not ready. Downloading RVC modules.")

        pbar_dict_module = {}

        def download_callback(status=None):
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


def _cehck_and_download_initial_samples():
    slot_manager = SlotManager.get_instance()
    valid_slot_infos = [x for x in slot_manager.get_slot_infos() if x.voice_changer_type is not None]
    if len(valid_slot_infos) == 0:
        logging.getLogger(LOGGER_NAME).info("Sample is not ready. Downloading initial samples.")
        print("Sample is not ready. Downloading initial samples.")

        sample_manager = SampleManager.get_instance()
        pbar_dict_sample = {}

        def download_callback(status=None):
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
