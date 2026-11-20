import threading

_stop_event = threading.Event()


def is_app_stopping() -> bool:
    """Return True if application shutdown has been requested."""
    return _stop_event.is_set()


def stop_app() -> None:
    """Signal the application to shut down."""
    _stop_event.set()


def wait_for_stop(timeout: float | None = None) -> bool:
    """Wait until application shutdown is signaled, or timeout expires.

    Returns True if the shutdown signal was set, False otherwise.
    """
    return _stop_event.wait(timeout)
