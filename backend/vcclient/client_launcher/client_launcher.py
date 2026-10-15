import logging
import os
import platform
import subprocess
import threading
import webbrowser
from typing import Callable

from vcclient.const import LOGGER_NAME, NATIVE_CLIENT_FILE_MAC, NATIVE_CLIENT_FILE_WIN


class ClientLauncher:
    def __init__(self, terminate_callback: Callable = None):
        self.terminate_callback = terminate_callback
        self.process = None

    def launch(self, port: int, https: bool = False):
        threading.Thread(target=self._launch_client, args=(port, https), daemon=True).start()

    def _launch_client(self, port: int, https: bool):
        protocol = "https" if https else "http"
        url = f"{protocol}://localhost:{port}/"

        try:
            client_path = str(NATIVE_CLIENT_FILE_WIN)
            if platform.system() == "Windows":
                client_path = str(NATIVE_CLIENT_FILE_WIN)
            elif platform.system() == "Linux":
                client_path = str(NATIVE_CLIENT_FILE_WIN)
            elif platform.system() == "Darwin":
                client_path = str(NATIVE_CLIENT_FILE_MAC)

            if os.path.exists(client_path):
                self.process = subprocess.Popen(
                    [client_path, "--disable-gpu", "-u", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout_thread = threading.Thread(
                    target=self.read_output,
                    args=(self.process.stdout, logging.getLogger(LOGGER_NAME).warning),
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=self.read_output,
                    args=(self.process.stderr, logging.getLogger(LOGGER_NAME).warning),
                    daemon=True,
                )
                stdout_thread.start()
                stderr_thread.start()

                return_code = self.process.wait()
                logging.getLogger(LOGGER_NAME).info(f"native client closed. {return_code}")
                if self.terminate_callback:
                    self.terminate_callback()
            else:
                # Fallback to standard web browser
                logging.getLogger(LOGGER_NAME).info(f"Opening browser at {url}")
                webbrowser.open(url)
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Failed to launch client: {e}")

    def stop(self):
        if hasattr(self, "process") and self.process and self.process.poll() is None:
            self.process.terminate()

    def read_output(self, pipe, log_function):
        with pipe:
            for line in iter(pipe.readline, b""):
                log_function(line.decode("utf-8", errors="replace").strip())
