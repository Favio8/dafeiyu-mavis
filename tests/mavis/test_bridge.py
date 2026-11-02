"""Quit must revoke execution before hide-on-close or upstream decoder cleanup."""
import threading
from types import SimpleNamespace

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from assistant.pet_bridge import PetBridge
from test_ui import until


def test_bridge_queued_presentation_and_quit_filter(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from assistant import pet_bridge
    class NoNativeHotkey:
        registered, error = True, None
        shortcut = "Ctrl+Alt+F12"
        def __init__(self, stop, shortcut=None):
            pass
        def start(self):
            return True
        def close(self):
            self.registered = False
    monkeypatch.setattr(pet_bridge, "EmergencyHotkey", NoNativeHotkey)
    monkeypatch.setenv("MAVIS_TEST_MODE", "1")
    seen = []
    main_thread = threading.get_ident()
    from pet import multi_window_shared
    target = SimpleNamespace(show_bubble=lambda *a, **k: seen.append(threading.get_ident()))
    monkeypatch.setattr(multi_window_shared, "presentation_targets", lambda shell: [target])
    bridge = PetBridge(app, SimpleNamespace(tray=None), SimpleNamespace(dir=tmp_path))
    try:
        until(lambda: bridge.window.latest is not None)
        bridge.controller.submit("exercise")
        until(lambda: bridge.window.allow.isEnabled())
        until(lambda: bool(seen))
        assert set(seen) == {main_thread}
        bridge.window.close()
        assert not bridge.window.isVisible() and not bridge.closed
        bridge.show()
        assert bridge.window.isVisible()
        assert bridge.eventFilter(app, QEvent(QEvent.Type.Quit)) is False
        assert bridge.closed and bridge.stop.event.is_set()
        assert bridge.controller.closed.is_set()
        assert bridge.window.exiting and not bridge.window.isVisible()
        bridge.show()
        assert not bridge.window.isVisible()
    finally:
        bridge.close()
        bridge.deleteLater()
