"""Async audit: collect snapshots from all 'doors' and produce a report.

This is the on-demand entry point invoked by POST /api/security/audit.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import psutil

from config import DEFAULT_SUSPICIOUS_COUNTRIES
from security import winapi
from security.findings import (
    Finding,
    f_arp_duplicate,
    f_defender_disabled,
    f_defender_signatures_stale,
    f_failed_logins_many,
    f_failed_logins_repeat_ip,
    f_firewall_disabled,
    f_guest_account,
    f_hosts_redirect,
    f_new_user,
    f_rdp_exposed,
    f_smb_exposed,
    f_ssh_exposed,
    f_suspicious_outbound,
    f_tor_outbound,
    f_unsigned_installed,
    f_unsigned_listener,
    f_wifi_weak_auth,
    risk_label,
)
from security.geoip import lookup, refresh_tor_exits

logger = logging.getLogger("dashboard.audit")


def _is_local(ip: str) -> bool:
    if not ip:
        return True
    try:
        ipobj = __import__("ipaddress").ip_address(ip)
    except ValueError:
        return False
    return ipobj.is_private or ipobj.is_loopback or ipobj.is_link_local


def _exe_trusted_path(exe_path: str) -> bool:
    """Quick path-based gate: only Microsoft-signed exes in Program Files or Windows."""
    if not exe_path:
        return False
    p = exe_path.lower().replace("/", "\\")
    trusted_prefixes = (
        "c:\\windows\\system32", "c:\\windows\\syswow64", "c:\\windows\\winsxs",
        "c:\\windows\\", "c:\\program files\\", "c:\\program files (x86)\\",
    )
    return any(p.startswith(prefix) for prefix in trusted_prefixes)


def _exe_signed_check(exe_path: str) -> bool:
    """Heuristic only — returns True if exe lives in a trusted system path.

    For a real Authenticode signature check see `_check_signatures_batch`.
    """
    return _exe_trusted_path(exe_path)


async def _check_signatures_batch(exe_paths: list[str]) -> dict[str, bool]:
    """Run PowerShell Get-AuthenticodeSignature for several exe paths at once.

    Returns a dict {path: is_signed}. Only the listening-port audit calls this.
    """
    if not exe_paths:
        return {}
    # Build a PowerShell snippet that emits "signed|<path>" lines.
    paths_ps = ",".join("'" + p.replace("'", "''") + "'" for p in exe_paths)
    script = (
        "$paths = @(" + paths_ps + "); "
        "foreach ($p in $paths) { "
        "  try { "
        "    $s = Get-AuthenticodeSignature -FilePath $p -ErrorAction SilentlyContinue; "
        "    if ($s.Status -eq 'Valid') { 'signed|' + $p } else { 'unsigned|' + $p } "
        "  } catch { 'unsigned|' + $p } "
        "}"
    )
    try:
        from security import winapi
        out = await winapi._run_powershell(script, timeout=20.0)
    except Exception as exc:
        logger.debug("signature check failed: %s", exc)
        return {p: False for p in exe_paths}

    result: dict[str, bool] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        verdict, path = line.split("|", 1)
        result[path] = (verdict.strip().lower() == "signed")
    # Any path we couldn't read defaults to False (treat as unverified).
    for p in exe_paths:
        result.setdefault(p, False)
    return result


async def _collect_ports() -> dict[str, Any]:
    """Inspect listening + established connections."""
    listening_ports: list[dict[str, Any]] = []
    established: list[dict[str, Any]] = []

    for c in psutil.net_connections(kind="inet"):
        try:
            laddr = c.laddr
            raddr = c.raddr
            if c.status == psutil.CONN_LISTEN and laddr:
                proc_name = ""
                proc_exe = ""
                proc_pid = c.pid or 0
                try:
                    if c.pid:
                        p = psutil.Process(c.pid)
                        proc_name = p.name()
                        proc_exe = p.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                listening_ports.append({
                    "pid": proc_pid,
                    "name": proc_name,
                    "exe": proc_exe,
                    "port": laddr.port,
                    "ip": laddr.ip,
                    "signed": _exe_signed_check(proc_exe),
                })
            elif c.status == psutil.CONN_ESTABLISHED and raddr and laddr:
                proc_name = ""
                proc_pid = c.pid or 0
                try:
                    if c.pid:
                        p = psutil.Process(c.pid)
                        proc_name = p.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                established.append({
                    "pid": proc_pid,
                    "name": proc_name,
                    "local": f"{laddr.ip}:{laddr.port}",
                    "remote_ip": raddr.ip,
                    "remote_port": raddr.port,
                })
        except Exception:
            continue

    return {"listening": listening_ports, "established": established}


async def _enrich_remotes(est: list[dict[str, Any]],
                         suspicious: list[str]) -> list[dict[str, Any]]:
    """Add geoIP info to outbound public remote IPs."""
    await refresh_tor_exits()
    public_ips = {c["remote_ip"] for c in est if c["remote_ip"] and not _is_local(c["remote_ip"])}
    # Cap lookups to avoid runaway costs.
    public_ips = set(list(public_ips)[:60])
    geo_map = await asyncio.gather(*[lookup(ip, suspicious=suspicious)
                                      for ip in public_ips],
                                    return_exceptions=True)
    geo_dict: dict[str, Any] = {}
    for ip, res in zip(public_ips, geo_map, strict=False):
        if isinstance(res, Exception):
            geo_dict[ip] = {"ip": ip, "available": False, "reason": str(res)}
        else:
            geo_dict[ip] = res

    out: list[dict[str, Any]] = []
    for c in est:
        c2 = dict(c)
        c2["geo"] = geo_dict.get(c["remote_ip"], {"ip": c["remote_ip"], "available": False})
        out.append(c2)
    return out


def _build_findings(data: dict[str, Any],
                    suspicious: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    # 1. Listening ports — RDP, SSH, SMB exposure.
    public_iface = ""
    private_iface_cookies = []
    for name, ips in (data.get("interfaces") or {}).items():
        if name.lower().startswith("loopback") or name.lower() == "lo":
            continue
        for ip in ips:
            v = ip.split("%")[0]
            try:
                ipobj = __import__("ipaddress").ip_address(v)
            except ValueError:
                continue
            if ipobj.version == 4 and not (ipobj.is_private or ipobj.is_loopback):
                public_iface = v
            else:
                private_iface_cookies.append((name, v))

    for s in data["net"].get("listening", []):
        port = s["port"]
        listening_on_public = (public_iface and s["ip"] in ("0.0.0.0", "::", public_iface))
        port_is_flagged = False
        if port == 3389:
            findings.append(f_rdp_exposed(listening_on_public))
            port_is_flagged = True
        elif port == 22:
            findings.append(f_ssh_exposed())
            port_is_flagged = True
        elif port in (139, 445):
            findings.append(f_smb_exposed(listening_on_public))
            port_is_flagged = True
        # "Unsigned process" finding only when:
        #   - the exe was checked and is genuinely unsigned, AND
        #   - we don't already have a port-based finding for it (no duplicates), AND
        #   - the process is not the Windows kernel (pid 4 has no exe path).
        if s.get("exe") and not s.get("signed") and not port_is_flagged and s.get("pid") not in (0, 4):
            findings.append(f_unsigned_listener(s["pid"], s["name"], port))

    # 2. Suspicious outbound (country or Tor).
    for c in data["net"].get("established", []):
        geo = c.get("geo", {})
        if not geo.get("available"):
            continue
        if geo.get("suspicious_country"):
            findings.append(f_suspicious_outbound(
                c["remote_ip"], geo.get("country") or "", geo.get("country_code") or "",
                c["pid"], c["name"],
            ))
        if geo.get("is_tor"):
            findings.append(f_tor_outbound(c["remote_ip"], c["pid"], c["name"]))

    # 3. Defender
    defender = data.get("defender", {})
    if defender.get("available"):
        rt = defender.get("RealTimeProtectionEnabled")
        av = defender.get("AntivirusEnabled")
        sig = defender.get("AntivirusSignatureLastUpdated") or defender.get("AntivirusSignatureLastUpdated ")
        if rt is False or av is False:
            findings.append(f_defender_disabled())
        if sig:
            try:
                sig_dt = datetime.fromisoformat(str(sig))
            except (ValueError, TypeError):
                sig_dt = None
            if sig_dt:
                age = (datetime.now(sig_dt.tzinfo) - sig_dt).total_seconds() / 86400
                if age > 7:
                    findings.append(f_defender_signatures_stale(age))

    # 4. Firewall
    fw = data.get("firewall", {})
    if fw.get("available"):
        for p in fw.get("profiles", []):
            name = p.get("Name", "").lower()
            enabled = p.get("Enabled")
            if enabled is False:
                findings.append(f_firewall_disabled(name))

    # 5. Failed logins
    fl = data.get("failed_logins", [])
    cutoff = datetime.now() - timedelta(hours=24)
    recent = []
    for r in fl:
        try:
            t = r.get("TimeCreated")
            if not t:
                continue
            dt = datetime.fromisoformat(str(t))
            if dt.replace(tzinfo=None) > cutoff:
                recent.append(r)
        except (ValueError, TypeError):
            continue
    if len(recent) > 10:
        findings.append(f_failed_logins_many(len(recent)))
    # Repeat IPs
    ip_counts: dict[str, int] = {}
    for r in recent:
        ip = r.get("IpAddress")
        if ip and ip not in ("-", "::1", "127.0.0.1"):
            ip_counts[ip] = ip_counts.get(ip, 0) + 1
    for ip, n in ip_counts.items():
        if n >= 3:
            findings.append(f_failed_logins_repeat_ip(ip, n))

    # 6. Users: Guest enabled + new accounts.
    users = data.get("users", [])
    for u in users:
        name = (u.get("Name") or "").lower()
        if name == "guest" and u.get("Enabled"):
            findings.append(f_guest_account())
        try:
            pwd_set = u.get("PasswordLastSet")
            if pwd_set:
                pwd_dt = datetime.fromisoformat(str(pwd_set))
                if (datetime.now(pwd_dt.tzinfo) - pwd_dt).days < 7:
                    findings.append(f_new_user(u.get("Name")))
        except (ValueError, TypeError):
            continue

    # 7. WiFi weak auth
    for w in data.get("wifi_profiles", []):
        ssid = w.get("SSID") or w.get("Ssid") or ""
        auth = (w.get("Auth") or "").lower()
        if not auth:
            continue
        if "wep" in auth or "open" in auth or "shared" in auth:
            findings.append(f_wifi_weak_auth(ssid, auth))

    # 8. Hosts file redirects.
    hosts = data.get("hosts", {})
    for s in (hosts.get("suspicious") or [])[:20]:
        findings.append(f_hosts_redirect(s["host"], s["ip"], s["reason"]))

    # 9. ARP duplicates.
    arp = data.get("arp", {})
    for d in (arp.get("duplicates") or [])[:10]:
        findings.append(f_arp_duplicate(d["mac"], d["ips"]))

    # 10. Installed programs — flag missing publisher.
    for p in data.get("installed_programs", [])[:50]:
        if not p.get("Publisher") and p.get("DisplayName"):
            findings.append(f_unsigned_installed(
                p.get("DisplayName"), p.get("Publisher"),
            ))

    return findings


async def run_audit(suspicious_override: list[str] | None = None) -> dict[str, Any]:
    """Run a complete audit synchronously-ish (overlapped I/O).

    Returns a JSON-serializable report dictionary.
    """
    suspicious = suspicious_override or list(DEFAULT_SUSPICIOUS_COUNTRIES)
    started = time.monotonic()

    ports_task = asyncio.create_task(_collect_ports())
    tasks_defender = asyncio.create_task(winapi.defender_status())
    tasks_logins = asyncio.create_task(winapi.failed_logins(limit=100))
    tasks_firewall = asyncio.create_task(winapi.firewall_status())
    tasks_scheduled = asyncio.create_task(winapi.list_scheduled_tasks())
    tasks_installed = asyncio.create_task(winapi.list_installed_programs(limit=200))
    tasks_users = asyncio.create_task(winapi.user_accounts())
    tasks_wifi = asyncio.create_task(winapi.wifi_profiles())
    hosts = winapi.read_hosts_file()
    arp = winapi.arp_table()
    sys_changes = winapi.recent_system32_changes(hours=24)

    ports = await ports_task
    established = await _enrich_remotes(ports["established"], suspicious)
    ports["established"] = established

    # Real Authenticode signature checks for the listener exes (batched).
    listener_exes = [s["exe"] for s in ports["listening"] if s.get("exe")]
    sig_map = await _check_signatures_batch(listener_exes)
    for s in ports["listening"]:
        if s.get("exe"):
            s["signed"] = bool(sig_map.get(s["exe"], False))
            # If we got a real signature result, store that too.
            s["authenticode_verified"] = s["signed"]

    defender = await tasks_defender
    failed_logins = await tasks_logins
    firewall = await tasks_firewall
    scheduled = await tasks_scheduled
    installed = await tasks_installed
    users = await tasks_users
    wifi = await tasks_wifi
    update_status = winapi.windows_update_status()

    interface_addrs = {}
    for name, snics in psutil.net_if_addrs().items():
        ips = []
        for sn in snics:
            addr = getattr(sn, "address", None) or (sn if isinstance(sn, str) else "")
            if not addr:
                continue
            addr = addr.split("%")[0]
            ips.append(addr)
        if any(not _is_local(ip) for ip in ips):
            interface_addrs[name] = ips

    data = {
        "interfaces": interface_addrs,
        "net": ports,
        "defender": defender,
        "failed_logins": failed_logins,
        "firewall": firewall,
        "scheduled_tasks": scheduled,
        "installed_programs": installed,
        "users": users,
        "wifi_profiles": wifi,
        "hosts": hosts,
        "arp": arp,
        "recent_system32": sys_changes,
        "windows_update": update_status,
        "suspicious_countries": suspicious,
    }

    findings = _build_findings(data, suspicious)
    total = sum(f.weight for f in findings)
    return {
        "generated_at": datetime.now().isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000, 0),
        "riskscore": total,
        "risk_label": risk_label(total),
        "findings": [f.to_dict() for f in findings],
        "data": data,
    }
