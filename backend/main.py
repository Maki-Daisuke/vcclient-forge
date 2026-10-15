import logging
import multiprocessing as mp
import platform
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

# Ensure the project root is in sys.path regardless of execution context
_here = Path(__file__).parent.resolve()
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import fire
import sounddevice as sd

from vcclient.app_status import AppStatus
from vcclient.client_launcher.client_launcher import ClientLauncher
from vcclient.const import LOGGER_NAME, VERSION
from vcclient.cui.vcclient_cui import VCClientCUI
from vcclient.initializer import _cehck_and_download_initial_samples, _check_and_download_rvc_modules
from vcclient.logger import setup_logger
from vcclient.proxy.ngrok_proxy_manager import NgrokProxyManager
from vcclient.server.vcserver import VCServer
from vcclient.utils.is_running_on_colab import is_running_on_colab
from vcclient.utils.parseBoolArg import parse_bool_arg
from vcclient.utils.resolve_url import resolve_base_url
from vcclient.voice_changer.auido_device_manager.audio_device_manager import AudioDeviceManager
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager
from vcclient.voice_changer.module_manager.module_manager import ModuleDownloadStatus, ModuleManager
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

setup_logger()
logger = logging.getLogger(LOGGER_NAME)


def gradient_text(text, start_color=(0, 255, 255), end_color=(255, 0, 255)):
    lines = text.splitlines()
    res = []
    n = max(len(lines), 1)
    for i, line in enumerate(lines):
        r = int(start_color[0] + (end_color[0] - start_color[0]) * (i / n))
        g = int(start_color[1] + (end_color[1] - start_color[1]) * (i / n))
        b = int(start_color[2] + (end_color[2] - start_color[2]) * (i / n))
        res.append(f"\033[38;2;{r};{g};{b}m{line}\033[0m")
    return "\n".join(res)


def ignore_ctrl_c():
    if platform.system() == "Windows":
        signal.signal(signal.SIGINT, signal.SIG_IGN)


def download_progreess(status: list[ModuleDownloadStatus]):
    for s in status:
        if s.status == "done":
            pass


def module_download(callback=None):
    mm = ModuleManager.get_instance()
    mm.download_rvc_modules(callback or download_progreess)


def download_applio_modules(callback=None):
    mm = ModuleManager.get_instance()
    mm.download_applio_modules(callback or download_progreess)


def start_cui(
    host: str = "0.0.0.0",
    port: int = 18888,
    https: bool = False,
    launch_client: bool = True,
    allow_origins: str = "*",
    no_cui: bool = False,
    ngrok_token: str = None,
    ngrok_proxy_url_file: str = None,
):
    https = parse_bool_arg(https)
    launch_client = parse_bool_arg(launch_client)
    no_cui = parse_bool_arg(no_cui)

    logger.info(f"VCClient Version: {VERSION}")
    print(f"VCClient Version: {VERSION}")

    _check_and_download_rvc_modules()
    _cehck_and_download_initial_samples()

    gpu_manager = GPUDeviceManager.get_instance()
    audio_manager = AudioDeviceManager.get_instance()
    app_status = AppStatus.get_instance()

    vcserver = VCServer(
        host=host,
        port=port,
        https=https,
        allow_origins=[allow_origins] if allow_origins else None,
    )
    vcserver_port = vcserver.start()

    proxy_manager = None
    proxy_url = None
    if ngrok_token:
        proxy_manager = NgrokProxyManager.get_instance()
        proxy_url = proxy_manager.start(token=ngrok_token, port=vcserver_port)
        if ngrok_proxy_url_file and proxy_url:
            with open(ngrok_proxy_url_file, "w", encoding="utf-8") as f:
                f.write(proxy_url)

    cui = None
    app = None
    if not no_cui and platform.system() != "Darwin":
        app = VCClientCUI(port=vcserver_port, https=https, terminate_callback=app_status.stop_app)
        cui = threading.Thread(target=app.run)
        cui.start()
    else:
        base_url = resolve_base_url(https, vcserver_port)
        bold_green_start = "\x1b[1;32m"
        bold_red_start = "\x1b[1;31m"
        reset = "\x1b[0m"
        urls = [
            ["Application", base_url],
            ["Log(rich)", f"{base_url}/?app_mode=LogViewer"],
            ["Log(text)", f"{base_url}/vcclient.log"],
            ["API", f"{base_url}/docs"],
            ["License(js)", f"{base_url}/licenses-js.json"],
            ["License(py)", f"{base_url}/licenses-py.json"],
        ]
        if proxy_url:
            urls.append(["Ngrok", proxy_url])

        key_max_length = max(len(u[0]) for u in urls)
        url_max_length = max(len(u[1]) for u in urls)
        box_width = key_max_length + url_max_length + 5

        print("-" * box_width)
        for u in urls:
            print(f" {bold_green_start}{u[0].ljust(key_max_length)}{reset} | {u[1]} ")
        print("-" * box_width)
        print(f"{bold_green_start}Please press Ctrl+C once to exit vcclient.{reset}")

    if launch_client and not is_running_on_colab():
        client_launcher = ClientLauncher(app_status.stop_app)
        client_launcher.launch(vcserver_port, https)

    if is_running_on_colab():
        while not app_status.end_flag:
            current_time = time.strftime("%Y/%m/%d %H:%M:%S")
            logging.getLogger(LOGGER_NAME).info(f"{current_time}: running...")
            if app_status.end_flag is True:
                break
            time.sleep(60)
    else:
        bold_red_start = "\x1b[1;31m"
        reset = "\x1b[0m"
        err_msg = ""
        while not app_status.end_flag:
            try:
                conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
                local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
                if conf.voice_changer_input_mode == "server":
                    if local_voice_changer_interface.local_voice_changer_enabled is True:
                        local_voice_changer_interface.run()
                if app_status.end_flag is True:
                    break
                time.sleep(0.3)
            except KeyboardInterrupt:
                err_msg = "KeyboardInterrupt"
                break
            except sd.PortAudioError as e:
                err_msg = f"sound device error:{e}"
                logging.getLogger(LOGGER_NAME).error(f"Error:{e}")
                logging.getLogger(LOGGER_NAME).error(f"traceback:{traceback.format_exc()}")
                wasapi_not_supported_msg = (
                    "If you are using WASAPI or ASIO, your device might not be compatible with it. "
                    "Please try using MME instead."
                )
                logging.getLogger(LOGGER_NAME).error(wasapi_not_supported_msg)
                print(err_msg)
                print(f" {bold_red_start}{wasapi_not_supported_msg}{reset} ")
                local_voice_changer_interface.stop()
                time.sleep(1)
            except Exception as e:
                err_msg = f"Error:{e}"
                logging.getLogger(LOGGER_NAME).error(f"Error:{e}")
                logging.getLogger(LOGGER_NAME).error(f"traceback:{traceback.format_exc()}")
                print(err_msg)
                local_voice_changer_interface.stop()
                time.sleep(1)

    bold_green_start = "\x1b[1;32m"
    reset = "\x1b[0m"
    print(f"{bold_green_start}terminate vcclient...{reset}")

    def ignore_ctrl_c(signum, frame):
        pass

    original_handler = signal.signal(signal.SIGINT, ignore_ctrl_c)
    try:
        app_status.stop_app()
        if not no_cui and platform.system() != "Darwin" and cui is not None:
            if cui.is_alive():
                if app is not None and hasattr(app, "action_quit_server"):
                    app.action_quit_server()
                cui.join()
        vcserver.stop()
        VoiceChanger.get_instance().stop_convert_chunk_bulk()
        if proxy_manager is not None:
            proxy_manager.stop()
    finally:
        print("")
        signal.signal(signal.SIGINT, original_handler)


def rest_client():
    print("REST Client interactive mode is currently not implemented.")


def convert_file(src: str, dst: str, slot: int = 0):
    print(f"Converting {src} -> {dst} using slot {slot}")


def main():
    mp.freeze_support()
    fire.Fire(
        {
            "module_download": module_download,
            "cui": start_cui,
            "download_applio_modules": download_applio_modules,
            "rest_client": rest_client,
            "convert_file": convert_file,
        }
    )


if __name__ == "__main__":
    main()
