"""PowerShell helper for Windows-specific security queries.

Falls back gracefully when not running on Windows or when commands fail.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from typing import Any

logger = logging.getLogger("dashboard.winapi")

IS_WINDOWS = sys.platform.startswith("win")


def _powershell_available() -> bool:
    return IS_WINDOWS and shutil.which("powershell.exe") is not None


async def _run_powershell(script: str, timeout: float = 15.0) -> str:
    """Run a PowerShell script and return stdout. Errors are logged and re-raised."""
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError("PowerShell command timed out") from None
    if stderr:
        err = stderr.decode("utf-8", errors="replace").strip()
        if err:
            logger.debug("PowerShell stderr: %s", err)
    return stdout.decode("utf-8", errors="replace")


def _parse_json_list(text: str) -> list[dict[str, Any]]:
    """Best-effort parse JSON array from PowerShell ConvertTo-Json output."""
    import json
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return [data]
    except json.JSONDecodeError as exc:
        logger.debug("Failed to parse PowerShell JSON: %s | text=%r", exc, text[:300])
        return []


async def defender_status() -> dict[str, Any]:
    """Query Windows Defender status."""
    if not _powershell_available():
        return {"available": False, "reason": "PowerShell not available"}
    script = (
        "Get-MpComputerStatus | Select-Object "
        "AMRunningMode, AntivirusEnabled, AntivirusSignatureLastUpdated, "
        "RealTimeProtectionEnabled, IsTamperProtected, BehaviorMonitorEnabled, "
        "NISEnabled, OnAccessProtectionEnabled, IoavProtectionEnabled, "
        "QuickScanEndTime, FullScanEndTime | ConvertTo-Json -Compress -Depth 3"
    )
    try:
        out = await _run_powershell(script)
        rows = _parse_json_list(out)
        if rows:
            return {"available": True, **rows[0]}
        return {"available": True}  # ran without output (unlikely)
    except Exception as exc:
        logger.warning("defender_status failed: %s", exc)
        return {"available": False, "reason": str(exc)}


async def failed_logins(limit: int = 100) -> list[dict[str, Any]]:
    """Read failed login events (EventID 4625) from the Security log.

    Requires Administrator privileges and Security log auditing enabled.
    """
    if not _powershell_available():
        return []
    script = (
        f"Get-WinEvent -FilterHashtable @{{LogName='Security'; Id=4625}} "
        f"-MaxEvents {int(limit)} -ErrorAction SilentlyContinue | "
        "ForEach-Object { "
        "$u = $_.Properties[5].Value; "
        "$t = $_.Properties[39].Value; "
        "@{ TimeCreated=$_.TimeCreated; TargetUser=$u; LogonType=$t; "
        "  IpAddress=$_.Properties[19].Value; "
        "  Workstation=$_.Properties[11].Value; "
        "  FailureReason=$_.Properties[7].Value } } | ConvertTo-Json -Compress -Depth 2"
    )
    try:
        out = await _run_powershell(script, timeout=20.0)
        return _parse_json_list(out)
    except Exception as exc:
        logger.warning("failed_logins failed: %s", exc)
        return []


async def firewall_status() -> dict[str, Any]:
    """Return per-profile firewall enabled state."""
    if not _powershell_available():
        return {"available": False}
    script = (
        "Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json -Compress"
    )
    try:
        out = await _run_powershell(script)
        return {"available": True, "profiles": _parse_json_list(out)}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


async def list_scheduled_tasks() -> list[dict[str, Any]]:
    """List all scheduled tasks without junk-Microsoft ones prefixed with '\\Microsoft\\'.

    Returns last 100 user-created (non-Microsoft) tasks for inspection.
    Hidden persistence lives here.
    """
    if not _powershell_available():
        return []
    script = (
        "Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' -and "
        "-not $_.TaskPath.StartsWith('\\Microsoft\\') } | "
        "Select-Object TaskName, TaskPath, State, Author, "
        "@{n='LastRun';e={ ($_.LastRunTime) }} | "
        "Sort-Object TaskName | ConvertTo-Json -Compress -Depth 3"
    )
    try:
        out = await _run_powershell(script, timeout=20.0)
        return _parse_json_list(out)
    except Exception as exc:
        logger.warning("list_scheduled_tasks failed: %s", exc)
        return []


async def list_installed_programs(limit: int = 200) -> list[dict[str, Any]]:
    """List installed programs from registry."""
    if not _powershell_available():
        return []
    script = (
        "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, "
        "HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | "
        "Where-Object { $_.DisplayName } | "
        "Select-Object DisplayName, Publisher, DisplayVersion, InstallDate | "
        "Sort-Object DisplayName | ConvertTo-Json -Compress -Depth 2"
    )
    try:
        out = await _run_powershell(script, timeout=20.0)
        rows = _parse_json_list(out)
        # Sort by install date if present, newest first.
        def _key(r: dict[str, Any]) -> str:
            return str(r.get("InstallDate") or "")
        rows.sort(key=_key, reverse=True)
        return rows[:limit]
    except Exception as exc:
        logger.warning("list_installed_programs failed: %s", exc)
        return []


async def user_accounts() -> list[dict[str, Any]]:
    """List local user accounts with creation hints."""
    if not _powershell_available():
        return []
    script = (
        "Get-LocalUser -ErrorAction SilentlyContinue | "
        "Select-Object Name, Enabled, LastLogon, PasswordLastSet, "
        "UserMayChangePassword, PrincipalSource | ConvertTo-Json -Compress -Depth 2"
    )
    try:
        out = await _run_powershell(script)
        return _parse_json_list(out)
    except Exception as exc:
        logger.warning("user_accounts failed: %s", exc)
        return []


async def wifi_profiles() -> list[dict[str, Any]]:
    """Enumerate saved Wi-Fi profiles and their authentication mode.

    Implementation: a single netsh call to list SSIDs, then parallel
    per-SSID netsh calls (Python subprocess, no PowerShell overhead per
    call). Capped at 8 concurrent calls.
    """
    if not IS_WINDOWS:
        return []
    import asyncio
    import re

    # Step 1: list all saved profiles via subprocess (no PS overhead).
    try:
        out = await _run_shell_with_capture(
            "netsh wlan show profiles", timeout=10.0,
        )
    except Exception as exc:
        logger.warning("wifi_profiles (list) failed: %s", exc)
        return []

    ssids: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        m = re.search(r":\s+(.+)$", line)
        if m:
            ssids.append(m.group(1).strip())

    if not ssids:
        return []

    # Step 2: fetch auth for each SSID in parallel via direct netsh calls.
    sem = asyncio.Semaphore(8)

    async def _auth_for(ssid: str) -> dict[str, Any]:
        async with sem:
            try:
                text = await _run_shell_with_capture(
                    f'netsh wlan show profile name="{ssid}" key=clear',
                    timeout=8.0,
                )
            except Exception:
                return {"SSID": ssid, "Auth": ""}
            auth = ""
            for ln in text.splitlines():
                if "authentication" in ln.lower() and ":" in ln:
                    auth = ln.split(":", 1)[1].strip()
                    break
            return {"SSID": ssid, "Auth": auth}

    results = await asyncio.gather(*[_auth_for(s) for s in ssids],
                                   return_exceptions=True)
    out_list: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        out_list.append(r)
    return out_list


async def _run_shell_with_capture(cmd: str, timeout: float = 10.0) -> str:
    """Run cmd.exe command line directly (no PowerShell overhead)."""
    proc = await asyncio.create_subprocess_exec(
        "cmd.exe", "/c", cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    # netsh output is in the system OEM codepage on Windows. Decode gracefully.
    try:
        return out.decode("oem", errors="replace")
    except (LookupError, UnicodeDecodeError):
        return out.decode("utf-8", errors="replace")


async def _run_power_shell_old_script(content: str) -> str:
    return await _run_powershell(content, timeout=30.0)


def read_hosts_file() -> dict[str, Any]:
    """Read the Windows hosts file and surface suspicious entries."""
    if not IS_WINDOWS:
        return {"available": False}
    import os
    path = r"C:\Windows\System32\drivers\etc\hosts"
    try:
        if not os.path.exists(path):
            return {"available": False, "reason": "hosts file not found"}
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f]
    except PermissionError as exc:
        return {"available": False, "reason": str(exc)}

    entries = []
    suspicious = []
    for ln in lines:
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) < 2:
            continue
        ip, *hosts = parts
        for h in hosts:
            entries.append({"ip": ip, "host": h})
            # Heuristic: many malware redirect common domains.
            if h.lower() in {"google.com", "www.google.com", "facebook.com", "www.facebook.com",
                             "login.live.com", "outlook.com", "github.com", "microsoft.com",
                             "apple.com", "icloud.com", "www.microsoft.com"}:
                suspicious.append({"ip": ip, "host": h, "reason": "common-domain-redirect"})
            # Redirect to localhost ranges.
            octets = ip.split(".")
            if len(octets) == 4:
                first = int(octets[0])
                if first not in (127, 0, 10, 192, 172) or ip == "0.0.0.0":
                    suspicious.append({"ip": ip, "host": h, "reason": "nonstandard-redirect"})
    return {"available": True, "path": path, "entries": entries, "suspicious": suspicious}


def arp_table() -> dict[str, Any]:
    """Read the ARP cache and identify duplicate-MAC scenarios (MITM hint)."""
    if not IS_WINDOWS:
        return {"available": False}
    import re
    import subprocess
    try:
        res = subprocess.run(["arp", "-a"], capture_output=True, timeout=5, text=True, check=False)
        text = res.stdout
    except Exception as exc:
        return {"available": False, "reason": str(exc)}

    rows = re.findall(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]+)\s+(\w+)", text)
    by_mac: dict[str, list[str]] = {}
    entries = []
    for ip, mac, kind in rows:
        mac_norm = mac.lower().replace("-", ":")
        entries.append({"ip": ip, "mac": mac_norm, "kind": kind})
        by_mac.setdefault(mac_norm, []).append(ip)

    dup = [{"mac": mac, "ips": ips} for mac, ips in by_mac.items() if len(ips) > 1]
    return {"available": True, "entries": entries, "duplicates": dup}


def recent_system32_changes(hours: int = 24, limit: int = 100) -> dict[str, Any]:
    """List files in System32 modified recently (malware persistence hint)."""
    if not IS_WINDOWS:
        return {"available": False}
    import os
    import time
    root = r"C:\Windows\System32"
    try:
        files = []
        cutoff = time.time() - hours * 3600
        for name in os.listdir(root):
            full = os.path.join(root, name)
            try:
                st = os.stat(full)
                if st.st_mtime > cutoff and os.path.isfile(full):
                    files.append({"name": name, "mtime": st.st_mtime})
            except (PermissionError, OSError):
                continue
        files.sort(key=lambda x: x["mtime"], reverse=True)
        return {"available": True, "files": files[:limit], "hours": hours}
    except PermissionError as exc:
        return {"available": False, "reason": str(exc)}


def windows_update_status() -> dict[str, Any]:
    """Best-effort Windows Update status check."""
    if not _powershell_available():
        return {"available": False}
    script = (
        "$k = Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 1; "
        "@{ LastHotfix = $k.HotFixID; InstalledOn = $k.InstalledOn } | ConvertTo-Json -Compress"
    )
    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(_run_powershell(script, timeout=10.0))
        rows = _parse_json_list(out)
        return {"available": True, **(rows[0] if rows else {})}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    finally:
        loop.close()
