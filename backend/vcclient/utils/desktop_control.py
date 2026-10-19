from collections.abc import Callable
from threading import Thread
from typing import TextIO


def watch_desktop_input(stream: TextIO, request_shutdown: Callable[[], None]) -> None:
    for line in stream:
        if line.strip() == "shutdown":
            break
    request_shutdown()


def start_desktop_control(stream: TextIO, request_shutdown: Callable[[], None]) -> Thread:
    thread = Thread(
        target=watch_desktop_input,
        args=(stream, request_shutdown),
        name="desktop-control",
        daemon=True,
    )
    thread.start()
    return thread
