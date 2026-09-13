"""Sensor-matching regression tests (stubbed LHM sensor lists)."""
import metrics
import sensors_lhm


def _s(name, type_, value, parent, hwname=""):
    return {"name": name, "type": type_, "value": value,
            "parent": parent, "hwname": hwname}


def test_amd_cpu_temperature(monkeypatch):
    monkeypatch.setattr(metrics, "_get_hw_sensors", lambda ttl=5.0: [
        _s("CPU Package", "Temperature", 55.0, "/amdcpu/0", "amd ryzen 7 2700u"),
    ])
    t = metrics._get_cpu_temperature()
    assert t is not None and t["primary"] == 55.0


def test_intel_cpu_power(monkeypatch):
    monkeypatch.setattr(metrics, "_get_hw_sensors", lambda ttl=5.0: [
        _s("CPU Package", "Power", 65.5, "/intelcpu/0", "intel core i7"),
    ])
    assert metrics._get_cpu_power() == 65.5


def test_type_case_variants(monkeypatch):
    for variant in ("temperature", "TEMPERATURE", "SensorType.Temperature"):
        monkeypatch.setattr(metrics, "_get_hw_sensors", lambda ttl=5.0, v=variant: [
            _s("CPU Package", v, 60.0, "/amdcpu/0"),
        ])
        t = metrics._get_cpu_temperature()
        assert t is not None and t["primary"] == 60.0, variant


def test_empty_sensors_yield_none(monkeypatch):
    monkeypatch.setattr(metrics, "_get_hw_sensors", lambda ttl=5.0: [])
    assert metrics._get_cpu_temperature() is None
    assert metrics._get_cpu_power() is None


def test_cpu_temperature_excludes_gpu_core(monkeypatch):
    monkeypatch.setattr(metrics, "_get_hw_sensors", lambda ttl=5.0: [
        _s("CPU Package", "Temperature", 50.0, "/amdcpu/0"),
        _s("GPU Core", "Temperature", 0.0, "/gpu-amd/0"),
    ])
    t = metrics._get_cpu_temperature()
    assert t is not None
    assert t["primary"] == 50.0
    assert t["max"] == 50.0
    assert t["average"] == 50.0
    assert all(r["name"] != "GPU Core" for r in t["core_temps"])


def test_sensors_status_hides_paths(monkeypatch):
    monkeypatch.setattr(sensors_lhm, "_init_state",
                        "dll_not_found:C:\\secret\\path\\x.dll", raising=False)
    msg = metrics.sensors_status()["message"]
    assert "secret" not in msg and ".dll" not in msg
    assert metrics.sensors_status()["state"] == "dll_not_found"


def test_igpu_lhm_usage_100_filtered_but_temp_merged(monkeypatch):
    monkeypatch.setattr(metrics, "_get_nvidia_gpus", lambda: [])
    monkeypatch.setattr(metrics, "_get_wmi_gpus", lambda: [
        {"name": "AMD Radeon Vega 8 Graphics", "vram_total_mb": 512},
    ])
    monkeypatch.setattr(metrics, "_get_gpu_sensors_lhm", lambda: {
        "amd radeon vega 8 graphics": {
            "gpu_usage_percent": 100, "temperature_celsius": 55.0},
    })
    monkeypatch.setattr(metrics, "_sensor_value", lambda *a, **k: None)
    snap = metrics.gpu_snapshot()
    assert len(snap["gpus"]) == 1
    g = snap["gpus"][0]
    assert g.get("gpu_usage_percent") is None
    assert g.get("temperature_celsius") == 55.0


def test_igpu_lhm_usage_35_kept(monkeypatch):
    monkeypatch.setattr(metrics, "_get_nvidia_gpus", lambda: [])
    monkeypatch.setattr(metrics, "_get_wmi_gpus", lambda: [
        {"name": "AMD Radeon Vega 8 Graphics", "vram_total_mb": 512},
    ])
    monkeypatch.setattr(metrics, "_get_gpu_sensors_lhm", lambda: {
        "amd radeon vega 8 graphics": {
            "gpu_usage_percent": 35, "temperature_celsius": 50.0},
    })
    monkeypatch.setattr(metrics, "_sensor_value", lambda *a, **k: None)
    snap = metrics.gpu_snapshot()
    g = snap["gpus"][0]
    assert g.get("gpu_usage_percent") == 35
    assert g.get("temperature_celsius") == 50.0


def test_dgpu_lhm_usage_100_kept(monkeypatch):
    monkeypatch.setattr(metrics, "_get_nvidia_gpus", lambda: [])
    monkeypatch.setattr(metrics, "_get_wmi_gpus", lambda: [
        {"name": "NVIDIA GeForce RTX 4060", "vram_total_mb": 8192},
    ])
    monkeypatch.setattr(metrics, "_get_gpu_sensors_lhm", lambda: {
        "nvidia geforce rtx 4060": {
            "gpu_usage_percent": 100, "temperature_celsius": 65.0},
    })
    monkeypatch.setattr(metrics, "_sensor_value", lambda *a, **k: None)
    snap = metrics.gpu_snapshot()
    g = snap["gpus"][0]
    assert g.get("gpu_usage_percent") == 100
    assert g.get("temperature_celsius") == 65.0
