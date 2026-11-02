"""Render the original SVG to PNG sizes and a PNG-backed Windows multi-size ICO."""
from __future__ import annotations

from pathlib import Path
import struct
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    from assistant.branding import ASSETS
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Mavis icon export")
    renderer = QSvgRenderer(str(ASSETS / "mavis.svg"))
    if not renderer.isValid():
        raise RuntimeError("invalid SVG")
    chunks, sizes = [], (16, 24, 32, 48, 64, 128, 256)
    for size in (*sizes, 512):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        path = ASSETS / f"mavis-{size}.png"
        if not image.save(str(path)):
            raise RuntimeError("PNG export failed")
        if size in sizes:
            chunks.append(path.read_bytes())
    offset = 6 + 16 * len(sizes)
    entries = []
    for size, chunk in zip(sizes, chunks):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(chunk), offset))
        offset += len(chunk)
    (ASSETS / "mavis.ico").write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries + chunks))
    print(f"Exported SVG-derived PNGs and 7-size ICO: {ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
