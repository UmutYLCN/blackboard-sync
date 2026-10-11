"""Just enough of the Windows Runtime, through ctypes, for the MSIX build.

The packaged app uses two WinRT classes (StartupTask, AppInstance, see
``package``). Calling them needs no extra dependency: an activation factory from
combase.dll and a few vtable slots. Interface IDs and slot order are those of the
Windows SDK metadata (``Windows.ApplicationModel`` and ``Windows.Foundation``).

Every call runs on a short-lived thread of its own in the multithreaded
apartment (``in_mta``), so the caller's COM apartment (the Tk thread's) is never
changed. Failures raise OSError, like the registry calls of the installer build.
"""

from __future__ import annotations

import ctypes
import threading
import time
import uuid

RO_INIT_MULTITHREADED = 1
# IUnknown's slots; IInspectable adds 3-5, so an interface's own methods start at 6.
QUERY_INTERFACE, RELEASE = 0, 2
IID_IASYNC_INFO = "00000036-0000-0000-c000-000000000046"
ASYNC_STATUS, ASYNC_ERROR_CODE, ASYNC_CANCEL = 7, 8, 9  # IAsyncInfo
GET_RESULTS = 8  # IAsyncOperation<T>
STARTED, COMPLETED, CANCELED, ERROR = range(4)  # AsyncStatus
ASYNC_TIMEOUT = 15.0


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


def check(hresult: int, what: str) -> None:
    if hresult < 0:
        raise OSError(f"{what} failed (HRESULT 0x{hresult & 0xFFFFFFFF:08X})")


def _combase():
    combase = ctypes.WinDLL("combase")
    combase.RoInitialize.argtypes = [ctypes.c_int]
    combase.RoInitialize.restype = ctypes.c_long
    combase.RoUninitialize.argtypes = []
    combase.RoUninitialize.restype = None
    combase.WindowsCreateString.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    combase.WindowsCreateString.restype = ctypes.c_long
    combase.WindowsDeleteString.argtypes = [ctypes.c_void_p]
    combase.WindowsDeleteString.restype = ctypes.c_long
    combase.RoGetActivationFactory.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
    ]
    combase.RoGetActivationFactory.restype = ctypes.c_long
    return combase


def _method(pointer: ctypes.c_void_p, slot: int, arguments: int, restype=ctypes.c_long):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *([ctypes.c_void_p] * arguments))
    return prototype(vtable[slot])


class Object:
    """An owned interface pointer, released when the ``with`` block ends."""

    def __init__(self, pointer: int):
        self.pointer = ctypes.c_void_p(pointer)

    def __enter__(self) -> Object:
        return self

    def __exit__(self, *exc) -> None:
        if self.pointer:
            _method(self.pointer, RELEASE, 0, ctypes.c_ulong)(self.pointer)
            self.pointer = ctypes.c_void_p()

    def call(self, slot: int, what: str, *args) -> None:
        check(_method(self.pointer, slot, len(args))(self.pointer, *args), what)

    def out(self, slot: int, what: str, *args, optional: bool = False) -> Object | None:
        """A method whose last parameter receives an interface pointer."""
        result = ctypes.c_void_p()
        self.call(slot, what, *args, ctypes.byref(result))
        if not result:
            if optional:
                return None
            raise OSError(f"{what} returned nothing")
        return Object(result.value)

    def get(self, slot: int, what: str) -> int:
        """A method whose only parameter receives a 32-bit value (an enum)."""
        result = ctypes.c_int32()
        self.call(slot, what, ctypes.byref(result))
        return result.value

    def query(self, iid: str, what: str) -> Object:
        guid = GUID.parse(iid)
        return self.out(QUERY_INTERFACE, what, ctypes.byref(guid))

    def wait(self, what: str) -> None:
        """Block until this IAsyncOperation finishes; raise if it did not complete."""
        with self.query(IID_IASYNC_INFO, what) as info:
            deadline = time.monotonic() + ASYNC_TIMEOUT
            while (status := info.get(ASYNC_STATUS, what)) == STARTED:
                if time.monotonic() > deadline:
                    info.call(ASYNC_CANCEL, what)
                    raise TimeoutError(f"{what} did not finish in {ASYNC_TIMEOUT:.0f} s")
                time.sleep(0.01)
            if status == ERROR:
                check(info.get(ASYNC_ERROR_CODE, what), what)
            if status != COMPLETED:
                raise OSError(f"{what} ended with status {status}")


class HString:
    """A WinRT string, deleted when the ``with`` block ends."""

    def __init__(self, combase, text: str):
        self.combase = combase
        self.handle = ctypes.c_void_p()
        check(combase.WindowsCreateString(text, len(text), ctypes.byref(self.handle)), "WindowsCreateString")

    def __enter__(self) -> HString:
        return self

    def __exit__(self, *exc) -> None:
        self.combase.WindowsDeleteString(self.handle)


def activation_factory(class_name: str, iid: str) -> Object:
    """The statics interface ``iid`` of runtime class ``class_name``."""
    combase = _combase()
    factory = ctypes.c_void_p()
    guid = GUID.parse(iid)
    with HString(combase, class_name) as name:
        check(combase.RoGetActivationFactory(name.handle, ctypes.byref(guid), ctypes.byref(factory)),
              f"RoGetActivationFactory({class_name})")
    return Object(factory.value)


def hstring(text: str) -> HString:
    return HString(_combase(), text)


def in_mta(function):
    """Run ``function()`` on a new thread in the multithreaded apartment."""
    result, error = [], []

    def run():
        combase = _combase()
        initialized = combase.RoInitialize(RO_INIT_MULTITHREADED)
        try:
            result.append(function())
        except BaseException as exc:
            error.append(exc)
        finally:
            if initialized >= 0:
                combase.RoUninitialize()

    thread = threading.Thread(target=run, name="winrt", daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
