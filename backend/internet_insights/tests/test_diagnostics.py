"""Tests for on-demand diagnostics: validate_target, tcp, tls, http, mtu."""

from __future__ import annotations

import asyncio
import socket
import time
from datetime import UTC, datetime

import httpcore
import httpx
import pytest

from internet_insights.diagnostics import validate_target, validate_timeout_ms
from internet_insights.diagnostics import http as http_diag
from internet_insights.diagnostics import mtu as mtu_diag
from internet_insights.diagnostics import tcp as tcp_diag
from internet_insights.diagnostics import tls as tls_diag
from internet_insights.diagnostics.http import SsrfBlockedError, redact_url
from internet_insights.diagnostics.http import _PinnedIpNetworkBackend


class TestValidateTarget:
    def test_valid_hostname_is_lowercased(self):
        assert validate_target("Example.COM") == "example.com"

    @pytest.mark.parametrize("target", ["1.1.1.1", "2606:4700::1111"])
    def test_valid_ip_literals(self, target: str):
        assert validate_target(target) == target

    @pytest.mark.parametrize("target", ["", "   ", "a b"])
    def test_empty_or_whitespace_rejected(self, target: str):
        with pytest.raises(ValueError):
            validate_target(target)

    @pytest.mark.parametrize("target", [None, 123, b"example.com"])
    def test_non_string_rejected(self, target):
        with pytest.raises(TypeError):
            validate_target(target)

    @pytest.mark.parametrize("target", ["https://example.com", "http://1.1.1.1", "ftp://x.dev"])
    def test_scheme_prefix_rejected(self, target: str):
        with pytest.raises(ValueError):
            validate_target(target)

    @pytest.mark.parametrize("target", ["192.168.1.10", "10.0.0.5", "127.0.0.1", "169.254.9.9"])
    def test_private_ipv4_rejected(self, target: str):
        with pytest.raises(ValueError):
            validate_target(target)

    @pytest.mark.parametrize("target", ["::1", "fe80::1"])
    def test_private_ipv6_rejected(self, target: str):
        with pytest.raises(ValueError):
            validate_target(target)

    @pytest.mark.parametrize("target", ["192.168.1.10", "10.0.0.5", "127.0.0.1", "169.254.9.9", "::1"])
    def test_allow_private_accepts_private_targets(self, target: str):
        assert validate_target(target, allow_private=True) == target

    def test_hostname_length_boundaries(self):
        too_long = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 63])
        assert len(too_long) == 255
        with pytest.raises(ValueError):
            validate_target(too_long)
        ok = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61])
        assert len(ok) == 253
        assert validate_target(ok) == ok


class TestTcpConnect:
    @pytest.mark.asyncio
    async def test_success_reports_duration(self, monkeypatch):
        monkeypatch.setattr(tcp_diag, "_connect_sync", lambda host, port, timeout_sec: None)
        result = await tcp_diag.tcp_connect("example.com", 443, timeout_ms=1000)
        assert result["status"] == "success"
        assert result["duration_ms"] is not None
        assert result["error_code"] is None

    @pytest.mark.asyncio
    async def test_connection_refused(self, monkeypatch):
        def _refused(host, port, timeout_sec):
            raise ConnectionRefusedError("refused")

        monkeypatch.setattr(tcp_diag, "_connect_sync", _refused)
        result = await tcp_diag.tcp_connect("example.com", 443)
        assert result["status"] == "refused"
        assert result["error_code"] == "ConnectionRefusedError"

    @pytest.mark.asyncio
    async def test_timeout(self, monkeypatch):
        def _timeout(host, port, timeout_sec):
            raise TimeoutError

        monkeypatch.setattr(tcp_diag, "_connect_sync", _timeout)
        result = await tcp_diag.tcp_connect("example.com", 443)
        assert result["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_generic_error(self, monkeypatch):
        def _boom(host, port, timeout_sec):
            raise RuntimeError("boom")

        monkeypatch.setattr(tcp_diag, "_connect_sync", _boom)
        result = await tcp_diag.tcp_connect("example.com", 443)
        assert result["status"] == "error"
        assert result["error_code"] == "RuntimeError"


def _fake_tls_result(version: str = "TLSv1.3", cipher: str = "TLS_AES_128_GCM_SHA256") -> tls_diag._TlsResult:
    info = tls_diag._TlsResult()
    info.version = version
    info.cipher = cipher
    info.cert_not_after = time.time() + 3600.0
    info.cert_expiry = datetime.fromtimestamp(info.cert_not_after, tz=UTC).isoformat()
    return info


class TestTlsHandshake:
    @pytest.mark.asyncio
    async def test_success_returns_version_cipher_and_cert(self, monkeypatch):
        monkeypatch.setattr(tls_diag, "_handshake_sync", lambda *args, **kwargs: _fake_tls_result())
        result = await tls_diag.tls_handshake("example.com", port=443, timeout_ms=1000)
        assert result["status"] == "success"
        assert result["version"] == "TLSv1.3"
        assert result["cipher"] == "TLS_AES_128_GCM_SHA256"
        assert result["cert_valid"] is True
        assert result["cert_expiry"] is not None

    @pytest.mark.asyncio
    async def test_timeout(self, monkeypatch):
        def _timeout(*args, **kwargs):
            raise TimeoutError

        monkeypatch.setattr(tls_diag, "_handshake_sync", _timeout)
        result = await tls_diag.tls_handshake("example.com", timeout_ms=1000)
        assert result["status"] == "timeout"
        assert result["version"] is None


def _resolver_for(ip: str):
    def _getaddrinfo(host, port=None, family=0, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


class TestHttpDiagnostic:
    @staticmethod
    def _handler_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
        # Plain bytes: async-generator content is incompatible with httpx
        # MockTransport under stream=True (httpx 0.28 raises TypeError).
        return httpx.Response(status_code, headers=headers, content=b"")

    @pytest.mark.asyncio
    async def test_success_with_mock_transport(self, monkeypatch):
        monkeypatch.setattr(http_diag.socket, "getaddrinfo", _resolver_for("93.184.216.34"))

        def handler(request: httpx.Request) -> httpx.Response:
            return self._handler_response(200)

        result = await http_diag.http_diagnostic("http://example.com/x", transport=httpx.MockTransport(handler))
        assert result["status"] == "success"
        assert result["status_code"] == 200
        assert result["redirect_chain"] == []
        assert result["dns_ms"] is not None
        assert result["ttfb_ms"] is not None
        assert result["total_ms"] is not None

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_blocked(self, monkeypatch):
        def _resolver(host, port=None, family=0, type=0):
            ip = "93.184.216.34" if "example.com" in str(host) else "192.168.0.10"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

        monkeypatch.setattr(http_diag.socket, "getaddrinfo", _resolver)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return self._handler_response(302, headers={"Location": "http://192.168.0.10/next"})
            return self._handler_response(200)

        with pytest.raises(SsrfBlockedError):
            await http_diag.http_diagnostic("http://example.com/start", transport=httpx.MockTransport(handler))

    @pytest.mark.asyncio
    async def test_non_http_scheme_rejected(self):
        with pytest.raises(ValueError):
            await http_diag.http_diagnostic("ftp://example.com/file")

    @pytest.mark.asyncio
    async def test_credentials_in_url_rejected_and_redact_url_works(self):
        with pytest.raises(ValueError):
            await http_diag.http_diagnostic("http://user:pass@example.com/")
        assert redact_url("https://user:pass@example.com/path") == "https://REDACTED@example.com/path"
        assert redact_url("https://example.com/path") == "https://example.com/path"

    @pytest.mark.asyncio
    async def test_body_truncated_at_size_cap(self, monkeypatch):
        monkeypatch.setattr(http_diag.socket, "getaddrinfo", _resolver_for("93.184.216.34"))
        monkeypatch.setattr(http_diag, "MAX_RESPONSE_BODY_BYTES", 16)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=bytes(range(64)))

        result = await http_diag.http_diagnostic("http://example.com/big", transport=httpx.MockTransport(handler))
        assert result["status"] == "success"
        assert result["status_code"] == 200
        assert result["content_length"] == 16
        assert result["body_truncated"] is True
        assert result["ttfb_ms"] is not None
        assert result["total_ms"] is not None


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    """Delegate that records every dial target and fails the connection."""

    def __init__(self, connect_error: Exception | None = None):
        self.dial_targets: list[str] = []
        self._connect_error = connect_error

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.dial_targets.append(str(host))
        if self._connect_error is not None:
            raise self._connect_error
        raise OSError(f"no route to {host}")


class TestPinnedTransportSecurity:
    """MAJOR-3: TOCTOU closure + validated-IP-only dialing + fail-closed guard."""

    @pytest.mark.asyncio
    async def test_rebinding_to_private_ip_blocked_at_connect_time(self, monkeypatch):
        public_ip, private_ip = "93.184.216.34", "192.168.0.10"
        calls = {"n": 0}

        def _rebinding_resolver(host, port=None, family=0, type=0):
            calls["n"] += 1
            ip = public_ip if calls["n"] == 1 else private_ip
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

        monkeypatch.setattr(http_diag.socket, "getaddrinfo", _rebinding_resolver)
        delegate = _RecordingBackend()
        backend = http_diag._PinnedIpNetworkBackend(delegate, allow_private=False)

        await http_diag._resolve_and_guard("example.com", allow_private=False)

        with pytest.raises(SsrfBlockedError):
            await backend.connect_tcp("example.com", 80, timeout=5.0)

        assert calls["n"] == 2
        assert delegate.dial_targets == []

    @pytest.mark.asyncio
    async def test_delegate_receives_only_validated_ip(self, monkeypatch):
        monkeypatch.setattr(http_diag.socket, "getaddrinfo", _resolver_for("93.184.216.34"))
        delegate = _RecordingBackend()
        backend = http_diag._PinnedIpNetworkBackend(delegate, allow_private=False)

        with pytest.raises(OSError, match=r"no route to 93\.184\.216\.34"):
            await backend.connect_tcp("example.com", 443, timeout=5.0)

        assert delegate.dial_targets == ["93.184.216.34"]

    @pytest.mark.asyncio
    async def test_deadline_shared_across_candidates(self, monkeypatch):
        ips = ["93.184.216.34", "93.184.216.35", "93.184.216.36"]

        def _multi_resolver(host, port=None, family=0, type=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]

        monkeypatch.setattr(http_diag.socket, "getaddrinfo", _multi_resolver)

        class _SlowBackend(httpcore.AsyncNetworkBackend):
            def __init__(self):
                self.timeouts: list[float | None] = []
                self.dial_targets: list[str] = []

            async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
                self.dial_targets.append(str(host))
                self.timeouts.append(timeout)
                await asyncio.sleep(0.3)
                raise OSError("refused")

        slow = _SlowBackend()
        backend = http_diag._PinnedIpNetworkBackend(slow, allow_private=False)

        start = time.monotonic()
        with pytest.raises(OSError):
            await backend.connect_tcp("example.com", 80, timeout=1.0)
        total = time.monotonic() - start

        assert slow.dial_targets == ips
        assert len(slow.timeouts) == 3
        assert slow.timeouts[0] == pytest.approx(1.0, abs=0.05)
        assert slow.timeouts[1] == pytest.approx(0.7, abs=0.05)
        assert slow.timeouts[2] == pytest.approx(0.4, abs=0.05)
        assert total < 1.6

    def test_pinned_transport_embeds_pinned_backend_and_is_fail_closed(self, monkeypatch):
        transport = http_diag._pinned_transport(allow_private=False)
        pool = transport._pool
        assert isinstance(pool._network_backend, _PinnedIpNetworkBackend)

        class _PoolWithoutBackend:
            _ssl_context = None
            _max_connections = 1
            _max_keepalive_connections = 1
            _keepalive_expiry = 5.0
            _http1 = True
            _http2 = False
            _uds = None
            _local_address = None
            _retries = 0
            _socket_options = None

        class _TransportWithoutBackend(httpx.AsyncHTTPTransport):
            def __init__(self, *args, **kwargs):
                self._pool = _PoolWithoutBackend()

        monkeypatch.setattr(httpx, "AsyncHTTPTransport", _TransportWithoutBackend)
        with pytest.raises(RuntimeError, match="fail-closed"):
            http_diag._pinned_transport(allow_private=False)


class TestMtuDiscovery:
    @pytest.mark.asyncio
    async def test_path_mtu_found_with_bounded_probes(self, monkeypatch):
        async def _probe(target, size, timeout_sec):
            return "success" if size <= 1400 else "error"

        monkeypatch.setattr(mtu_diag, "_ping_size_probe", _probe)
        result = await mtu_diag.mtu_discovery("example.com", min_size=1300, max_size=1500)
        assert result["status"] == "success"
        assert result["path_mtu"] == 1400
        assert len(result["probes"]) <= mtu_diag.MAX_PROBES

    @pytest.mark.asyncio
    async def test_probe_budget_capped_at_max_probes(self, monkeypatch):
        async def _probe(target, size, timeout_sec):
            return "error"

        monkeypatch.setattr(mtu_diag, "_ping_size_probe", _probe)
        result = await mtu_diag.mtu_discovery("example.com")
        assert result["path_mtu"] is None
        assert result["status"] == "error"
        assert len(result["probes"]) <= mtu_diag.MAX_PROBES


class TestValidateTimeoutMs:
    def test_over_cap_clamped(self):
        assert validate_timeout_ms(999_999, 10_000) == 10_000
        assert validate_timeout_ms(30_000, 30_000) == 30_000

    def test_within_cap_passthrough(self):
        assert validate_timeout_ms(1_500, 10_000) == 1_500

    def test_below_minimum_rejected(self):
        with pytest.raises(ValueError):
            validate_timeout_ms(50, 10_000)
