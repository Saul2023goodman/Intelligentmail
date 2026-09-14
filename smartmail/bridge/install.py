"""Register an explicit extension ID and one store with Chrome or Edge on Windows."""

import json
import re
import sys
from pathlib import Path

from . import BridgeError, HOST_NAME

REGISTRY_KEYS = {
    "chrome": rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
    "edge": rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
}


def prepare_installation(home, extension_id, browser):
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise BridgeError("Use the 32-character extension ID shown by Chrome or Edge")
    if browser not in REGISTRY_KEYS:
        raise BridgeError("Supported browsers are chrome and edge")
    home = Path(home).resolve()
    directory = home / "native-host" / browser
    directory.mkdir(parents=True, exist_ok=True)
    origin = f"chrome-extension://{extension_id}/"
    repository = Path(__file__).resolve().parents[2]
    # A fixed Python bootstrap carries paths as Python literals, not shell text.
    bootstrap = directory / "host.py"
    bootstrap.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(repository)!r})\n"
        "from smartmail.bridge.__main__ import serve\n"
        f"serve({str(home)!r}, {origin!r})\n", encoding="utf-8")
    launcher = directory / "host.cmd"
    python_path = str(Path(sys.executable).resolve())
    # cmd.exe expands percent and exclamation marks even in quoted paths.
    if any(char in python_path + str(bootstrap) for char in '%!\r\n"'):
        raise BridgeError("Native host launcher paths cannot contain %, !, quotes or newlines")
    launcher.write_text(
        f'@echo off\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n"{python_path}" -X utf8 "{bootstrap}" %*\n',
        encoding="utf-8")
    manifest = directory / f"{HOST_NAME}.json"
    manifest.write_text(json.dumps({
        "name": HOST_NAME, "description": "SmartMail 163 mailbox extension bridge",
        "path": str(launcher), "type": "stdio", "allowed_origins": [origin],
    }, indent=2), encoding="utf-8")
    return {"manifest": str(manifest), "browser": browser, "home": str(home),
            "extension_id": extension_id, "registry_key": REGISTRY_KEYS[browser]}


def install(home, extension_id, browser):
    if sys.platform != "win32":
        raise BridgeError("Automatic native host installation currently supports Windows only")
    import winreg
    result = prepare_installation(home, extension_id, browser)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, result["registry_key"]) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, result["manifest"])
    return result


def uninstall(browser):
    if sys.platform != "win32":
        raise BridgeError("Automatic native host installation currently supports Windows only")
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEYS[browser])
    except FileNotFoundError:
        pass
    return {"browser": browser, "registered": False}
