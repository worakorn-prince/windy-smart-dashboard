"""System metrics collection via psutil and WMI."""
from __future__ import annotations

import asyncio
import json
import platform
import socket
import subprocess
import threading
import time
from datetime import datetime
from typing import Any

import psutil

# Module-level state for delta calculations.
_last_net_io = psutil.net_io_counters()
_last_disk_io = psutil.disk_io_counters()
_last_ts = time.monotonic()
_last_boot = None
_hostname = socket.gethostname()

# WMI query cache
_wmi_cache: dict[str, Any] = {}
_wmi_cache_ts: dict[str, float] = {}
_wmi_cache_ttl = 30.0  # seconds
_wmi_lock = threading.Lock()


def _delta_per_sec(cur: int, prev: int, dt: float) -> float:
    if dt <= 0:
        return 0.0
    diff = cur - prev
    if diff < 0:
        return 0.0
    return diff / dt


async def _run_powershell(script: str, timeout: float = 10.0) -> str:
    """Run a PowerShell script and return stdout."""
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
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return stdout.decode("utf-8", errors="replace")


def _run_powershell_sync(script: str, timeout: float = 10.0) -> str:
    """Run a PowerShell script synchronously and return stdout."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""


def _get_wmi_cached(key: str, script: str | None, ttl: float = 30.0) -> Any:
    """Get WMI data with caching. Failures are NOT cached (retry next call)."""
    import json
    now = time.time()
    cached = _wmi_cache.get(key)
    if cached is not None and (now - _wmi_cache_ts.get(key, 0)) < ttl:
        return cached
    if script is None:
        return None
    with _wmi_lock:
        # Double-check inside the lock (another thread may have filled it).
        cached = _wmi_cache.get(key)
        if cached is not None and (now - _wmi_cache_ts.get(key, 0)) < ttl:
            return cached
        try:
            output = _run_powershell_sync(script, timeout=15.0)
            data = json.loads(output) if output.strip() else None
            if data is not None:
                _wmi_cache[key] = data
                _wmi_cache_ts[key] = now
            return data
        except (json.JSONDecodeError, Exception):
            return None


def cpu_snapshot() -> dict[str, Any]:
    overall = psutil.cpu_percent(interval=None, percpu=False)
    cores = psutil.cpu_percent(interval=None, percpu=True)
    freq = psutil.cpu_freq()

    # Get detailed CPU info from WMI
    cpu_info = _get_wmi_cached("cpu_info", r"""
        Get-CimInstance Win32_Processor | ForEach-Object {
            @{
                Name = $_.Name
                Manufacturer = $_.Manufacturer
                NumberOfCores = $_.NumberOfCores
                NumberOfLogicalProcessors = $_.NumberOfLogicalProcessors
                MaxClockSpeed = $_.MaxClockSpeed
                L2CacheSize = $_.L2CacheSize
                L3CacheSize = $_.L3CacheSize
                SocketDesignation = $_.SocketDesignation
            }
        } | ConvertTo-Json -Compress
    """, ttl=3600)

    cpu_temp = _get_cpu_temperature()
    if cpu_temp is None:
        # Fallback that does not require Administrator.
        cpu_temp = _get_cpu_temperature_wmi()
    cpu_power = _get_cpu_power()
    cpu_fan = _get_cpu_fan_speed()

    return {
        "overall": round(overall, 1),
        "cores": [round(c, 1) for c in cores],
        "core_count": len(cores),
        "freq_mhz": {
            "current": round(freq.current, 0) if freq else None,
            "min": round(freq.min, 0) if freq and freq.min else None,
            "max": round(freq.max, 0) if freq and freq.max else None,
        },
        "info": cpu_info,
        "temperature_celsius": cpu_temp,
        "power_watts": cpu_power,
        "fan_rpm": cpu_fan,
    }


# =============================================================================
# Hardware sensors (LibreHardwareMonitor / OpenHardwareMonitor via WMI)
#
# Modern LibreHardwareMonitor publishes to root\LibreHardwareMonitor;
# legacy OpenHardwareMonitor used root\OpenHardwareMonitor. We try both
# in a single cached query, then filter in Python.
# =============================================================================

_hw_sensors_cache: list[dict[str, Any]] | None = None
_hw_sensors_ts: float = 0.0
HW_SENSORS_TTL = 5.0  # seconds


def _get_hw_sensors(ttl: float = HW_SENSORS_TTL) -> list[dict[str, Any]]:
    """Fetch all hardware sensors.

    Priority:
      1. In-process LibreHardwareMonitorLib via pythonnet (reliable,
         no GUI/WMI needed; requires elevated backend).
      2. WMI root\\LibreHardwareMonitor / root\\OpenHardwareMonitor
         (only works when the LHM GUI publishes them).
    """
    global _hw_sensors_cache, _hw_sensors_ts
    now = time.time()
    if _hw_sensors_cache is not None and (now - _hw_sensors_ts) < ttl:
        return _hw_sensors_cache

    sensors = _read_sensors_lhm_direct()

    if not sensors:
        sensors = _read_sensors_wmi()

    _hw_sensors_cache = sensors
    _hw_sensors_ts = now
    return sensors


def _read_sensors_lhm_direct() -> list[dict[str, Any]]:
    """Sensor read via in-process LibreHardwareMonitorLib."""
    try:
        import sensors_lhm
    except ImportError:
        return []
    raw = sensors_lhm.read_all_sensors()
    return [
        {
            "name": s["name"],
            "type": s["type"],
            "value": s["value"],
            "parent": s["parent"].lower(),
            "hwname": s.get("hwname", "").lower(),
        }
        for s in raw
    ]


def _read_sensors_wmi() -> list[dict[str, Any]]:
    """Legacy path — query LHM/OHM GUI-published WMI namespaces."""
    script = r"""
        $out = @()
        foreach ($ns in @('root\LibreHardwareMonitor', 'root\OpenHardwareMonitor')) {
            try {
                $sensors = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction Stop |
                           Select-Object Name, SensorType, Value, Parent
                if ($sensors) { $out += $sensors; break }
            } catch { }
        }
        $out | ConvertTo-Json -Compress -Depth 3
    """
    out = _run_powershell_sync(script, timeout=12)
    data: Any = []
    if out.strip():
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            data = []
    if isinstance(data, dict):
        data = [data]

    sensors: list[dict[str, Any]] = []
    for s in data or []:
        try:
            val = s.get("Value")
            sensors.append({
                "name": str(s.get("Name", "") or ""),
                "type": str(s.get("SensorType", "") or ""),
                "value": float(val) if val is not None else None,
                "parent": str(s.get("Parent", "") or "").lower(),
            })
        except Exception:
            continue
    return [s for s in sensors if s["value"] is not None]


def _filter_sensors(sensor_type: str, *keywords: str,
                    exclude: tuple = ()) -> list[dict[str, Any]]:
    """Filter cached sensors by type + keyword match on name/parent."""
    hits = []
    for s in _get_hw_sensors():
        if s["type"].lower() != sensor_type.lower():
            continue
        blob = (s["name"] + " " + s["parent"]).lower()
        if any(x.lower() in blob for x in exclude):
            continue
        if any(k.lower() in blob for k in keywords):
            hits.append(s)
    return hits


def _sensor_value(sensor_type: str, *keywords: str,
                  exclude: tuple = ()) -> float | None:
    """Return first matching sensor's numeric value."""
    hits = _filter_sensors(sensor_type, *keywords, exclude=exclude)
    for s in hits:
        if s["value"] is not None:
            return s["value"]
    return None


def _get_cpu_temperature() -> dict[str, Any] | None:
    """CPU temperature from LibreHardwareMonitor/OHM.

    Prefers package-level readings (Package / Tctl/Tdie), falls back to
    per-core temps.
    """
    temps = _filter_sensors(
        "Temperature",
        "cpu", "package", "tctl", "tdie", "core", "ccd", "socket", "proc ",
    )
    if not temps:
        return None

    readings = [{"name": t["name"], "value": t["value"]}
                for t in temps if t["value"] is not None]
    if not readings:
        return None

    # Prefer a single package/Tdie reading as "the" temperature.
    preferred = [
        r for r in readings
        if any(k in r["name"].lower() for k in ("package", "tdie", "tctl"))
    ]
    primary = preferred[0]["value"] if preferred else max(
        r["value"] for r in readings
    )
    return {
        "primary": round(primary, 1),
        "core_temps": readings[:16],
        "max": round(max(r["value"] for r in readings), 1),
        "average": round(sum(r["value"] for r in readings) / len(readings), 1),
    }


def _get_cpu_temperature_wmi() -> dict[str, Any] | None:
    """Best-effort CPU temperature via WMI MSAcpi_ThermalZoneTemperature.

    This works WITHOUT Administrator on many machines, so the CPU
    temperature can still appear even if LibreHardwareMonitor is unavailable
    (e.g. the user declined the UAC prompt). Values are deci-Kelvin.
    """
    script = r'''
        $out = @()
        try {
            Get-CimInstance -Namespace root\WMI -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop | ForEach-Object {
                $out += [math]::Round(($_.CurrentTemperature - 2732) / 10, 1)
            }
        } catch { }
        ConvertTo-Json -Compress -InputObject $out
    '''
    data = _get_wmi_cached("cpu_temp_wmi", script, ttl=10.0)
    if not data:
        return None
    if isinstance(data, (int, float)):
        data = [data]
    if not isinstance(data, list):
        return None
    vals = [float(v) for v in data if isinstance(v, (int, float))]
    if not vals:
        return None
    return {
        "primary": round(max(vals), 1),
        "core_temps": [{"name": "ThermalZone", "value": round(v, 1)} for v in vals],
        "max": round(max(vals), 1),
        "average": round(sum(vals) / len(vals), 1),
    }


def _get_cpu_power() -> float | None:
    """CPU package power draw in watts."""
    return _sensor_value("Power", "cpu", "package", "tdie", exclude=("gpu",))


def _get_cpu_fan_speed() -> int | None:
    """Chassis/CPU fan RPM (first non-GPU fan)."""
    v = _sensor_value("Fan", "fan", exclude=("gpu",))
    return int(v) if v is not None else None


# =============================================================================
# RAM
# =============================================================================

def ram_snapshot() -> dict[str, Any]:
    v = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Get detailed RAM info using wmic (more reliable than PowerShell on Windows)
    ram_info = _get_ram_info_wmic()

    # Calculate channels and DDR type
    ram_details = _analyze_ram_details(ram_info)

    # Try to get RAM temperature
    ram_temp = _get_ram_temperature()
    ram_voltage = _get_ram_voltage()

    return {
        "total": v.total,
        "used": v.used,
        "available": v.available,
        "percent": round(v.percent, 1),
        "cached": getattr(v, "cached", 0),
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": round(swap.percent, 1),
        "details": ram_details,
        "temperature_celsius": ram_temp,
        "voltage": ram_voltage,
    }


def _get_ram_info_wmic() -> list[dict[str, Any]]:
    """Get RAM info using wmic command."""
    cache_key = "ram_info_wmic"
    cached = _get_wmi_cached(cache_key, None, ttl=3600)
    if cached is not None:
        return cached

    try:
        result = subprocess.run(
            ["wmic", "memorychip", "get", "Capacity,Speed,ConfiguredClockSpeed,Manufacturer,PartNumber,MemoryType,FormFactor,DeviceLocator,BankLabel", "/format:csv"],
            capture_output=True,
            timeout=15,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            return []

        header = lines[0].strip().split(',')
        results = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.strip().split(',')
            if len(parts) < len(header):
                continue
            row = dict(zip(header, parts, strict=False))
            for key in ["Capacity", "Speed", "ConfiguredClockSpeed", "MemoryType", "FormFactor"]:
                if key in row and row[key].isdigit():
                    row[key] = int(row[key])
            results.append(row)

        _wmi_cache["ram_info_wmic"] = results
        _wmi_cache_ts["ram_info_wmic"] = time.time()
        return results
    except Exception:
        return []


def _infer_ddr_type_from_speed(speed_mhz: int) -> str:
    """Infer DDR type from memory speed when MemoryType is unknown."""
    if speed_mhz >= 4800:
        return "DDR5"
    elif speed_mhz >= 2133:
        return "DDR4"
    elif speed_mhz >= 1600:
        return "DDR3"
    elif speed_mhz >= 800:
        return "DDR2"
    elif speed_mhz >= 400:
        return "DDR"
    else:
        return "Unknown"


def _analyze_ram_details(ram_info: Any) -> dict[str, Any]:
    """Analyze RAM details from wmic output."""
    if not ram_info or not isinstance(ram_info, list):
        return {"type": "Unknown", "channels": 0, "modules": []}

    modules = []
    total_capacity = 0
    speeds = []
    types = set()

    type_map = {
        0: "Unknown",
        20: "DDR",
        21: "DDR2",
        22: "DDR2 FB-DIMM",
        24: "DDR3",
        26: "DDR4",
        27: "DDR5",
    }

    for mem in ram_info:
        capacity = mem.get("Capacity", 0)
        speed = mem.get("Speed", 0) or mem.get("ConfiguredClockSpeed", 0)
        mem_type = mem.get("MemoryType", 0)

        type_str = type_map.get(mem_type)
        if not type_str or type_str == "Unknown":
            # Fallback: infer from speed
            type_str = _infer_ddr_type_from_speed(speed)
        types.add(type_str)

        modules.append({
            "capacity_gb": round(capacity / (1024**3), 1),
            "speed_mhz": speed,
            "type": type_str,
            "manufacturer": mem.get("Manufacturer", "Unknown"),
            "part_number": mem.get("PartNumber", "").strip(),
            "location": mem.get("DeviceLocator", ""),
            "bank": mem.get("BankLabel", ""),
        })
        total_capacity += capacity
        if speed:
            speeds.append(speed)

    banks = set()
    for mem in ram_info:
        bank = mem.get("BankLabel", "").strip()
        if bank:
            banks.add(bank)
    channels = len(banks) if banks else (1 if len(modules) == 1 else 2)

    return {
        "type": ", ".join(sorted(types)) if types else "Unknown",
        "channels": channels,
        "max_speed_mhz": max(speeds) if speeds else 0,
        "modules": modules,
        "total_capacity_gb": round(total_capacity / (1024**3), 1),
    }


def _get_ram_temperature() -> dict[str, Any] | None:
    """RAM/DIMM temperature from LHM (parent /ram or names with DIMM/Memory)."""
    temps = _filter_sensors(
        "Temperature",
        "ram", "memory", "dimm", "/ram",
        exclude=("gpu",),
    )
    readings = [{"name": t["name"], "value": t["value"]}
                for t in temps if t["value"] is not None]
    if not readings:
        return None
    return {
        "temps": readings[:8],
        "max": round(max(r["value"] for r in readings), 1),
    }


def _get_ram_voltage() -> float | None:
    """DRAM voltage (VDD / VDDR / Memory Voltage)."""
    return _sensor_value("Voltage", "vdd", "dimm", "memory", "/ram")


# =============================================================================
# Disk
# =============================================================================

_last_disk_io = psutil.disk_io_counters()
_last_disk_ts = time.monotonic()


def disk_snapshot() -> dict[str, Any]:
    global _last_disk_io, _last_disk_ts
    now = time.monotonic()
    dt = now - _last_disk_ts
    _last_disk_ts = now
    partitions: list[dict[str, Any]] = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
            partitions.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": round(usage.percent, 1),
            })
        except (PermissionError, OSError):
            continue

    cur = psutil.disk_io_counters()
    read_rate = _delta_per_sec(cur.read_bytes, _last_disk_io.read_bytes, dt) if cur and _last_disk_io else 0
    write_rate = _delta_per_sec(cur.write_bytes, _last_disk_io.write_bytes, dt) if cur and _last_disk_io else 0
    _last_disk_io = cur or _last_disk_io

    disk_details = _get_disk_details()
    disk_temps = _get_disk_temperatures()

    return {
        "partitions": partitions,
        "io": {
            "read_bytes_per_sec": round(read_rate, 0),
            "write_bytes_per_sec": round(write_rate, 0),
        },
        "details": disk_details,
        "temperatures": disk_temps,
    }


def _get_disk_details() -> list[dict[str, Any]]:
    """Get detailed disk info including SMART health."""
    disk_data = _get_wmi_cached("disk_details", r"""
        Get-CimInstance Win32_DiskDrive | ForEach-Object {
            @{
                Model = $_.Model
                InterfaceType = $_.InterfaceType
                MediaType = $_.MediaType
                Size = $_.Size
                Partitions = $_.Partitions
                SerialNumber = $_.SerialNumber
                FirmwareRevision = $_.FirmwareRevision
                Status = $_.Status
            }
        } | ConvertTo-Json -Compress
    """, ttl=3600)

    if not disk_data or not isinstance(disk_data, list):
        return []

    smart_data = _get_smart_data()

    results = []
    for disk in disk_data:
        model = disk.get("Model", "").strip()
        smart = smart_data.get(model, {}) if smart_data else {}

        interface = disk.get("InterfaceType", "").upper()
        media = disk.get("MediaType", "").upper()
        if "NVME" in interface or "NVME" in media:
            drive_type = "NVMe SSD"
        elif "SSD" in media or "SOLID STATE" in media:
            drive_type = "SATA SSD"
        elif "HDD" in media or "HARD DISK" in media:
            drive_type = "HDD"
        else:
            drive_type = "Unknown"

        results.append({
            "model": model,
            "type": drive_type,
            "interface": interface,
            "capacity_gb": round(disk.get("Size", 0) / (1024**3), 1) if disk.get("Size") else 0,
            "serial": disk.get("SerialNumber", "").strip(),
            "firmware": disk.get("FirmwareRevision", "").strip(),
            "status": disk.get("Status", "Unknown"),
            "smart_health": smart.get("health", "Unknown"),
            "smart_raw": smart.get("raw", {}),
        })
    return results


def _get_smart_data() -> dict[str, Any]:
    """Get SMART health/status via WMI (cached 5 min)."""
    smart_data = _get_wmi_cached("smart_data", r"""
        Get-CimInstance Win32_DiskDrive | ForEach-Object {
            $model = $_.Model.Trim()
            @{
                Model = $model
                Status = $_.Status
                Size = $_.Size
            }
        } | ConvertTo-Json -Compress
    """, ttl=300)

    if not smart_data or not isinstance(smart_data, list):
        return {}

    result = {}
    for disk in smart_data:
        model = disk.get("Model", "").strip()
        status = disk.get("Status", "Unknown")
        health = "Good" if status == "OK" else "Warning" if status in ["Degraded", "Pred Fail"] else "Critical"
        result[model] = {"health": health, "status": status, "raw": disk}
    return result


def _get_disk_temperatures() -> dict[str, Any]:
    """Drive temperatures from LHM (parents /hdd/*, /nvme/* or drive-like names)."""
    temps = _filter_sensors(
        "Temperature",
        "hdd", "nvme", "ssd", "drive", "disk",
    )
    return {t["name"]: round(t["value"], 1)
            for t in temps if t["value"] is not None}


def _get_gpu_sensors_lhm() -> dict[str, dict[str, Any]]:
    """GPU live metrics from LHM keyed by lowercase GPU hardware name.

    Handles identifier variants: /gpu/0 (NVIDIA), /gpu-amd/N, /gpu-intel/0.
    Gives temperature/power/fan/clock/utilization for AMD & Intel GPUs that
    nvidia-smi cannot see.
    """
    groups: dict[str, dict[str, Any]] = {}
    for s in _get_hw_sensors():
        parent = s.get("parent", "")
        if "/gpu" not in parent:
            continue
        hwname = s.get("hwname", "")
        if not hwname:
            continue
        g = groups.setdefault(hwname, {})

        name_l = s["name"].lower()
        v = s["value"]
        if v is None:
            continue
        if s["type"] == "Temperature":
            if "hot spot" in name_l or "hotspot" in name_l:
                g["hotspot_temp"] = round(v, 1)
            else:
                g["temperature_celsius"] = round(v, 1)
        elif s["type"] == "Power":
            g["power_draw_watts"] = round(v, 1)
        elif s["type"] == "Fan":
            g["fan_speed_percent"] = round(v, 0)
        elif s["type"] == "Control":
            # AMD often reports fan speed as a "Control" sensor (0-100%).
            if "fan" in name_l:
                g["fan_speed_percent"] = round(v, 0)
        elif s["type"] == "Clock":
            if "memory" in name_l:
                g["memory_clock_mhz"] = round(v)
            elif "core" in name_l:
                g["graphics_clock_mhz"] = round(v)
        elif s["type"] == "Voltage":
            g.setdefault("voltage", round(v, 2))
        elif s["type"] == "Load":
            # Canonical core-load sensor on AMD; NVIDIA exposes similar.
            if name_l.startswith("gpu core"):
                g["gpu_usage_percent"] = round(
                    max(g.get("gpu_usage_percent") or 0, v), 1)
        elif s["type"] == "SmallData":
            # VRAM sizes (MB). Ignore D3D shared-memory noise.
            if name_l == "gpu memory total":
                g.setdefault("vram_total_mb", round(v))
            elif name_l == "gpu memory used":
                g["vram_used_mb"] = round(v)
            elif name_l == "gpu memory free":
                g["vram_free_mb"] = round(v)
    return groups


# =============================================================================
# Network
# =============================================================================

_last_net_io = psutil.net_io_counters()
_last_net_ts = time.monotonic()


def network_snapshot() -> dict[str, Any]:
    global _last_net_io, _last_net_ts
    now = time.monotonic()
    dt = now - _last_net_ts
    _last_net_ts = now
    cur = psutil.net_io_counters()
    send_rate = _delta_per_sec(cur.bytes_sent, _last_net_io.bytes_sent, dt)
    recv_rate = _delta_per_sec(cur.bytes_recv, _last_net_io.bytes_recv, dt)
    _last_net_io = cur

    addrs: dict[str, list[str]] = {}
    for name, snics in psutil.net_if_addrs().items():
        ips = []
        for sn in snics:
            fam = sn.family
            if (fam == socket.AF_INET and sn.address != "127.0.0.1") or (fam == socket.AF_INET6 and "%" not in sn.address and not sn.address.startswith("fe80")):
                ips.append(sn.address)
        if ips:
            addrs[name] = ips

    adapter_details = _get_adapter_details()
    wifi_info = _get_wifi_info()
    public_ip = _get_public_ip()

    return {
        "interfaces": addrs,
        "bytes_sent": cur.bytes_sent,
        "bytes_recv": cur.bytes_recv,
        "packets_sent": cur.packets_sent,
        "packets_recv": cur.packets_recv,
        "send_bytes_per_sec": round(send_rate, 0),
        "recv_bytes_per_sec": round(recv_rate, 0),
        "adapters": adapter_details,
        "wifi": wifi_info,
        "public_ip": public_ip,
    }


def _get_adapter_details() -> list[dict[str, Any]]:
    """Get detailed network adapter info from WMI."""
    adapter_data = _get_wmi_cached("adapter_details", r"""
        Get-CimInstance Win32_NetworkAdapter | Where-Object {$_.PhysicalAdapter -eq $true} | ForEach-Object {
            @{
                Name = $_.Name
                Description = $_.Description
                MACAddress = $_.MACAddress
                AdapterType = $_.AdapterType
                Speed = $_.Speed
                NetConnectionStatus = $_.NetConnectionStatus
                NetConnectionID = $_.NetConnectionID
                Manufacturer = $_.Manufacturer
                PNPDeviceID = $_.PNPDeviceID
            }
        } | ConvertTo-Json -Compress
    """, ttl=300)

    if not adapter_data or not isinstance(adapter_data, list):
        return []

    results = []
    for adapter in adapter_data:
        ip_config = _get_adapter_ip_config(adapter.get("Description", ""))

        status_map = {
            0: "Disconnected",
            1: "Connecting",
            2: "Connected",
            3: "Disconnecting",
            4: "Hardware Not Present",
            5: "Hardware Disabled",
            6: "Hardware Malfunction",
            7: "Media Disconnected",
            8: "Authenticating",
            9: "Authentication Succeeded",
            10: "Authentication Failed",
            11: "Invalid Address",
            12: "Credentials Required",
        }

        results.append({
            "name": adapter.get("Name", ""),
            "description": adapter.get("Description", ""),
            "mac": adapter.get("MACAddress", ""),
            "type": adapter.get("AdapterType", ""),
            "speed_mbps": adapter.get("Speed", 0) // 1000000 if adapter.get("Speed") else 0,
            "status": status_map.get(adapter.get("NetConnectionStatus", 0), "Unknown"),
            "connection_name": adapter.get("NetConnectionID", ""),
            "manufacturer": adapter.get("Manufacturer", ""),
            "ipv4": ip_config.get("ipv4", []),
            "ipv6": ip_config.get("ipv6", []),
            "gateway": ip_config.get("gateway", []),
            "dns": ip_config.get("dns", []),
        })
    return results


def _get_adapter_ip_config(adapter_desc: str) -> dict[str, list[str]]:
    """Get IP configuration for a specific adapter."""
    try:
        script = rf"""
            $adapter = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "Description = '{adapter_desc.replace("'", "''")}'"
            if ($adapter) {{
                @{{
                    IPv4 = $adapter.IPAddress -like '*.*.*.*'
                    IPv6 = $adapter.IPAddress -notlike '*.*.*.*'
                    Gateway = $adapter.DefaultIPGateway
                    DNSServer = $adapter.DNSServerSearchOrder
                }} | ConvertTo-Json -Compress
            }}
        """
        out = _run_powershell_sync(script, timeout=5)
        if out.strip():
            import json
            return json.loads(out)
    except Exception:
        pass
    return {"ipv4": [], "ipv6": [], "gateway": [], "dns": []}


def _get_wifi_info() -> dict[str, Any] | None:
    """Get WiFi connection info."""
    wifi_data = _get_wmi_cached("wifi_info", r"""
        try {
            $wifi = netsh wlan show interfaces
            $ssid = ($wifi -match 'SSID\s+:\\s+(.+)' | ForEach-Object { $_ -replace '.*:\\s+','' })[0]
            $signal = ($wifi -match 'Signal\s+:\\s+(\d+)%' | ForEach-Object { $_ -replace '.*:\\s+','' -replace '%','' })[0]
            $bssid = ($wifi -match 'BSSID\s+:\\s+(.+)' | ForEach-Object { $_ -replace '.*:\\s+','' })[0]
            $channel = ($wifi -match 'Channel\s+:\\s+(\d+)' | ForEach-Object { $_ -replace '.*:\\s+','' })[0]
            $radio = ($wifi -match 'Radio type\s+:\\s+(.+)' | ForEach-Object { $_ -replace '.*:\\s+','' })[0]
            @{ SSID = $ssid; Signal = [int]$signal; BSSID = $bssid; Channel = [int]$channel; RadioType = $radio } | ConvertTo-Json -Compress
        } catch { $null }
    """, ttl=10)

    if wifi_data and isinstance(wifi_data, dict) and wifi_data.get("SSID"):
        return wifi_data
    return None


_public_ip_cache: str | None = None
_public_ip_ts: float = 0.0
PUBLIC_IP_TTL = 300.0  # refresh every 5 minutes


def _get_public_ip() -> str | None:
    """Get public IP address (cached for 5 minutes to avoid hammering the API)."""
    global _public_ip_cache, _public_ip_ts
    now = time.time()
    if _public_ip_cache is not None and (now - _public_ip_ts) < PUBLIC_IP_TTL:
        return _public_ip_cache
    try:
        import urllib.request
        req = urllib.request.Request('https://api.ipify.org', headers={'User-Agent': 'WindySmartDashboard/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            _public_ip_cache = response.read().decode().strip()
            _public_ip_ts = now
            return _public_ip_cache
    except Exception:
        # Keep serving the last known value; mark ts so we retry later.
        _public_ip_ts = now
        return _public_ip_cache


# =============================================================================
# GPU
# =============================================================================

def gpu_snapshot() -> dict[str, Any]:
    """Get GPU information — static info from WMI, live metrics from
    nvidia-smi (NVIDIA) and LibreHardwareMonitor (AMD/Intel/NVIDIA)."""
    gpus: list[dict[str, Any]] = []
    gpus.extend(_get_nvidia_gpus())
    wmi_gpus = _get_wmi_gpus()
    gpus.extend(wmi_gpus)

    # Merge LibreHardwareMonitor live sensors by GPU name.
    lhm = _get_gpu_sensors_lhm()
    if lhm:
        for g in gpus:
            live = lhm.get(g.get("name", "").lower())
            if not live:
                continue
            for key in ("temperature_celsius", "hotspot_temp", "power_draw_watts",
                        "fan_speed_percent", "graphics_clock_mhz",
                        "memory_clock_mhz", "gpu_usage_percent"):
                val = live.get(key)
                if val is not None and not g.get(key):
                    g[key] = val

    # iGPUs (e.g. Vega) often expose no temperature of their own — fall back
    # to the CPU's GFX temperature sensor.
    gfx = _sensor_value("Temperature", "gfx")
    if gfx is not None:
        for g in gpus:
            n = g.get("name", "").lower()
            is_igpu = ("vega" in n or "radeon(tm)" in n or
                       g.get("vram_total_mb") in (512, 1024, 2048))
            if is_igpu and not g.get("temperature_celsius"):
                g["temperature_celsius"] = round(gfx, 1)

    return {"gpus": gpus, "count": len(gpus)}


def _get_nvidia_gpus() -> list[dict[str, Any]]:
    """Get NVIDIA GPU info via nvidia-smi."""
    try:
        result = subprocess.run([
            "nvidia-smi",
            "--query-gpu=index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,clocks.gr,clocks.mem,fan.speed",
            "--format=csv,noheader,nounits"
        ], capture_output=True, timeout=10, text=True, check=False)

        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 12:
                gpus.append({
                    "vendor": "NVIDIA",
                    "index": int(parts[0]),
                    "name": parts[1],
                    "driver_version": parts[2],
                    "vram_total_mb": int(parts[3]),
                    "vram_used_mb": int(parts[4]),
                    "vram_free_mb": int(parts[5]),
                    "gpu_usage_percent": float(parts[6]),
                    "vram_usage_percent": float(parts[7]),
                    "temperature_celsius": float(parts[8]),
                    "power_draw_watts": float(parts[9]) if parts[9] != '[Not Supported]' else None,
                    "graphics_clock_mhz": int(parts[10]) if parts[10] != '[Not Supported]' else None,
                    "memory_clock_mhz": int(parts[11]) if parts[11] != '[Not Supported]' else None,
                    "fan_speed_percent": float(parts[12]) if len(parts) > 12 and parts[12] != '[Not Supported]' else None,
                })
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []


def _get_wmi_gpus() -> list[dict[str, Any]]:
    """Get AMD/Intel GPU info via WMI."""
    gpu_data = _get_wmi_cached("gpu_wmi", r"""
        Get-CimInstance Win32_VideoController | ForEach-Object {
            @{
                Name = $_.Name
                AdapterRAM = $_.AdapterRAM
                DriverVersion = $_.DriverVersion
                VideoProcessor = $_.VideoProcessor
                VideoModeDescription = $_.VideoModeDescription
                CurrentHorizontalResolution = $_.CurrentHorizontalResolution
                CurrentVerticalResolution = $_.CurrentVerticalResolution
                CurrentRefreshRate = $_.CurrentRefreshRate
                Status = $_.Status
                AdapterDACType = $_.AdapterDACType
                Monochrome = $_.Monochrome
                InstalledDisplayDrivers = $_.InstalledDisplayDrivers
                DriverDate = $_.DriverDate
            }
        } | ConvertTo-Json -Compress
    """, ttl=3600)

    if not gpu_data or not isinstance(gpu_data, list):
        return []

    gpus = []
    for gpu in gpu_data:
        name = gpu.get("Name", "").lower()
        if "basic" in name or "remote" in name or "hyper-v" in name:
            continue

        gpus.append({
            "vendor": "AMD" if "amd" in name or "radeon" in name else "Intel" if "intel" in name or "uhd" in name or "iris" in name else "Other",
            "name": gpu.get("Name", ""),
            "vram_total_mb": round(gpu.get("AdapterRAM", 0) / (1024**2), 1) if gpu.get("AdapterRAM") else None,
            "driver_version": gpu.get("DriverVersion", ""),
            "video_processor": gpu.get("VideoProcessor", ""),
            "resolution": f"{gpu.get('CurrentHorizontalResolution', 0)}x{gpu.get('CurrentVerticalResolution', 0)}",
            "refresh_rate": gpu.get("CurrentRefreshRate", 0),
            "status": gpu.get("Status", ""),
            "driver_date": gpu.get("DriverDate", ""),
        })
    return gpus


# =============================================================================
# System
# =============================================================================

def processes_snapshot(top_n: int = 10) -> list[dict[str, Any]]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "",
                "user": info["username"] or "",
                "cpu": round(info["cpu_percent"] or 0.0, 1),
                "ram_percent": round(info["memory_percent"] or 0.0, 2),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: (x["cpu"], x["ram_percent"]), reverse=True)
    return procs[:top_n]


def sensors_status() -> dict[str, Any]:
    """Return hardware-sensor availability state + a human-readable message."""
    try:
        import sensors_lhm

        return {
            "state": sensors_lhm.init_state(),
            "message": sensors_lhm.status_message(),
        }
    except Exception:
        return {"state": "no_pythonnet", "message": "sensors_lhm unavailable"}


def system_snapshot() -> dict[str, Any]:
    boot_ts = psutil.boot_time()
    uptime_seconds = time.time() - boot_ts
    days, rem = divmod(int(uptime_seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    battery = _get_battery_info()

    return {
        "hostname": _hostname,
        "os": platform.platform(),
        "os_name": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "python_version": platform.python_version(),
        "boot_time": datetime.fromtimestamp(boot_ts).astimezone().isoformat(),
        "uptime_seconds": int(uptime_seconds),
        "uptime": f"{days}d {hours}h {minutes}m",
        "now": datetime.now().isoformat(),
        "battery": battery,
        "sensors": sensors_status(),
    }


def _get_battery_info() -> dict[str, Any] | None:
    """Get battery information for laptops."""
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return None

        wmi_battery = _get_wmi_cached("battery_details", r"""
            Get-CimInstance Win32_Battery | ForEach-Object {
                @{
                    DesignCapacity = $_.DesignCapacity
                    FullChargeCapacity = $_.FullChargeCapacity
                    BatteryStatus = $_.BatteryStatus
                    EstimatedChargeRemaining = $_.EstimatedChargeRemaining
                    EstimatedRunTime = $_.EstimatedRunTime
                    Chemistry = $_.Chemistry
                }
            } | ConvertTo-Json -Compress
        """, ttl=60)

        health_percent = None
        cycle_count = None
        if wmi_battery and isinstance(wmi_battery, list) and len(wmi_battery) > 0:
            bat = wmi_battery[0]
            design = bat.get("DesignCapacity", 0)
            full = bat.get("FullChargeCapacity", 0)
            if design and full:
                health_percent = round((full / design) * 100, 1)

        return {
            "percent": round(battery.percent, 1),
            "charging": battery.power_plugged,
            "time_remaining": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
            "health_percent": health_percent,
            "cycle_count": cycle_count,
        }
    except Exception:
        return None


# =============================================================================
# Snapshots
# =============================================================================

def full_snapshot() -> dict[str, Any]:
    return {
        "ts": time.time(),
        "cpu": cpu_snapshot(),
        "ram": ram_snapshot(),
        "disk": disk_snapshot(),
        "network": network_snapshot(),
        "system": system_snapshot(),
        "gpu": gpu_snapshot(),
    }


async def full_snapshot_async() -> dict[str, Any]:
    cpu, ram, disk, network, system, gpu = await asyncio.gather(
        asyncio.to_thread(cpu_snapshot),
        asyncio.to_thread(ram_snapshot),
        asyncio.to_thread(disk_snapshot),
        asyncio.to_thread(network_snapshot),
        asyncio.to_thread(system_snapshot),
        asyncio.to_thread(gpu_snapshot),
    )
    return {
        "ts": time.time(),
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "network": network,
        "system": system,
        "gpu": gpu,
    }


def light_snapshot() -> dict[str, Any]:
    """Cheap scalar-only snapshot for history sampling.

    Uses psutil instant values plus cached hardware sensors (5s TTL), so it is
    safe to call every few seconds without spawning subprocesses.
    """
    cpu_temp = None
    ct = _get_cpu_temperature()
    if ct:
        cpu_temp = ct.get("primary")

    gpu_temp = None
    gpu_fan_pct = None
    gpu_power_w = None
    try:
        gpus = _get_gpu_sensors_lhm()
        temps = [g.get("temperature_celsius") for g in gpus.values()]
        temps = [t for t in temps if t is not None]
        if temps:
            gpu_temp = round(max(temps), 1)
        fans = [g.get("fan_speed_percent") for g in gpus.values()]
        fans = [f for f in fans if f is not None]
        if fans:
            gpu_fan_pct = max(fans)
        pw = [g.get("power_draw_watts") for g in gpus.values()]
        pw = [p for p in pw if p is not None]
        if pw:
            gpu_power_w = round(max(pw), 1)
    except Exception:
        pass

    disk_temp_max = None
    try:
        dtemps = _get_disk_temperatures()
        vals = [t for t in dtemps.values() if isinstance(t, (int, float))]
        if vals:
            disk_temp_max = max(vals)
    except Exception:
        pass

    return {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "ram_pct": psutil.virtual_memory().percent,
        "swap_pct": psutil.swap_memory().percent,
        "cpu_temp": cpu_temp,
        "gpu_temp": gpu_temp,
        "disk_temp_max": disk_temp_max,
        "cpu_fan_rpm": _get_cpu_fan_speed(),
        "gpu_fan_pct": gpu_fan_pct,
        "cpu_power_w": _get_cpu_power(),
        "gpu_power_w": gpu_power_w,
    }


def humanize_bytes(n: float) -> str:
    if n is None:
        return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0:
            return f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:,.1f} EB"
