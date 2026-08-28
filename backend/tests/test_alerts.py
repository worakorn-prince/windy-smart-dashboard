import pytest

import alerts
import config


@pytest.fixture(autouse=True)
def _reset_state():
    alerts.reset_state()
    yield
    alerts.reset_state()


@pytest.fixture(autouse=True)
def _safe_disk(monkeypatch):
    # Isolate tests from this machine's real disk usage.
    monkeypatch.setattr(alerts, "_max_disk_used_pct", lambda: 50.0)


def _sample(cpu_temp=None, gpu_temp=None, ram_pct=30):
    return {"cpu_temp": cpu_temp, "gpu_temp": gpu_temp, "ram_pct": ram_pct}


def test_no_fire_below_threshold():
    assert alerts.evaluate(_sample(cpu_temp=50)) == []


def test_none_value_never_fires():
    assert alerts.evaluate(_sample(cpu_temp=None)) == []


def test_transient_spike_does_not_fire(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 3)
    fired = []
    for _ in range(2):
        fired = alerts.evaluate(_sample(cpu_temp=90))
    assert fired == []


def test_sustained_breach_fires_once(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 3)
    fired = []
    for _ in range(3):
        fired = alerts.evaluate(_sample(cpu_temp=90))
    assert len(fired) == 1
    assert fired[0]["id"] == "cpu_temp"
    assert fired[0]["value"] == 90
    assert "limit" in fired[0]["message"]


def test_cooldown_blocks_immediate_refire(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 1)
    monkeypatch.setattr(config, "ALERT_COOLDOWN_SEC", 300)
    assert len(alerts.evaluate(_sample(cpu_temp=90))) == 1
    assert alerts.evaluate(_sample(cpu_temp=90)) == []


def test_recovery_resets_breach_counter(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 2)
    alerts.evaluate(_sample(cpu_temp=90))
    alerts.evaluate(_sample(cpu_temp=50))
    assert alerts.evaluate(_sample(cpu_temp=90)) == []


def test_disk_full_rule(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 1)
    monkeypatch.setattr(alerts, "_max_disk_used_pct", lambda: 96.0)

    fired = alerts.evaluate(_sample())
    assert any(a["id"] == "disk_full" for a in fired)


def test_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "ALERTS_ENABLED", False)
    assert alerts.evaluate(_sample(cpu_temp=99, gpu_temp=99, ram_pct=99)) == []
