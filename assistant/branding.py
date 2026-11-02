"""Original scalable Mavis mark; no external icon/font runtime dependency."""
from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS = Path(__file__).with_name("assets")


def application_icon() -> QIcon:
    return QIcon(str(ASSETS / "mavis.svg"))
