import json

import pytest
from fastapi.testclient import TestClient

import alerts
import config
import main


@pytest.fixture(autouse=True)
def _isolated_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "RULES_PATH", tmp_path / "alert_rules.json")
    monkeypatch.setattr(alerts, "_rules", None)
    alerts.reset_state()
    yield
    alerts.reset_state()


@pytest.fixture()
def client():
    return TestClient(main.app)


def _sample(cpu_temp=None, gpu_temp=None, ram_pct=30):
    return {"cpu_temp": cpu_temp, "gpu_temp": gpu_temp, "ram_pct": ram_pct}


# ---- default seed ---- #

def test_default_seed_when_file_missing():
    rules = alerts.get_rules()
    assert [r["id"] for r in rules["rules"]] == ["cpu_temp", "gpu_temp", "ram_pct", "disk_full"]
    by_id = {r["id"]: r for r in rules["rules"]}
    assert by_id["cpu_temp"]["threshold"] == config.ALERT_CPU_TEMP
    assert by_id["gpu_temp"]["threshold"] == config.ALERT_GPU_TEMP
    assert by_id["ram_pct"]["threshold"] == config.ALERT_RAM_PCT
    assert by_id["disk_full"]["threshold"] == config.ALERT_DISK_PCT
    assert all(r["op"] == ">=" and r["enabled"] is True for r in rules["rules"])
    assert rules["channels"] == {"toast": True, "sound": False}


def test_default_seed_tracks_config(monkeypatch):
    monkeypatch.setattr(config, "ALERT_RAM_PCT", 50.0)
    rules = alerts.get_rules()
    by_id = {r["id"]: r for r in rules["rules"]}
    assert by_id["ram_pct"]["threshold"] == 50.0


def test_invalid_file_falls_back_to_defaults(tmp_path):
    alerts.RULES_PATH.write_text("{not json", encoding="utf-8")
    assert alerts.load_rules() == alerts._default_rules()


def test_legacy_behavior_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 1)
    monkeypatch.setattr(config, "ALERT_RAM_PCT", 50.0)
    fired = alerts.evaluate(_sample(ram_pct=60))
    assert any(a["id"] == "ram_pct" and a["threshold"] == 50.0 for a in fired)


# ---- validation ---- #

def _valid_payload(threshold=80, op=">=", enabled=True, channels=None):
    return {
        "rules": [{"id": "cpu_temp", "metric": "cpu_temp", "op": op,
                   "threshold": threshold, "enabled": enabled}],
        "channels": channels if channels is not None else {"toast": True, "sound": False},
    }


@pytest.mark.parametrize("mutate", [
    lambda p: p["rules"][0].update(op="<"),
    lambda p: p["rules"][0].update(metric="bogus"),
    lambda p: p["rules"][0].update(threshold="80"),
    lambda p: p["rules"][0].update(threshold=None),
    lambda p: p["rules"][0].update(enabled="yes"),
    lambda p: p["rules"].append(p["rules"][0]),
    lambda p: p.update(rules="nope"),
    lambda p: p.update(channels={"toast": "yes"}),
])
def test_validate_rejects_bad_payloads(mutate):
    payload = _valid_payload()
    mutate(payload)
    with pytest.raises(ValueError):
        alerts._validate_rules_payload(payload)


def test_validate_accepts_strict_op():
    out = alerts._validate_rules_payload(_valid_payload())
    assert out["rules"][0]["op"] == ">="


# ---- hot reload + persistence ---- #

def test_set_rules_hot_reloads_evaluator(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 1)
    alerts.set_rules(_valid_payload(threshold=50))
    fired = alerts.evaluate(_sample(cpu_temp=60))
    assert len(fired) == 1
    assert fired[0]["id"] == "cpu_temp"
    assert fired[0]["threshold"] == 50
    assert "limit 50" in fired[0]["message"]


def test_disabled_rule_never_fires(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SUSTAINED_SAMPLES", 1)
    rule = {"id": "cpu_temp", "metric": "cpu_temp", "op": ">=",
            "threshold": 10, "enabled": False}
    alerts.set_rules({"rules": [rule], "channels": {"toast": True, "sound": False}})
    assert alerts.evaluate(_sample(cpu_temp=99)) == []


def test_set_rules_persists_and_loads_back():
    saved = alerts.set_rules(_valid_payload())
    on_disk = json.loads(alerts.RULES_PATH.read_text(encoding="utf-8"))
    assert on_disk == saved
    alerts._rules = None
    assert alerts.load_rules() == saved


def test_channels_hot_reload():
    assert alerts.get_channels() == {"toast": True, "sound": False}
    alerts.set_rules(_valid_payload(channels={"toast": False, "sound": True}))
    assert alerts.get_channels() == {"toast": False, "sound": True}


# ---- API ---- #

def test_api_get_rules_defaults(client):
    r = client.get("/api/alerts/rules")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rules"]) == 4
    assert body["channels"] == {"toast": True, "sound": False}


def test_api_put_rules_ok(client):
    r = client.put("/api/alerts/rules", json=_valid_payload(threshold=70))
    assert r.status_code == 200
    assert r.json()["rules"][0]["threshold"] == 70
    on_disk = json.loads(alerts.RULES_PATH.read_text(encoding="utf-8"))
    assert on_disk["rules"][0]["threshold"] == 70


def test_api_put_rules_invalid_op_400(client):
    payload = _valid_payload()
    payload["rules"][0]["op"] = "!="
    r = client.put("/api/alerts/rules", json=payload)
    assert r.status_code == 400


def test_api_put_rules_invalid_metric_400(client):
    payload = _valid_payload()
    payload["rules"][0]["metric"] = "wifi"
    r = client.put("/api/alerts/rules", json=payload)
    assert r.status_code == 400


def test_api_put_then_get_roundtrip(client):
    client.put("/api/alerts/rules", json=_valid_payload(channels={"toast": False, "sound": True}))
    r = client.get("/api/alerts/rules")
    assert r.json()["channels"] == {"toast": False, "sound": True}
