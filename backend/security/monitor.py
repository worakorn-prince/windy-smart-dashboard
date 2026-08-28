"""Live security events monitor: continuously polls for new events and pushes them
as colored messages via the /ws/security stream.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Awaitable, Callable

import psutil

from config import DEFAULT_SUSPICIOUS_COUNTRIES
from security import geoip, winapi

logger = logging.getLogger("dashboard.secmonitor")


@dataclass
class Event:
    type: str
    timestamp: str
    title: str
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class SecurityMonitor:
    def __init__(self, on_event: Callable[[Event], Awaitable[None]] | None = None,
                 suspicious: list[str] | None = None):
        self._on_event = on_event
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._known_ports: set[str] = set()
        self._known_remotes: set[str] = set()
        self._known_failed_ips: set[str] = set()
        self.suspicious = suspicious or list(DEFAULT_SUSPICIOUS_COUNTRIES)

    def set_on_event(self, cb: Callable[[Event], Awaitable[None]]) -> None:
        self._on_event = cb

    async def _emit(self, evt: Event) -> None:
        if self._on_event:
            try:
                await self._on_event(evt)
            except Exception:
                logger.exception("Event callback failed")

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except TimeoutError:
                self._task.cancel()

    async def _run(self) -> None:
        # Initial refresh for Tor exits.
        await geoip.refresh_tor_exits()

        # Stagger concurrent pollers.
        t_ports = asyncio.create_task(self._poll_ports())
        t_remotes = asyncio.create_task(self._poll_remotes())
        t_failed = asyncio.create_task(self._poll_failed_logins())
        t_def = asyncio.create_task(self._poll_defender())
        try:
            await asyncio.gather(t_ports, t_remotes, t_failed, t_def)
        except asyncio.CancelledError:
            pass
        finally:
            for t in (t_ports, t_remotes, t_failed, t_def):
                if not t.done():
                    t.cancel()

    # ----- Pollers -----

    async def _poll_ports(self) -> None:
        from config import SECURITY_PORTS_INTERVAL
        while not self._stop.is_set():
            try:
                seen: set[str] = set()
                for c in psutil.net_connections(kind="inet"):
                    if c.status == psutil.CONN_LISTEN and c.laddr:
                        key = f"{c.laddr.ip}:{c.laddr.port}:{c.pid}"
                        seen.add(key)
                        if key not in self._known_ports:
                            name = ""
                            exe = ""
                            try:
                                if c.pid:
                                    p = psutil.Process(c.pid)
                                    name = p.name()
                                    exe = p.exe()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                            await self._emit(Event(
                                type="port_opened",
                                timestamp=datetime.now().isoformat(),
                                title=f"New listening port {c.laddr.port}/{name}",
                                detail={
                                    "ip": c.laddr.ip, "port": c.laddr.port,
                                    "pid": c.pid, "name": name, "exe": exe,
                                },
                            ))
                # If a previously-listening port is no longer listening.
                for old in list(self._known_ports - seen):
                    ip, port, pid = old.split(":")
                    await self._emit(Event(
                        type="port_closed",
                        timestamp=datetime.now().isoformat(),
                        title=f"Port closed {port}",
                        detail={"ip": ip, "port": int(port), "pid": int(pid) if pid.isdigit() else None},
                    ))
                self._known_ports = seen
            except Exception as exc:
                logger.debug("port poll failed: %s", exc)
            await asyncio.sleep(SECURITY_PORTS_INTERVAL)

    async def _poll_remotes(self) -> None:
        from config import SECURITY_CONNECTIONS_INTERVAL
        while not self._stop.is_set():
            try:
                seen: set[str] = set()
                new_ips: list[str] = []
                for c in psutil.net_connections(kind="inet"):
                    if c.status == psutil.CONN_ESTABLISHED and c.raddr and c.laddr:
                        ip = c.raddr.ip
                        if ip.startswith("127.") or ip in {"::1", "0.0.0.0"}:
                            continue
                        try:
                            iobj = __import__("ipaddress").ip_address(ip)
                            if iobj.is_private or iobj.is_loopback:
                                continue
                        except ValueError:
                            continue
                        key = f"{ip}:{c.raddr.port}:{c.pid}"
                        seen.add(key)
                        if key not in self._known_remotes and ip not in new_ips:
                            new_ips.append(ip)
                            name = ""
                            try:
                                if c.pid:
                                    name = psutil.Process(c.pid).name()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                            await self._emit(Event(
                                type="outbound_connection",
                                timestamp=datetime.now().isoformat(),
                                title=f"{name or 'process'} → {ip}:{c.raddr.port}",
                                detail={"ip": ip, "port": c.raddr.port, "pid": c.pid, "name": name},
                            ))
                            # geoIP lookup
                            geo = await geoip.lookup(ip, suspicious=self.suspicious)
                            if geo.get("available"):
                                if geo.get("suspicious_country"):
                                    await self._emit(Event(
                                        type="suspicious_outbound",
                                        timestamp=datetime.now().isoformat(),
                                        title=f"⚠️ Outbound to suspicious country {geo.get('country_code')}",
                                        detail={"ip": ip, "country": geo.get("country"),
                                                "country_code": geo.get("country_code"),
                                                "isp": geo.get("isp"), "pid": c.pid, "name": name},
                                    ))
                                if geo.get("is_tor"):
                                    await self._emit(Event(
                                        type="tor_outbound",
                                        timestamp=datetime.now().isoformat(),
                                        title=f"⚠️ Outbound to Tor exit node {ip}",
                                        detail={"ip": ip, "pid": c.pid, "name": name},
                                    ))
                # Forget old entries that disappeared.
                self._known_remotes = seen
            except Exception as exc:
                logger.debug("remotes poll failed: %s", exc)
            await asyncio.sleep(SECURITY_CONNECTIONS_INTERVAL)

    async def _poll_failed_logins(self) -> None:
        from config import SECURITY_FAILED_LOGINS_INTERVAL
        while not self._stop.is_set():
            try:
                events = await winapi.failed_logins(limit=50)
                cutoff = datetime.now() - timedelta(minutes=2)
                new_ips: set[str] = set()
                for e in events:
                    t = e.get("TimeCreated")
                    if not t:
                        continue
                    try:
                        dt = datetime.fromisoformat(str(t))
                    except (ValueError, TypeError):
                        continue
                    ip = e.get("IpAddress")
                    if dt.replace(tzinfo=None) > cutoff and ip and ip not in ("-", "::1", "127.0.0.1"):
                        key = f"{ip}:{dt.isoformat()}"
                        if key not in self._known_failed_ips:
                            new_ips.add(ip)
                            await self._emit(Event(
                                type="failed_login",
                                timestamp=datetime.now().isoformat(),
                                title=f"Failed login as '{e.get('TargetUser')}' from {ip}",
                                detail={"ip": ip, "user": e.get("TargetUser"),
                                        "logon_type": e.get("LogonType"),
                                        "workstation": e.get("Workstation"),
                                        "time": str(t)},
                            ))
                        self._known_failed_ips.add(key)
                if len(self._known_failed_ips) > 500:
                    self._known_failed_ips = set(list(self._known_failed_ips)[-500:])
            except Exception as exc:
                logger.debug("failed logins poll failed: %s", exc)
            await asyncio.sleep(SECURITY_FAILED_LOGINS_INTERVAL)

    async def _poll_defender(self) -> None:
        from config import SECURITY_DEFENDER_INTERVAL
        prev_rt = None
        while not self._stop.is_set():
            try:
                status = await winapi.defender_status()
                if status.get("available"):
                    rt = status.get("RealTimeProtectionEnabled")
                    if prev_rt is not None and rt != prev_rt:
                        if rt is False:
                            await self._emit(Event(
                                type="defender_disabled",
                                timestamp=datetime.now().isoformat(),
                                title="⚠️ Defender real-time protection DISABLED",
                                detail=status,
                            ))
                        elif rt is True:
                            await self._emit(Event(
                                type="defender_enabled",
                                timestamp=datetime.now().isoformat(),
                                title="Defender real-time protection enabled",
                                detail=status,
                            ))
                    prev_rt = rt
            except Exception as exc:
                logger.debug("defender poll failed: %s", exc)
            await asyncio.sleep(SECURITY_DEFENDER_INTERVAL)
