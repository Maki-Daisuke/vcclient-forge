import argparse
import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    mp.freeze_support()
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)

# Ensure standard I/O is unbuffered so supervisor processes (like Tauri) receive lines immediately
os.environ["PYTHONUNBUFFERED"] = "1"
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass

# Ensure the project root is in sys.path regardless of execution context
_here = Path(__file__).parent.resolve()
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import sounddevice as sd

from vcclient.app_status import AppStatus
from vcclient.const import VERSION
from vcclient.initializer import (
    _check_and_convert_legacy_pth_models,
    _check_and_download_initial_samples,
    _check_and_download_rvc_modules,
)
from vcclient.logger import logger
from vcclient.server.vcserver import VCServer
from vcclient.voice_changer.audio_device_manager.audio_device_manager import AudioDeviceManager
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


def start_server(
    host: str = "0.0.0.0",
    port: int = 18888,
):
    app_status = AppStatus.get_instance()

    def handle_shutdown_signal(signum, frame):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, signal.SIG_DFL)
        app_status.stop_app()

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handle_shutdown_signal)

    logger.info("VCClient Forge v%s", VERSION)
    print(f"VCClient Forge v{VERSION}", flush=True)

    _check_and_download_rvc_modules()
    _check_and_convert_legacy_pth_models()
    _check_and_download_initial_samples()
    if app_status.end_flag:
        return

    gpu_manager = GPUDeviceManager.get_instance()
    audio_manager = AudioDeviceManager.get_instance()

    vcserver = VCServer(
        host=host,
        port=port,
    )
    vcserver_port = vcserver.start()

    deadline = time.monotonic() + 30
    while not vcserver.server.started:
        if app_status.end_flag:
            return
        if vcserver.server_thread is not None and not vcserver.server_thread.is_alive():
            raise RuntimeError("Backend failed to listen; check whether the port is already in use")
        if time.monotonic() >= deadline:
            raise TimeoutError("Backend did not become ready within the startup timeout")
        time.sleep(0.05)

    base_url = f"http://localhost:{vcserver_port}"
    print("-" * 50, flush=True)
    print(f" Application: {base_url}", flush=True)
    print(f" API Docs:    {base_url}/docs", flush=True)
    print("-" * 50, flush=True)
    print("Please press Ctrl+C once to exit vcclient.", flush=True)

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
            logger.error("sound device error: %s", e, exc_info=True)
            wasapi_not_supported_msg = (
                "If you are using WASAPI or ASIO, your device might not be compatible with it. "
                "Please try using MME instead."
            )
            logger.error(wasapi_not_supported_msg)
            print(err_msg)
            print(f" {wasapi_not_supported_msg} ")
            local_voice_changer_interface.stop()
            time.sleep(1)
        except Exception as e:
            err_msg = f"Error:{e}"
            logger.error("Runtime error: %s", e, exc_info=True)
            print(err_msg)
            local_voice_changer_interface.stop()
            time.sleep(1)

    print("terminate vcclient... (press Ctrl+C again to force exit)", flush=True)

    try:
        app_status.stop_app()
        vcserver.stop()
        VoiceChanger.get_instance().stop_convert_chunk_bulk()
    except KeyboardInterrupt:
        print("\nforce exit vcclient.", flush=True)
        os._exit(1)


def main():
    mp.freeze_support()

    parser = argparse.ArgumentParser(description=f"VCClient {VERSION} (pure-ONNX backend)")
    parser.add_argument("command", nargs="?", default="server", help=argparse.SUPPRESS)
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Binding host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=18888, help="Server port (default: 18888)")
    args: argparse.Namespace = parser.parse_args()

    if args.command in ("--help", "-h", "help"):
        parser.print_help()
        sys.exit(0)

    start_server(
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
