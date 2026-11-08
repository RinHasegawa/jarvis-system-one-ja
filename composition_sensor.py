"""UI Automation TextEdit completion sensor, isolated from the GUI process.

Watches only the specified JARVIS text control. Emits event metadata, not text.
"""
import ctypes
from ctypes import wintypes
import json
import sys
import threading
import uuid

P = ctypes.c_void_p
HRESULT = ctypes.c_long
WIN = ctypes.WINFUNCTYPE
IID_UNKNOWN = uuid.UUID('00000000-0000-0000-c000-000000000046').bytes_le
IID_HANDLER = uuid.UUID('92faa680-e704-4156-931a-e32d5bb38f3f').bytes_le

class GUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte * 16)]
    @classmethod
    def from_string(cls, value):
        return cls((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))

def emit(event, **fields):
    print(json.dumps({'event': event, **fields}), flush=True)

def method(obj, index, result, *args):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(P))).contents
    return WIN(result, P, *args)(vtable[index])

def release(obj):
    if obj: method(obj, 2, wintypes.ULONG)(obj)

class EventHandler:
    def __init__(self):
        self.refs = 1
        self.lock = threading.Lock()
        self.query_cb = WIN(HRESULT, P, ctypes.POINTER(GUID), ctypes.POINTER(P))(self.query)
        self.add_cb = WIN(wintypes.ULONG, P)(self.add_ref)
        self.release_cb = WIN(wintypes.ULONG, P)(self.release_ref)
        self.event_cb = WIN(HRESULT, P, P, ctypes.c_int, P)(self.changed)
        self.vtable = (P * 4)(*(ctypes.cast(cb, P) for cb in
                                (self.query_cb, self.add_cb, self.release_cb, self.event_cb)))
        self.object = (P * 1)(ctypes.cast(self.vtable, P))
        self.pointer = ctypes.cast(self.object, P)

    def query(self, this, iid, out):
        if not out: return -2147467261  # E_POINTER
        if bytes(iid.contents.data) in (IID_UNKNOWN, IID_HANDLER):
            out[0] = this
            self.add_ref(this)
            return 0
        out[0] = None
        return -2147467262  # E_NOINTERFACE

    def add_ref(self, this):
        with self.lock:
            self.refs += 1
            return self.refs

    def release_ref(self, this):
        with self.lock:
            self.refs = max(0, self.refs - 1)
            return self.refs

    def changed(self, this, sender, change_type, payload):
        # Deliberately do not read payload; it may contain dictated text.
        if change_type == 3: emit('composition_finalized', change_type=3)
        return 0

def run(hwnd):
    ole = ctypes.OleDLL('ole32')
    ole.CoInitializeEx.argtypes = [P, wintypes.DWORD]
    ole.CoInitializeEx.restype = HRESULT
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), P, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(P)]
    ole.CoCreateInstance.restype = HRESULT
    result = ole.CoInitializeEx(None, 0)
    if result < 0: raise OSError('COM initialization failed')
    automation, element, pattern = P(), P(), P()
    handler = EventHandler()
    subscribed = False
    try:
        clsid = GUID.from_string('e22ad333-b25f-460c-83d0-0581107395c9')
        iid = GUID.from_string('73d768da-9b51-4b89-936e-c209290973e7')
        hr = ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(automation))
        if hr < 0: raise OSError('UI Automation client unavailable')
        hr = method(automation, 6, HRESULT, wintypes.HWND, ctypes.POINTER(P))(automation, hwnd, ctypes.byref(element))
        if hr < 0 or not element: raise OSError(f'JARVIS input control not accessible (HRESULT 0x{hr & 0xffffffff:08X})')
        hr = method(element, 16, HRESULT, ctypes.c_int, ctypes.POINTER(P))(element, 10032, ctypes.byref(pattern))
        available = hr >= 0 and bool(pattern)
        release(pattern)
        pattern = P()
        hr = method(automation, 64, HRESULT, P, ctypes.c_int, ctypes.c_int, P, P)(
            automation, element, 1, 3, None, handler.pointer)
        if hr < 0: raise OSError('Could not subscribe to TextEdit events')
        subscribed = True
        emit('sensor_ready', text_edit_pattern_available=available)
        # Parent closes stdin to stop; callbacks arrive on UI Automation threads.
        sys.stdin.buffer.read(1)
    finally:
        if subscribed:
            method(automation, 65, HRESULT, P, P)(automation, element, handler.pointer)
        release(element)
        release(automation)
        ole.CoUninitialize()

if __name__ == '__main__':
    try:
        run(int(sys.argv[1]))
    except Exception as exc:
        emit('sensor_error', error_type=type(exc).__name__, detail=str(exc))
        sys.exit(1)
