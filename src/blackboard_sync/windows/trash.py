"""Recycle one recorded path; veto any Shell fallback to permanent deletion."""

from pathlib import Path

# IFileOperation flags, including recycling and no associated HTML asset folders.
FLAGS = 0x00080000 | 0x20000000 | 0x00100000 | 0x0400 | 0x0010 | 0x0004 | 0x2000
RECYCLE_IF_POSSIBLE = 0x80
E_ABORT = -2147467260


def recycle(path: Path) -> None:
    try:
        import pythoncom
        import pywintypes
        from win32com.shell import shell
        from win32com.server.exception import COMException
        from send2trash.win.IFileOperationProgressSink import FileOperationProgressSink
    except ImportError as exc:
        # Never fall back to SHFileOperation, which can permanently delete files
        # when recycling is unavailable (e.g. on a network/removable volume).
        raise OSError("Geri Dönüşüm Kutusu API'si yüklenemedi; dosya korundu.") from exc

    class RecycleOnlySink(FileOperationProgressSink):
        def PreDeleteItem(self, flags, item):
            if not flags & RECYCLE_IF_POSSIBLE:
                # Raise a COM error: a plain Python return value is not an
                # HRESULT failure in pywin32's server callback implementation.
                raise COMException("Dosya geri dönüştürülemiyor; kalıcı silme iptal edildi.", scode=E_ABORT)
            return 0

    pythoncom.CoInitialize()
    operation = None
    try:
        operation = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None,
                                               pythoncom.CLSCTX_ALL, shell.IID_IFileOperation)
        operation.SetOperationFlags(FLAGS)
        item = shell.SHCreateItemFromParsingName(str(path.absolute()), None, shell.IID_IShellItem)
        sink = pythoncom.WrapObject(RecycleOnlySink(), shell.IID_IFileOperationProgressSink)
        operation.DeleteItem(item, sink)
        result = operation.PerformOperations()
        if result or operation.GetAnyOperationsAborted():
            raise OSError("Dosya Geri Dönüşüm Kutusu'na taşınamadı; dosya korundu.")
    except pywintypes.com_error as exc:
        raise OSError(f"Geri Dönüşüm Kutusu işlemi başarısız: {exc}") from exc
    finally:
        operation = None
        pythoncom.CoUninitialize()
