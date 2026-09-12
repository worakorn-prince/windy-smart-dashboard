"""Security actions: kill process, block/unblock outbound IP via Windows firewall.

All commands require Administrator privileges and will report failure otherwise.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
import time
from typing import Any

import psutil

from config import PROTECTED_PIDS

logger = logging.getLogger("dashboard.actions")

RULE_PREFIX = "WSDB_"
LEGACY_RULE_PREFIX = "WindySmartDashboard_block_"
_RULE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


async def kill_process(pid: int, force: bool = False) -> dict[str, Any]:
    """Terminate a process by PID. Refuses system-critical PIDs."""
    if pid in PROTECTED_PIDS:
        return {"ok": False, "reason": "protected_pid"}
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return {"ok": False, "reason": "no_such_process"}
    try:
        p.terminate()
    except psutil.AccessDenied:
        return {"ok": False, "reason": "access_denied"}
    if force:
        try:
            p.kill()
        except psutil.AccessDenied:
            return {"ok": False, "reason": "access_denied"}

    # Wait up to 3 seconds for the process to exit.
    for _ in range(15):
        if not p.is_running():
            return {"ok": True, "pid": pid, "name": p.name()}
        await asyncio.sleep(0.2)
    return {"ok": False, "reason": "still_running", "pid": pid, "name": p.name()}


def _make_rule_name(ip: str) -> str:
    """Build a unique firewall rule name for an IP."""
    digest = hashlib.sha256(f"{ip}_{time.time_ns()}".encode()).hexdigest()[:16]
    return f"{RULE_PREFIX}{digest}"


def _validate_rule_name(rule_name: str) -> bool:
    """Return True when a rule name belongs to this dashboard."""
    if not isinstance(rule_name, str):
        return False
    if not _RULE_NAME_RE.match(rule_name):
        return False
    return rule_name.startswith((RULE_PREFIX, LEGACY_RULE_PREFIX))


async def block_ip(ip: str) -> dict[str, Any]:
    """Create a Windows firewall rule to block outbound traffic to an IP."""
    if not _validate_ip(ip):
        return {"ok": False, "reason": "invalid_ip"}
    rule_name = _make_rule_name(ip)
    script = (
        f"netsh advfirewall firewall add rule name=\"{rule_name}\" "
        f"dir=out action=block remoteip={ip}"
    )
    try:
        res = await _run_shell(script)
    except Exception:
        logger.exception("block_ip failed")
        return {"ok": False, "reason": "block_failed"}
    if "OK" in res or "ok" in res.lower():
        return {"ok": True, "ip": ip, "rule_name": rule_name}
    if "requires elevation" in res.lower() or "access" in res.lower():
        return {"ok": False, "reason": "requires_admin", "stdout": res}
    return {"ok": False, "reason": "unexpected_output", "stdout": res}


async def unblock_ip(rule_name: str) -> dict[str, Any]:
    """Remove a firewall block rule by name, returning the result."""
    if not _validate_rule_name(rule_name):
        return {"ok": False, "reason": "invalid_rule_name"}
    script = f"netsh advfirewall firewall delete rule name=\"{rule_name}\""
    try:
        res = await _run_shell(script)
    except Exception:
        logger.exception("unblock_ip failed")
        return {"ok": False, "reason": "unblock_failed"}
    if "deleted" in res.lower() or "no rule" in res.lower():
        return {"ok": True, "rule_name": rule_name}
    if "elevation" in res.lower() or "access" in res.lower():
        return {"ok": False, "reason": "requires_admin"}
    return {"ok": False, "reason": "unexpected_output", "stdout": res}


async def list_block_rules() -> dict[str, Any]:
    """List firewall block rules created by this dashboard."""
    # netsh outputs "Rule Name:" records separated by blank lines.
    script = "netsh advfirewall firewall show rule name=all dir=out"
    try:
        res = await _run_shell_with_timeout(script, timeout=15.0)
    except Exception:
        logger.exception("list_block_rules failed")
        return {"ok": False, "reason": "list_failed", "rules": []}

    rules: list[dict[str, Any]] = []
    # Split records on blank line.
    for record in res.replace("\r\n", "\n").split("\n\n"):
        if RULE_PREFIX not in record and LEGACY_RULE_PREFIX not in record:
            continue
        name = ""
        rip = ""
        for line in record.split("\n"):
            line = line.strip()
            if line.lower().startswith("rule name:"):
                name = line.split(":", 1)[1].strip()
            elif line.lower().startswith("remoteip:"):
                rip = line.split(":", 1)[1].strip()
        if name:
            rules.append({"name": name, "ip": rip})
    return {"ok": True, "rules": rules}


def _validate_ip(ip: str) -> bool:
    """Return True when a string is a valid IP address."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


async def _run_shell(cmd: str) -> str:
    """Run a shell command with the default timeout."""
    return await _run_shell_with_timeout(cmd, timeout=15.0)


async def _run_shell_with_timeout(cmd: str, timeout: float = 15.0) -> str:
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
    return out.decode("utf-8", errors="replace")


async def _run_shell_ps(script: str) -> str:
    return await _run_shell_ps_with_timeout(script, timeout=15.0)


async def _run_shell_ps_with_timeout(script: str, timeout: float = 15.0) -> str:
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return out.decode("utf-8", errors="replace")
