"""Route collector for route table snapshots and traceroute."""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import logging
import platform
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_config
from ..storage.repositories import (
    DnsProbeRepository,
    DiagnosticResultRepository,
    DiagnosticSessionRepository,
    generate_session_id,
)

logger = logging.getLogger("dashboard.internet_insights.collectors.route")


@dataclass
class RouteEntry:
    destination: str
    prefix_length: int
    next_hop: str
    interface_index: int
    metric: int
    protocol: int
    age: int
    origin: int


@dataclass
class TracerouteHop:
    hop: int
    address: str | None
    rtt_ms: float | None
    status: str  # success, timeout, unreachable


class RouteCollector:
    """Background collector for route table snapshots and on-demand traceroute."""

    def __init__(self):
        self.config = get_config()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._consecutive_failures = 0
        self._run_lock = asyncio.Lock()
        self._is_windows = platform.system() == "Windows"
        self._iphlpapi = None
        self._ws2_32 = None
        self._init_windows_api()

        # Repositories (lazy init)
        self._dns_repo: DnsProbeRepository | None = None
        self._diag_session_repo: DiagnosticSessionRepository | None = None
        self._diag_result_repo: DiagnosticResultRepository | None = None

    @property
    def name(self) -> str:
        return "route"

    def _init_windows_api(self) -> None:
        """Initialize Windows IPHLPAPI and WS2_32 for route/traceroute functions."""
        if not self._is_windows:
            return
        try:
            self._iphlpapi = ctypes.windll.LoadLibrary("iphlpapi.dll")
            self._ws2_32 = ctypes.windll.LoadLibrary("ws2_32.dll")
            logger.debug("Windows IPHLPAPI and WS2_32 loaded successfully")
        except Exception as e:
            logger.warning("Failed to load Windows networking DLLs: %s", e)
            self._iphlpapi = None
            self._ws2_32 = None

    def _get_repos(self):
        """Lazy initialize repositories."""
        if self._dns_repo is None:
            from ..storage.repositories import DnsProbeRepository, DiagnosticSessionRepository, DiagnosticResultRepository
            self._dns_repo = DnsProbeRepository()
            self._diag_session_repo = DiagnosticSessionRepository()
            self._diag_result_repo = DiagnosticResultRepository()
        return self._dns_repo, self._diag_session_repo, self._diag_result_repo

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_loop(self) -> None:
        """Periodic route table snapshot collection."""
        while self._running:
            if self._run_lock.locked():
                await asyncio.sleep(0.5)
                continue

            start = time.monotonic()
            self._last_run_start = start

            try:
                await self._collect_route_snapshot()
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("RouteCollector failed (%d): %s", self._consecutive_failures, e)
            finally:
                self._last_run_duration = time.monotonic() - start

            sleep_time = max(0.1, self.config.route_interval - self._last_run_duration)
            await asyncio.sleep(sleep_time)

    async def _collect_route_snapshot(self) -> None:
        """Collect current route table snapshot."""
        if self._is_windows and self._iphlpapi:
            routes = await asyncio.to_thread(self._get_windows_routes)
        else:
            routes = await asyncio.to_thread(self._get_psutil_routes)

        # Store route snapshot in diagnostic sessions/results
        # (using existing diagnostic tables for route data)
        if routes:
            _, session_repo, result_repo = self._get_repos()
            session_id = generate_session_id()
            session = await asyncio.to_thread(
                session_repo.create,
                type('DiagnosticSession', (), {
                    'id': session_id,
                    'started_at': time.time(),
                    'completed_at': time.time(),
                    'status': 'completed',
                    'target': 'route_snapshot',
                    'diagnostic_type': 'route',
                    'config_json': '{}',
                    'summary_json': f'{{"route_count": {len(routes)}}}',
                    'error': None,
                })()
            )
            results = [
                type('DiagnosticResult', (), {
                    'session_id': session_id,
                    'ts': time.time(),
                    'sequence': i,
                    'result_type': 'route',
                    'payload_json': str(route.__dict__).replace("'", '"'),
                })()
                for i, route in enumerate(routes)
            ]
            await asyncio.to_thread(result_repo.insert_batch, results)

    def _get_windows_routes(self) -> list[RouteEntry]:
        """Get IPv4/IPv6 route table via GetIpForwardTable2."""
        routes = []

        # MIB_IPFORWARD_TABLE2 and MIB_IPFORWARD_ROW2 structures
        # This is a simplified version - full implementation requires complex structures
        try:
            # Use GetIpForwardTable2 for IPv4 (AF_INET=2) and IPv6 (AF_INET6=23)
            # For simplicity, we'll use a fallback approach with netsh or psutil
            pass
        except Exception as e:
            logger.warning("GetIpForwardTable2 failed: %s", e)

        return routes

    def _get_psutil_routes(self) -> list[RouteEntry]:
        """Get route table via psutil (cross-platform fallback)."""
        import psutil
        routes = []
        try:
            # psutil.net_if_stats() doesn't provide routing table
            # Use platform-specific commands or netifaces if available
            # For now, return empty - will be populated by GetBestRoute2 on demand
            pass
        except Exception as e:
            logger.warning("psutil route collection failed: %s", e)
        return routes

    def get_default_gateway(self) -> tuple[str | None, int | None]:
        """Get default gateway IP and interface index."""
        if self._is_windows and self._iphlpapi:
            return self._get_windows_default_gateway()
        return self._get_psutil_default_gateway()

    def _get_windows_default_gateway(self) -> tuple[str | None, int | None]:
        """Get default gateway via GetIpForwardTable2 or GetBestRoute2."""
        try:
            # Use GetBestRoute2 to find route to a known internet address
            # This gives us the interface index and next hop for the default route
            dest_addr = socket.inet_aton("8.8.8.8")
            source_addr = socket.inet_aton("0.0.0.0")

            # MIB_IPFORWARD_ROW2 for result
            class SOCKADDR_INET(ctypes.Structure):
                _fields_ = [
                    ("si_family", ctypes.c_ushort),
                    ("Ipv4", ctypes.c_byte * 4),
                    ("Ipv6", ctypes.c_byte * 16),
                ]

            class MIB_IPFORWARD_ROW2(ctypes.Structure):
                _fields_ = [
                    ("InterfaceLuid", ctypes.c_ulonglong),
                    ("InterfaceIndex", ctypes.c_uint),
                    ("DestinationPrefix", SOCKADDR_INET),  # Simplified
                    ("PrefixLength", ctypes.c_uchar),
                    ("NextHop", SOCKADDR_INET),
                    ("SitePrefixLength", ctypes.c_uchar),
                    ("ValidLifetime", ctypes.c_ulong),
                    ("PreferredLifetime", ctypes.c_ulong),
                    ("Metric", ctypes.c_ulong),
                    ("Protocol", ctypes.c_ulong),
                    ("Loopback", ctypes.c_bool),
                    ("AutoconfigureAddress", ctypes.c_bool),
                    ("Publish", ctypes.c_bool),
                    ("Immortal", ctypes.c_bool),
                    ("Age", ctypes.c_ulong),
                    ("Origin", ctypes.c_ulong),
                ]

            # GetBestRoute2 signature
            # NETIOAPI_API GetBestRoute2(
            #   NET_IFINDEX       InterfaceIndex,
            #   PSOCKADDR_INET    SourceAddress,
            #   PSOCKADDR_INET    DestinationAddress,
            #   PMIB_IPFORWARD_ROW2 Route
            # )
            self._iphlpapi.GetBestRoute2.argtypes = [
                ctypes.c_uint,
                ctypes.POINTER(SOCKADDR_INET),
                ctypes.POINTER(SOCKADDR_INET),
                ctypes.POINTER(MIB_IPFORWARD_ROW2),
            ]
            self._iphlpapi.GetBestRoute2.restype = ctypes.c_ulong

            dest = SOCKADDR_INET()
            dest.si_family = socket.AF_INET
            dest.Ipv4 = (ctypes.c_byte * 4)(*dest_addr)

            src = SOCKADDR_INET()
            src.si_family = socket.AF_INET
            src.Ipv4 = (ctypes.c_byte * 4)(*source_addr)

            route = MIB_IPFORWARD_ROW2()
            result = self._iphlpapi.GetBestRoute2(0, ctypes.byref(src), ctypes.byref(dest), ctypes.byref(route))

            if result == 0:
                # Extract next hop
                next_hop_bytes = bytes(route.NextHop.Ipv4[:4])
                next_hop = socket.inet_ntoa(next_hop_bytes)
                return next_hop, route.InterfaceIndex
        except Exception as e:
            logger.warning("GetBestRoute2 failed: %s", e)
        return None, None

    def _get_psutil_default_gateway(self) -> tuple[str | None, int | None]:
        """Get default gateway via psutil/netifaces fallback."""
        try:
            import netifaces
            gateways = netifaces.gateways()
            default_gw = gateways.get('default', {}).get(netifaces.AF_INET)
            if default_gw:
                return default_gw[0], default_gw[1] if len(default_gw) > 1 else None
        except Exception:
            pass
        return None, None

    async def traceroute(
        self,
        target: str,
        max_hops: int = 30,
        timeout_ms: int = 3000,
        protocol: str = "icmp"
    ) -> list[TracerouteHop]:
        """Perform traceroute to target."""
        if self._is_windows:
            return await asyncio.to_thread(self._traceroute_windows, target, max_hops, timeout_ms, protocol)
        return await asyncio.to_thread(self._traceroute_unix, target, max_hops, timeout_ms, protocol)

    def _traceroute_windows(self, target: str, max_hops: int, timeout_ms: int, protocol: str) -> list[TracerouteHop]:
        """Windows traceroute using ICMP (tracert-style) or UDP."""
        hops = []
        try:
            # Resolve target
            dest_ip = socket.gethostbyname(target)
        except socket.gaierror:
            return [TracerouteHop(hop=0, address=None, rtt_ms=None, status="dns_failure")]

        # Use raw ICMP sockets on Windows (requires admin) or UDP fallback
        # For non-admin, use UDP with increasing TTL
        if protocol == "icmp":
            return self._traceroute_icmp_windows(dest_ip, max_hops, timeout_ms)
        return self._traceroute_udp_windows(dest_ip, max_hops, timeout_ms)

    def _traceroute_icmp_windows(self, dest_ip: str, max_hops: int, timeout_ms: int) -> list[TracerouteHop]:
        """ICMP traceroute on Windows (requires raw socket / admin)."""
        hops = []
        try:
            # ICMP raw socket requires admin privileges
            icmp_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            icmp_socket.settimeout(timeout_ms / 1000.0)

            for ttl in range(1, max_hops + 1):
                icmp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)

                # Build ICMP echo request
                icmp_type = 8  # Echo request
                icmp_code = 0
                icmp_checksum = 0
                icmp_id = 12345
                icmp_seq = ttl
                header = struct.pack("!BBHHH", icmp_type, icmp_code, icmp_checksum, icmp_id, icmp_seq)
                checksum = self._checksum(header)
                header = struct.pack("!BBHHH", icmp_type, icmp_code, checksum, icmp_id, icmp_seq)

                start = time.time()
                try:
                    icmp_socket.sendto(header, (dest_ip, 0))
                    data, addr = icmp_socket.recvfrom(1024)
                    rtt_ms = round((time.time() - start) * 1000, 1)
                    hops.append(TracerouteHop(hop=ttl, address=addr[0], rtt_ms=rtt_ms, status="success"))

                    # Check if we reached destination
                    if addr[0] == dest_ip:
                        break
                except socket.timeout:
                    hops.append(TracerouteHop(hop=ttl, address=None, rtt_ms=None, status="timeout"))
                except Exception:
                    hops.append(TracerouteHop(hop=ttl, address=None, rtt_ms=None, status="error"))

            icmp_socket.close()
        except PermissionError:
            logger.warning("ICMP traceroute requires admin privileges, falling back to UDP")
            return self._traceroute_udp_windows(dest_ip, max_hops, timeout_ms)
        except Exception as e:
            logger.warning("ICMP traceroute failed: %s", e)

        return hops

    def _traceroute_udp_windows(self, dest_ip: str, max_hops: int, timeout_ms: int) -> list[TracerouteHop]:
        """UDP traceroute on Windows (no admin required)."""
        hops = []
        port = 33434  # Standard traceroute port range

        for ttl in range(1, max_hops + 1):
            try:
                # Create UDP socket with TTL
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
                sock.settimeout(timeout_ms / 1000.0)

                start = time.time()
                try:
                    sock.sendto(b"traceroute", (dest_ip, port))
                    data, addr = sock.recvfrom(1024)
                    rtt_ms = round((time.time() - start) * 1000, 1)
                    hops.append(TracerouteHop(hop=ttl, address=addr[0], rtt_ms=rtt_ms, status="success"))

                    if addr[0] == dest_ip:
                        sock.close()
                        break
                except socket.timeout:
                    hops.append(TracerouteHop(hop=ttl, address=None, rtt_ms=None, status="timeout"))
                except ConnectionRefusedError:
                    # Destination reached (port unreachable)
                    rtt_ms = round((time.time() - start) * 1000, 1)
                    hops.append(TracerouteHop(hop=ttl, address=dest_ip, rtt_ms=rtt_ms, status="success"))
                    sock.close()
                    break
                except Exception:
                    hops.append(TracerouteHop(hop=ttl, address=None, rtt_ms=None, status="error"))
                finally:
                    sock.close()
            except Exception as e:
                logger.warning("UDP traceroute hop %d failed: %s", ttl, e)
                hops.append(TracerouteHop(hop=ttl, address=None, rtt_ms=None, status="error"))

        return hops

    def _traceroute_unix(self, target: str, max_hops: int, timeout_ms: int, protocol: str) -> list[TracerouteHop]:
        """Unix traceroute (Linux/macOS)."""
        # Similar implementation for Unix
        return self._traceroute_udp_windows(target, max_hops, timeout_ms)  # Reuse UDP logic

    def _checksum(self, data: bytes) -> int:
        """Calculate ICMP checksum."""
        if len(data) % 2:
            data += b'\x00'
        s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
        s = (s >> 16) + (s & 0xFFFF)
        s += s >> 16
        return ~s & 0xFFFF

    def get_status(self) -> dict[str, Any]:
        gateway_ip, gateway_iface = self.get_default_gateway()
        return {
            "name": self.name,
            "running": self._running,
            "interval_sec": self.config.route_interval,
            "last_run_duration_sec": self._last_run_duration,
            "consecutive_failures": self._consecutive_failures,
            "platform": platform.system(),
            "windows_api_available": self._iphlpapi is not None,
            "default_gateway": gateway_ip,
            "gateway_interface_index": gateway_iface,
        }