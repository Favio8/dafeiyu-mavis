"""Presentation-only screen-edge light. Never receives focus or user input."""
from __future__ import annotations

import ctypes
import sys
import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen, QRegion
from PySide6.QtWidgets import QApplication, QWidget


def motion_allowed() -> bool:
    """Respect the Windows client-area animation preference; fail to static."""
    if sys.platform != "win32":
        return False
    enabled = ctypes.c_int()
    return bool(ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0) and enabled.value)


class EdgeGlow(QWidget):
    """One nonactivating, input-transparent ring per screen, in Qt logical pixels."""
    BAND = 28

    def __init__(self, screen):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle("Mavis · 操作边缘提示")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.phase = 0.0
        self.setGeometry(screen.geometry())
        self._mask()

    def _mask(self):
        self.setMask(QRegion(self.rect()) - QRegion(self.rect().adjusted(self.BAND, self.BAND, -self.BAND, -self.BAND)))

    def resizeEvent(self, event):  # noqa: N802
        self._mask()
        super().resizeEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Only the perimeter is painted; the center has zero alpha and is outside
        # the native region too. No screenshot capture or texture of user content.
        gradient = QConicalGradient(self.rect().center(), self.phase)
        for position, color in [(0, "#3075FF"), (.25, "#49DCEC"), (.5, "#8174F5"), (.75, "#4676F5"), (1, "#3075FF")]:
            gradient.setColorAt(position, QColor(color))
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        for width, opacity in [(48, .025), (36, .04), (24, .06), (14, .1), (7, .22), (3, .8)]:
            painter.setOpacity(opacity)
            painter.setPen(QPen(gradient, width))
            painter.drawRoundedRect(rect, 16, 16)
        painter.end()


class ExecutionOverlay(QObject):
    """Poll host state independently of queued UI updates; stop always wins.

    Hiding the effect is presentation only. The independent stop thread continues
    to revoke input even if Qt is busy; the renderer is not a safety mechanism.
    """
    def __init__(self, activity, stopped, parent=None):
        super().__init__(parent)
        self.activity, self.stopped = activity, stopped
        self.enabled = True
        self.windows = []
        self._preview_until = 0.0
        self._closed = False
        self._motion = motion_allowed()
        app = QApplication.instance()
        app.screenAdded.connect(self._rebuild)
        app.screenRemoved.connect(self._rebuild)
        self._screens = []
        self._rebuild()
        self.poll = QTimer(self)
        self.poll.setInterval(75)
        self.poll.timeout.connect(self.sync)
        self.poll.start()
        self.animation = QTimer(self)
        self.animation.setInterval(33)
        self.animation.timeout.connect(self._animate)

    def _rebuild(self, *_):
        for screen in self._screens:
            try:
                screen.geometryChanged.disconnect(self._geometry)
            except (RuntimeError, TypeError):
                pass
        for window in self.windows:
            window.close()
            window.deleteLater()
        self._screens = QApplication.instance().screens()
        self.windows = [EdgeGlow(screen) for screen in self._screens]
        for screen in self._screens:
            screen.geometryChanged.connect(self._geometry)

    def _geometry(self, *_):
        for screen, window in zip(self._screens, self.windows):
            window.setGeometry(screen.geometry())

    def set_enabled(self, enabled: bool):
        """Local session preference; cannot enable computer operation."""
        self.enabled = bool(enabled)
        self._preview_until = 0
        self.sync()

    def preview(self):
        """Four-second local preview. No task, permission, model or input call."""
        if not self.stopped.is_set():
            self._preview_until = time.monotonic() + 4
            self.sync()

    def sync(self):
        if self._closed:
            return
        if self.stopped.is_set():
            self._preview_until = 0
        visible = self.enabled and not self.stopped.is_set() and (self.activity.active or time.monotonic() < self._preview_until)
        if visible and any(not w.isVisible() for w in self.windows):
            self._motion = motion_allowed()
        for window in self.windows:
            if visible != window.isVisible():
                window.setVisible(visible)
        if visible and self._motion:
            if not self.animation.isActive():
                self.animation.start()
        else:
            self.animation.stop()

    def _animate(self):
        self.sync()
        if not self.animation.isActive():
            return
        phase = (time.monotonic() * 24) % 360
        for window in self.windows:
            window.phase = phase
            window.update()

    def close(self):
        """Destroy only our visual windows and timers."""
        self._closed = True
        self.poll.stop()
        self.animation.stop()
        app = QApplication.instance()
        app.screenAdded.disconnect(self._rebuild)
        app.screenRemoved.disconnect(self._rebuild)
        for screen in self._screens:
            try:
                screen.geometryChanged.disconnect(self._geometry)
            except (RuntimeError, TypeError):
                pass
        for window in self.windows:
            window.close()
            window.deleteLater()
