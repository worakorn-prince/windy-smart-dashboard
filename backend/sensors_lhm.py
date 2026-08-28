"""In-process LibreHardwareMonitor integration via pythonnet.

Loads LibreHardwareMonitorLib.dll directly (no GUI, no WMI namespace needed).
Requires the backend process to run as Administrator for full sensor access;
otherwise read_all_sensors() returns [] and callers fall back gracefully.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from typing import Any

logger = logging.getLogger("dashboard.sensors_lhm")

# winget portable install location; overridable via env var.
LHM_DLL_DIR = os.environ.get(
    "LHM_DLL_DIR",
    r"C:\Users\Prince\AppData\Local\Microsoft\WinGet\Packages"
    r"\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe",
)

_lock = threading.Lock()
_computer: Any = None
_init_state: str = ""  # "", "ok", "requires_admin", "no_pythonnet", "failed:<msg>"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


def init_state() -> str:
    """Return current init state ('', 'ok', 'requires_admin', ...)."""
    return _init_state


def _assembly_resolver(directory: str):
    """Hook .NET AssemblyResolve so LHM's sibling DLLs can be found."""
    from System import AppDomain, Reflection  # type: ignore

    def resolver(sender: Any, args: Any) -> Any | None:
        name = Reflection.AssemblyName(args.Name).Name
        path = os.path.join(directory, name + ".dll")
        if os.path.exists(path):
            try:
                return Reflection.Assembly.LoadFrom(path)
            except Exception:
                return None
        return None

    try:
        handler = Reflection.ResolveEventHandler(resolver)
        AppDomain.CurrentDomain.add_AssemblyResolve(handler)
    except Exception as exc:
        logger.debug("AssemblyResolve hook skipped: %s", exc)


def _preload_dlls(directory: str) -> None:
    """Best-effort preload of every sibling DLL (helps dependency probing)."""
    import contextlib
    import clr  # type: ignore

    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith(".dll"):
            continue
        with contextlib.suppress(Exception):
            clr.AddReference(os.path.join(directory, fname))


def _init() -> None:
    global _computer, _init_state
    if _computer is not None or _init_state:
        return

    if not sys.platform.startswith("win"):
        _init_state = "not_windows"
        return
    if not is_admin():
        _init_state = "requires_admin"
        logger.info("LHM: backend not elevated - hardware temps disabled")
        return

    dll_path = os.path.join(LHM_DLL_DIR, "LibreHardwareMonitorLib.dll")
    if not os.path.exists(dll_path):
        _init_state = f"dll_not_found:{dll_path}"
        logger.warning("LHM DLL missing: %s", dll_path)
        return

    try:
        import clr  # type: ignore  # pythonnet

        sys.path.insert(0, LHM_DLL_DIR)
        _preload_dlls(LHM_DLL_DIR)
        _assembly_resolver(LHM_DLL_DIR)
        clr.AddReference("LibreHardwareMonitorLib")

        from LibreHardwareMonitor import Hardware  # type: ignore

        comp = Hardware.Computer()
        comp.IsCpuEnabled = True
        comp.IsGpuEnabled = True
        comp.IsMemoryEnabled = True
        comp.IsStorageEnabled = True
        comp.IsMotherboardEnabled = True
        comp.IsNetworkEnabled = False
        comp.IsPsuEnabled = False
        comp.IsControllerEnabled = False
        comp.Open()

        _computer = comp
        _init_state = "ok"
        logger.info("LibreHardwareMonitor initialized in-process")
    except Exception as exc:
        _init_state = f"failed:{exc}"
        logger.warning("LHM init failed: %s", exc)


def read_all_sensors() -> list[dict[str, Any]]:
    """Read every sensor. Returns list shaped like the WMI variant:
    {name, type, value, parent} where parent looks like '/amdcpu/0'.
    """
    if _computer is None:
        with _lock:
            _init()
        if _computer is None:
            return []

    out: list[dict[str, Any]] = []
    with _lock:
        try:
            def walk(hw: Any) -> None:
                hw.Update()
                identifier = str(hw.Identifier)  # e.g. /amdcpu/0
                hwname = str(hw.Name)
                for s in hw.Sensors:
                    val: float | None
                    try:
                        val = float(s.Value) if s.Value is not None else None
                    except (TypeError, ValueError):
                        val = None
                    stype = str(s.SensorType)
                    stype = stype.rsplit(".", maxsplit=1)[-1].rstrip(")")
                    out.append({
                        "name": str(s.Name),
                        "type": stype,
                        "value": val,
                        "parent": identifier,
                        "hwname": hwname,
                    })
                for sub in hw.SubHardware:
                    walk(sub)

            for hw in _computer.Hardware:
                walk(hw)
        except Exception as exc:
            logger.debug("LHM sensor walk failed: %s", exc)
    return out
