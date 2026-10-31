"""Verify icon resources in both built PEs, without executing either binary."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import struct


def ico_images(path):
    data = Path(path).read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    if reserved or kind != 1:
        raise ValueError("Invalid ICO asset")
    images = set()
    for i in range(count):
        size, offset = struct.unpack_from("<II", data, 6 + i * 16 + 8)
        images.add(data[offset:offset + size])
    return images


def embedded_images(path):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD]
    api.LoadLibraryExW.restype = ctypes.c_void_p
    api.FindResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    api.FindResourceW.restype = ctypes.c_void_p
    api.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    api.SizeofResource.restype = wintypes.DWORD
    api.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    api.LoadResource.restype = ctypes.c_void_p
    api.LockResource.argtypes = [ctypes.c_void_p]
    api.LockResource.restype = ctypes.c_void_p
    api.FreeLibrary.argtypes = [ctypes.c_void_p]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_void_p, wintypes.LPARAM)
    images = set()

    @callback_type
    def collect(module, resource_type, name, param):
        resource = api.FindResourceW(module, name, resource_type)
        size = api.SizeofResource(module, resource)
        pointer = api.LockResource(api.LoadResource(module, resource))
        if pointer and size:
            images.add(ctypes.string_at(pointer, size))
        return True

    api.EnumResourceNamesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, callback_type, wintypes.LPARAM]
    handle = api.LoadLibraryExW(str(Path(path).resolve()), None, 0x02 | 0x20)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not api.EnumResourceNamesW(handle, 3, collect, 0):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        api.FreeLibrary(handle)
    return images


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for executable, icon in (("ULTRON.exe", "jarvis.ico"), ("ULTRON-Setup.exe", "setup.ico")):
        assert ico_images(root / "config" / icon) <= embedded_images(root / "dist" / executable), executable
        print(executable + ": verified " + icon)
