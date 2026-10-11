"""Windows 10/11 toasts via WinRT in PowerShell, with data encoded separately."""

import base64
import subprocess
from xml.etree import ElementTree as ET

from .presentation import notification_fields
from . import activation, package


def toast_identity() -> str:
    return package.app_user_model_id() if package.is_packaged() else "Blackboard Sync"


def notifier_script(identity: str) -> str:
    # AUMIDs come from Windows, but still quote them as PowerShell data.
    identity = identity.replace("'", "''")
    return """
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s')
""" % identity


def toast_script(note) -> str:
    fields = notification_fields(note)
    launch = activation.STORE_URI if package.is_packaged() else fields["launch"]
    attributes = {"activationType": "protocol", "launch": launch} if launch else {}
    toast = ET.Element("toast", attributes)
    binding = ET.SubElement(ET.SubElement(toast, "visual"), "binding", template="ToastGeneric")
    ET.SubElement(binding, "text").text = fields["title"]
    ET.SubElement(binding, "text").text = fields["msg"]
    payload = base64.b64encode(ET.tostring(toast, encoding="utf-8")).decode("ascii")
    return notifier_script(toast_identity()) + """
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')))
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$notifier.Show($toast)
""" % payload


def show(note):
    _run_script(toast_script(note))


def check_identity() -> str:
    """Create the real notifier in the child process, without displaying a toast."""
    identity = toast_identity()
    _run_script(notifier_script(identity))
    return identity


def _run_script(script: str):
    script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", script],
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
