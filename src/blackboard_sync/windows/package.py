"""The MSIX (Microsoft Store) build: package identity and what comes with it.

The same frozen app ships two ways: the Inno Setup installer, which runs without
package identity, and an MSIX package (``packaging/msix``), which Windows starts
with one. Code that must behave differently in the package asks ``is_packaged()``;
the rest of this module wraps WinRT APIs that only a packaged process can use.
"""

from __future__ import annotations

import ctypes
import functools
import sys

from . import winrt

ERROR_INSUFFICIENT_BUFFER = 122  # the expected answer to the size query
APP_ID = "BlackboardSync"  # Application/Id in AppxManifest.xml.in

STARTUP_TASK = "Windows.ApplicationModel.StartupTask"
IID_STARTUP_TASK_STATICS = "ee5b60bd-a148-41a7-b26e-e8b88a1e62f8"
GET_ASYNC = 7  # IStartupTaskStatics
REQUEST_ENABLE_ASYNC, DISABLE, GET_STATE = 6, 7, 8  # IStartupTask
# StartupTaskState
DISABLED, DISABLED_BY_USER, ENABLED, DISABLED_BY_POLICY, ENABLED_BY_POLICY = range(5)
ENABLED_STATES = (ENABLED, ENABLED_BY_POLICY)

APP_INSTANCE = "Windows.ApplicationModel.AppInstance"
IID_APP_INSTANCE_STATICS = "9d11e77f-9ea6-47af-a6ec-46784c5ba254"
GET_ACTIVATED_EVENT_ARGS = 7  # IAppInstanceStatics
GET_KIND = 6  # IActivatedEventArgs
STARTUP_TASK_ACTIVATION = 1020  # ActivationKind.StartupTask


@functools.cache
def full_name() -> str | None:
    """This process's package full name, or None without package identity."""
    if sys.platform != "win32":
        return None
    function = getattr(ctypes.windll.kernel32, "GetCurrentPackageFullName", None)
    if function is None:  # before Windows 8
        return None
    function.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
    function.restype = ctypes.c_long
    length = ctypes.c_uint32(0)
    # APPMODEL_ERROR_NO_PACKAGE (15700) when the process has no identity.
    if function(ctypes.byref(length), None) != ERROR_INSUFFICIENT_BUFFER:
        return None
    buffer = ctypes.create_unicode_buffer(length.value)
    if function(ctypes.byref(length), buffer) != 0:
        return None
    return buffer.value


def is_packaged() -> bool:
    return full_name() is not None


@functools.cache
def family_name() -> str:
    """The current package family; fail closed if Windows cannot supply it."""
    function = ctypes.windll.kernel32.GetCurrentPackageFamilyName
    function.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
    function.restype = ctypes.c_long
    length = ctypes.c_uint32(0)
    if function(ctypes.byref(length), None) != ERROR_INSUFFICIENT_BUFFER:
        raise OSError("GetCurrentPackageFamilyName could not read the package identity")
    buffer = ctypes.create_unicode_buffer(length.value)
    if function(ctypes.byref(length), buffer) != 0:
        raise OSError("GetCurrentPackageFamilyName failed")
    return buffer.value


def app_user_model_id() -> str:
    """The GUI app's AUMID, including when called by its CLI twin."""
    return f"{family_name()}!{APP_ID}"


def _with_startup_task(task_id: str, use):
    def run():
        what = f"StartupTask.GetAsync({task_id})"
        with winrt.activation_factory(STARTUP_TASK, IID_STARTUP_TASK_STATICS) as statics:
            with winrt.hstring(task_id) as name, statics.out(GET_ASYNC, what, name.handle) as operation:
                operation.wait(what)
                with operation.out(winrt.GET_RESULTS, what) as task:
                    return use(task)

    return winrt.in_mta(run)


def startup_task_state(task_id: str) -> int:
    """The StartupTaskState of the manifest's startup task ``task_id``."""
    return _with_startup_task(task_id, lambda task: task.get(GET_STATE, "StartupTask.State"))


def set_startup_task(task_id: str, enabled: bool) -> int:
    """Enable or disable the startup task as far as Windows lets the app; the new state.

    A task the user turned off in Task Manager or Settings (DISABLED_BY_USER), or
    that policy controls, only the user or the policy can change: it is left alone.
    """

    def change(task):
        state = task.get(GET_STATE, "StartupTask.State")
        if enabled and state == DISABLED:
            what = "StartupTask.RequestEnableAsync"
            with task.out(REQUEST_ENABLE_ASYNC, what) as operation:
                operation.wait(what)
                return operation.get(winrt.GET_RESULTS, what)
        if not enabled and state == ENABLED:
            task.call(DISABLE, "StartupTask.Disable")
            return DISABLED
        return state

    return _with_startup_task(task_id, change)


def activation_kind() -> int | None:
    """How Windows started this packaged process (ActivationKind), or None.

    Windows answers only the first call in a process; later calls give None.
    """

    def run():
        what = "AppInstance.GetActivatedEventArgs"
        with winrt.activation_factory(APP_INSTANCE, IID_APP_INSTANCE_STATICS) as statics:
            arguments = statics.out(GET_ACTIVATED_EVENT_ARGS, what, optional=True)
            if arguments is None:
                return None
            with arguments:
                return arguments.get(GET_KIND, "IActivatedEventArgs.Kind")

    return winrt.in_mta(run)
