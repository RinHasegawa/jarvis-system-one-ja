"""Windows user-bound encryption for the optional Jev key."""
import ctypes
from ctypes import wintypes
from pathlib import Path

KEY_FILE = Path(__file__).resolve().parent / '.cache' / 'jarvis_jev_key.dpapi'
crypt = ctypes.WinDLL('crypt32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)

class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
crypt.CryptProtectData.restype = wintypes.BOOL
crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
crypt.CryptUnprotectData.restype = wintypes.BOOL
kernel.LocalFree.argtypes = [ctypes.c_void_p]
kernel.LocalFree.restype = ctypes.c_void_p

def transform(data, encrypt):
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), buf)
    outgoing = Blob()
    operation = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    if not operation(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel.LocalFree(outgoing.pbData)

def save_key(key, path=KEY_FILE):
    encoded = key.strip().encode('utf-8')
    if not encoded:
        raise ValueError('Key is empty')
    encrypted = transform(encoded, True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_bytes(encrypted)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

def load_key(path=KEY_FILE):
    if not path.exists(): return ''
    return transform(path.read_bytes(), False).decode('utf-8')

def remove_key(path=KEY_FILE):
    path.unlink(missing_ok=True)
