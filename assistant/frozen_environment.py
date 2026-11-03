"""Keep shipped DLL search paths out of a registered external Windows application."""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys


@contextmanager
def external_application():
    """Neutralize PyInstaller's inherited DLL path only around the external spawn.

    This runs in the dedicated native worker, not the UI process. The fixed
    companion worker and bundled decoder continue using their shipped runtime.
    """
    if not getattr(sys, "frozen", False):
        yield
        return
    root = Path(sys._MEIPASS).resolve()
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(p for p in old_path.split(os.pathsep) if p and not Path(p).resolve().is_relative_to(root))
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    try:
        if not kernel.SetDllDirectoryW(None):
            raise OSError("EXTERNAL_DLL_PATH_RESET_FAILED")
        yield
    finally:
        os.environ["PATH"] = old_path
        kernel.SetDllDirectoryW(str(root))
