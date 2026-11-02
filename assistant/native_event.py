"""Session-local stop event, named by the private IPC nonce, never a model field."""
import ctypes
from ctypes import wintypes
import threading


class NativeStopEvent:
    def __init__(self, name: str, *, create=False):
        self.lock = threading.Lock()
        self.parent_handle = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.OpenEventW.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
        self.kernel.OpenEventW.restype = wintypes.HANDLE
        self.kernel.SetEvent.argtypes = [wintypes.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateEventW(None,True,False,name) if create else self.kernel.OpenEventW(0x100002,False,name)
        if not self.handle:
            raise RuntimeError("NATIVE_STOP_EVENT_UNAVAILABLE")

    def set(self):
        with self.lock:
            if self.handle:
                self.kernel.SetEvent(self.handle)

    def is_set(self):
        return self.wait(0)

    def wait(self, seconds):
        with self.lock:
            handle = self.handle
        if self.parent_handle and self.kernel.WaitForSingleObject(self.parent_handle,0)!=0x102:
            return True
        return not handle or self.kernel.WaitForSingleObject(handle, max(0,int(seconds*1000))) != 0x102

    def close(self):
        with self.lock:
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
