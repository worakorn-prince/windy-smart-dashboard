"""Tests for on-demand diagnostics: validate_target, tcp, tls, http, mtu."""

from __future__ import annotations

import socket
import time
from datetime import UTC, datetime

import httpx
import pytest

from internet_insights.diagnostics import validate_target, validate_timeout_ms
from internet_insights.diagnostics import http as http_diag
from internet_insights.diagnostics import mtu as mtu_diag
from internet_insights.diagnostics import tcp as tcp_diag
from internet_insights.diagnostics import tls as tls_diag
from internet_insights.diagnostics.http import SsrfBlockedError, redact_url


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
        async def _body():
            yield b""

        return httpx.Response(status_code, headers=headers, content=_body())

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
