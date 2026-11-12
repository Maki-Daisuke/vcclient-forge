from threading import Event, Thread

from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface


def test_run_does_not_start_after_stop(monkeypatch):
    interface = LocalVoiceChangerInterface()
    started = []
    monkeypatch.setattr(interface, "setup", lambda: started.append(True))
    interface.run()
    assert not started
    assert not interface.stream_running


def test_run_reports_stream_until_launch_returns(monkeypatch):
    interface = LocalVoiceChangerInterface()
    interface.local_voice_changer_enabled = True
    entered, release = Event(), Event()
    monkeypatch.setattr(interface, "setup", lambda: None)

    def launch():
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(interface, "launch_converter", launch)
    worker = Thread(target=interface.run)
    worker.start()
    try:
        assert entered.wait(5)
        assert interface.stream_running
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert not interface.stream_running
