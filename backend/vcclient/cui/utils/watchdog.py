import logging
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from vcclient.const import LOGGER_NAME
from vcclient.voice_changer.voice_chanager_const import ModelDir, SettingsDir


class VCClientFileEventHandler(FileSystemEventHandler):
    def __init__(self, callback=None):

        super().__init__()

        self.callback = callback

    def on_any_event(self, event):

        if str(ModelDir) in event.src_path:
            self.callback("model", event)

        if str(SettingsDir) in event.src_path:
            self.callback("config", event)

            return None


class VCClientFileWatcher:
    def __init__(self, paths=None, handler=None):

        self.observer = Observer()

        self.handler = handler

        self.paths = paths

        self.stop_flag = False

        self.thread = threading.Thread(target=self.run)

        self.thread.start()

    def run(self):

        for path in self.paths:
            self.observer.schedule(self.handler, path, recursive=True)

        self.observer.start()

        logging.getLogger(LOGGER_NAME).info("MyWatcher Started")

        time.sleep(1)

        if self.stop_flag:
            pass

        self.observer.stop()

        self.observer.join()

        logging.getLogger(LOGGER_NAME).info("MyWatcher Terminated")

    def stop(self):

        self.stop_flag = True
