"""Windows 10/11 toasts via WinRT in PowerShell, with data encoded separately."""

import base64
import subprocess
from xml.etree import ElementTree as ET

from .presentation import notification_fields


def toast_script(note) -> str:
    fields = notification_fields(note)
    attributes = {"activationType": "protocol", "launch": fields["launch"]} if fields["launch"] else {}
    toast = ET.Element("toast", attributes)
    binding = ET.SubElement(ET.SubElement(toast, "visual"), "binding", template="ToastGeneric")
    ET.SubElement(binding, "text").text = fields["title"]
    ET.SubElement(binding, "text").text = fields["msg"]
    payload = base64.b64encode(ET.tostring(toast, encoding="utf-8")).decode("ascii")
    return """
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')))
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Blackboard Sync').Show($toast)
""" % payload


def show(note):
    script = base64.b64encode(toast_script(note).encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", script],
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
