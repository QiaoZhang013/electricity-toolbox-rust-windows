"""Small OS boundaries shared by the unchanged Tk UI and business tools."""
from __future__ import annotations

from contextlib import contextmanager
import os
import json
import hashlib
import shutil
from pathlib import Path
import subprocess
import sys


def hidden_process_options():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def detached_browser_process_options():
    """Keep the persistent WPS browser outside a short-lived worker's job."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB}
    return {"start_new_session": True}


def configure_dpi():
    """Ask Windows for physical display metrics before constructing Tk windows."""
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except AttributeError:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    # os.kill(pid, 0) terminates a Windows process; use a query-only handle.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5  # Access denied is not proof of exit.
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def _windows_system_directory() -> Path | None:
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        kernel.GetSystemDirectoryW.restype = wintypes.UINT
        buffer = ctypes.create_unicode_buffer(32768)
        count = kernel.GetSystemDirectoryW(buffer, len(buffer))
        if 0 < count < len(buffer):
            return Path(buffer.value)
    for variable in ('SystemRoot', 'WINDIR'):
        if root := os.environ.get(variable):
            return Path(root) / 'System32'
    return None


def windows_powershell_executable() -> Path:
    """Find the Windows component even when a desktop launch has no shell PATH."""
    system = _windows_system_directory()
    if system is not None:
        candidate = system / 'WindowsPowerShell/v1.0/powershell.exe'
        if candidate.is_file():
            return candidate
    if discovered := shutil.which('powershell.exe'):
        return Path(discovered).resolve()
    raise RuntimeError('未找到 Windows PowerShell，无法执行系统检查；请检查 Windows 系统组件是否完整。')


def windows_system_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if system := _windows_system_directory():
        # PowerShell itself needs these for startup. Repair only its environment;
        # do not change the user's PATH or machine settings.
        for variable in ('SYSTEMROOT', 'WINDIR'):
            if not environment.get(variable):
                environment[variable] = str(system.parent)
    return environment


def windows_browser_processes(pid: int | None = None) -> list[dict]:
    """Query command lines only when starting/reconnecting the dedicated browser."""
    condition = f"ProcessId={int(pid)}" if pid is not None else "Name='chrome.exe' OR Name='msedge.exe'"
    script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
              f"@(Get-CimInstance Win32_Process -Filter \"{condition}\" | "
              "Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress")
    result = subprocess.run([str(windows_powershell_executable()), "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, encoding="utf-8", timeout=10,
                            check=True, env=windows_system_environment(), **hidden_process_options())
    rows = json.loads(result.stdout.strip() or "[]")
    return [rows] if isinstance(rows, dict) else rows


def find_windows_browser() -> Path | None:
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            for relative in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"):
                path = Path(root) / relative
                if path.is_file():
                    return path
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            path = Path(playwright.chromium.executable_path)
            if path.is_file():
                return path
    except (ImportError, OSError):
        pass
    return None


def open_path(path: Path):
    if sys.platform == "win32":
        os.startfile(str(path.resolve()))
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=False)


@contextmanager
def directory_lock(directory: Path):
    """Nonblocking interprocess lock; kernel releases ownership on process exit."""
    if os.name != "nt":
        import fcntl
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(descriptor)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    identity = os.path.normcase(str(directory.resolve())).encode("utf-8")
    name = "Global\\ElectricityToolbox.Output." + hashlib.sha256(identity).hexdigest()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = False
    try:
        status = kernel.WaitForSingleObject(handle, 0)
        if status == 258:
            raise BlockingIOError(32, "输出目录正在使用", str(directory))
        if status not in (0, 128):  # WAIT_OBJECT_0 or abandoned owner.
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
