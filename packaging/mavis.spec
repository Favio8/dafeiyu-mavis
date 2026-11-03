# Mavis onedir: shared runtime, windowed UI and fixed console worker.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
stage = Path(os.environ["MAVIS_BUILD_STAGE"])
datas = [(str(root/"assets/characters"), "assets/characters"),
         (str(root/"assets/sounds"), "assets/sounds"),
         (str(root/"assets/chat"), "assets/chat"),
         (str(root/"assets/big_blue_fat_fish"), "assets/big_blue_fat_fish"),
         (str(root/"assistant/assets"), "assistant/assets"),
         (str(root/"resources"), "resources"),
         (str(root/"LICENSE"), "."), (str(root/"THIRD_PARTY_NOTICES.md"), "."),
         (str(stage/"build-info.json"), "."), (str(stage/"licenses"), "licenses"),
         (str(stage/"icon.ico"), "assets")]
datas += [(str(root/"tests/mavis/test_m5_safety.py"), "acceptance/tests/mavis"),
          (str(root/"tests/fixtures/mavis/m5-negative-cases.json"), "acceptance/tests/fixtures/mavis"),
          (str(root/"packaging/mavis-pytest.ini"), "acceptance")]
for name in ("UPSTREAM_BASELINE.md", "MAVIS_LICENSE_INVENTORY.md", "KNOWN_LIMITATIONS.md", "USER_GUIDE.md", "MODEL_PACKS.md"):
    datas.append((str(root/"docs"/name), "docs"))
datas += collect_data_files("pet", includes=["**/*.json", "**/*.qss", "**/*.svg"])
binaries = []
hidden = collect_submodules("assistant") + collect_submodules("comtypes.gen") + collect_submodules("_pytest")
for package in ("imageio_ffmpeg", "certifi", "keyring", "win32ctypes", "sherpa_onnx", "sentencepiece", "pypinyin", "tzdata"):
    data, binary, modules = collect_all(package)
    datas += data
    binaries += binary
    hidden += modules
for distribution in ("PySide6", "shiboken6", "sherpa-onnx", "keyring", "comtypes", "pydantic", "aiohttp", "imageio-ffmpeg", "Pillow", "psutil", "pywin32"):
    datas += copy_metadata(distribution)
a = Analysis([str(root/"packaging/mavis_entry.py")], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hidden+["PySide6.QtSvg", "PySide6.QtMultimedia", "pythoncom", "pywintypes", "win32com.client", "win32cred"],
             excludes=["pet.chat", "OpenGL", "PyQt5", "PyQt6", "PySide2", "torch", "transformers", "pandas", "IPython", "matplotlib", "windows_use", "litellm", "posthog"],
             noarchive=False)
pyz = PYZ(a.pure)
common = dict(exclude_binaries=True, debug=False, bootloader_ignore_signals=False,
              strip=False, upx=False, icon=str(root/"assistant/assets/mavis.ico"), version=str(stage/"version.txt"))
ui = EXE(pyz, a.scripts, [], name="DaFeiYuMavis", console=False, **common)
worker = EXE(pyz, a.scripts, [], name="mavis-worker", console=True, **common)
collect = COLLECT(ui, worker, a.binaries, a.datas, strip=False, upx=False, name="DaFeiYuMavis")
