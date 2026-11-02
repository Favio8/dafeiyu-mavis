# Mavis · M core

Original vector mark: an open blue orbital ring around a white M, with a cyan
core point. Intended for the native Mavis window, core-only tray and future
Windows packaging. It does not reuse DeepSeek or JARVIS brand artwork.

- Source: `mavis.svg`, 256 × 256 viewBox, transparent outer corners.
- Primary: `#002FA7`; ring: `#6CA5FF`; core: `#7DE2F5`; M: white.
- PNG: 16, 24, 32, 48, 64, 128, 256 and 512 px.
- ICO: 16–256 px, seven embedded PNG images with alpha.
- Rebuild: `.venv/Scripts/python.exe scripts/mavis_export_icon.py`.

Navigation and action icons use the existing `pet.context_menus.icons` vector
provider. No Lucide package or new font is required. The full pet host retains
its existing character tray icon; installer resources remain a later packaging step.
