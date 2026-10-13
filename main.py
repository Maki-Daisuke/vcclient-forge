import logging
import multiprocessing as mp
import platform
import signal
import sys
import time
from pathlib import Path

import fire

# Setup environment
_here = Path(__file__).parent.resolve()
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))


from vcclient_dev.app_status import AppStatus
from vcclient_dev.client_launcher.client_launcher import ClientLauncher
from vcclient_dev.const import LOG_FILE, LOGGER_NAME, VERSION
from vcclient_dev.cui.vcclient_cui import VCClientCUI
from vcclient_dev.initializer import _cehck_and_download_initial_samples, _check_and_download_rvc_modules
from vcclient_dev.logger import setup_logger
from vcclient_dev.proxy.ngrok_proxy_manager import NgrokProxyManager
from vcclient_dev.server.vcserver import VCServer
from vcclient_dev.utils.is_running_on_colab import is_running_on_colab
from vcclient_dev.utils.parseBoolArg import parse_bool_arg
from vcclient_dev.utils.resolve_url import resolve_base_url
from vcclient_dev.voice_changer.auido_device_manager.audio_device_manager import AudioDeviceManager
from vcclient_dev.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient_dev.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager
from vcclient_dev.voice_changer.module_manager.module_manager import ModuleDownloadStatus, ModuleManager
from vcclient_dev.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient_dev.voice_changer.voice_change_manager.voice_changer import VoiceChanger

setup_logger(LOGGER_NAME, LOG_FILE)
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

    vcserver = VCServer.get_instance(
        host=host,
        port=port,
        https=https,
        allow_origins=allow_origins,
    )
    vcserver_port = vcserver.start()

    proxy_url = None
    if ngrok_token:
        proxy_manager = NgrokProxyManager.get_instance()
        proxy_url = proxy_manager.start(token=ngrok_token, port=vcserver_port)
        if ngrok_proxy_url_file and proxy_url:
            with open(ngrok_proxy_url_file, "w", encoding="utf-8") as f:
                f.write(proxy_url)

    base_url = resolve_base_url(https, vcserver_port)
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

    print("--------------------------------------------------")
    print("Please open the following URL in your browser:")
    for label, u in urls:
        print(f"  {label.ljust(15)}: {u}")
    print("--------------------------------------------------")

    if launch_client and not is_running_on_colab():
        launcher = ClientLauncher(terminate_callback=vcserver.stop)
        launcher.launch(port=vcserver_port, https=https)

    if no_cui:
        print("Running in headless/no-CUI mode. Press Ctrl+C to terminate.")
        try:
            while not app_status.end_flag:
                time.sleep(1)
                conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
                lvc = LocalVoiceChangerInterface.get_instance()
                if conf.voice_changer_input_mode == "server_device":
                    if not lvc.local_voice_changer_enabled:
                        pass
        except KeyboardInterrupt:
            print("\nShutting down server...")
        finally:
            vcserver.stop()
            VoiceChanger.get_instance().stop_convert_chunk_bulk()
    else:
        try:
            cui = VCClientCUI(port=vcserver_port, https=https, terminate_callback=vcserver.stop)
            cui.run()
        except Exception as e:
            logger.error(f"CUI Error: {e}")
        finally:
            vcserver.stop()
            VoiceChanger.get_instance().stop_convert_chunk_bulk()


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
