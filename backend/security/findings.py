"""Risk scoring rules and findings data model.

Findings are accumulated during an audit; each finding has a severity label,
weight, category, and structured payload for display in the UI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    id: str
    category: str
    title: str
    description: str
    weight: int
    severity: str  # info, low, medium, high, critical
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Severity bands 0=info, 1=low, 2=medium, 3=high, 4=critical
def classify_severity(weight: int) -> str:
    if weight == 0:
        return "info"
    if 1 <= weight <= 10:
        return "low"
    if 11 <= weight <= 20:
        return "medium"
    if 21 <= weight <= 35:
        return "high"
    return "critical"


def risk_label(total: int) -> str:
    if total <= 20:
        return "Low"
    if total <= 50:
        return "Medium"
    if total <= 80:
        return "High"
    return "Critical"


def new(id_: str, category: str, title: str, description: str, weight: int,
        data: dict[str, Any] | None = None) -> Finding:
    return Finding(
        id=id_,
        category=category,
        title=title,
        description=description,
        weight=weight,
        severity=classify_severity(weight),
        data=data or {},
    )


# Convenience builders for common findings.

def f_rdp_exposed(public: bool) -> Finding:
    weight = 25 if public else 20
    label = "public interface" if public else "LAN interface"
    return new(
        "rdp_exposed", "firewall_ports",
        f"RDP (3389) exposed on {label}",
        "Remote Desktop Protocol is accepting connections; review if this is intended.",
        weight,
        {"port": 3389, "public": public},
    )


def f_ssh_exposed() -> Finding:
    return new(
        "ssh_exposed", "firewall_ports",
        "SSH (22) listening",
        "SSH server detected. Use key-based auth only.",
        15, {"port": 22},
    )


def f_smb_exposed(public: bool) -> Finding:
    weight = 30 if public else 15
    label = "public" if public else "LAN"
    return new(
        "smb_exposed", "firewall_ports",
        f"SMB (port 445/139) exposed on {label}",
        "SMB is a frequent attack vector. Block at firewall if unused.",
        weight, {"ports": [139, 445], "public": public},
    )


def f_defender_disabled() -> Finding:
    return new(
        "defender_disabled", "antivirus",
        "Windows Defender disabled or real-time off",
        "Real-time protection is disabled. Malware can install without warning.",
        30,
    )


def f_defender_signatures_stale(days_old: float) -> Finding:
    return new(
        "defender_signatures_stale", "antivirus",
        f"Defender signatures {days_old:.1f} days old",
        "Update virus definitions immediately.",
        20, {"days": days_old},
    )


def f_failed_logins_many(count_24h: int) -> Finding:
    return new(
        "failed_logins_many", "authentication",
        f"{count_24h} failed login attempts in last 24h",
        "Investigate Source IP — likely automated brute force.",
        25, {"count": count_24h},
    )


def f_failed_logins_repeat_ip(ip: str, count: int) -> Finding:
    return new(
        "failed_logins_repeat", "authentication",
        f"IP {ip} failed login {count} times",
        "Repeated attempts from one source — block it.",
        15, {"ip": ip, "count": count},
    )


def f_unsigned_listener(pid: int, name: str, port: int) -> Finding:
    return new(
        "unsigned_listener", "process",
        f"Unsigned process '{name}' (pid {pid}) listening on port {port}",
        "Validate signature and path — possible malware beacon.",
        20, {"pid": pid, "name": name, "port": port},
    )


def f_suspicious_outbound(ip: str, country: str, country_code: str, pid: int, name: str) -> Finding:
    return new(
        "suspicious_outbound", "network",
        f"Outbound to suspicious country {country_code} ({country})",
        f"Process {name} (pid {pid}) connected to {ip}.",
        10, {"ip": ip, "country": country, "pid": pid, "name": name},
    )


def f_tor_outbound(ip: str, pid: int, name: str) -> Finding:
    return new(
        "tor_outbound", "network",
        f"Outbound to Tor exit node {ip}",
        f"Process {name} (pid {pid}) talks to Tor — review.",
        15, {"ip": ip, "pid": pid, "name": name},
    )


def f_firewall_disabled(profile: str) -> Finding:
    return new(
        f"firewall_off_{profile}", "firewall_ports",
        f"Windows Firewall disabled on {profile} profile",
        "Re-enable firewall protection.",
        15 if profile.lower() == "public" else 10,
        {"profile": profile},
    )


def f_guest_account() -> Finding:
    return new(
        "guest_account_enabled", "users",
        "Guest account enabled",
        "Disable Guest unless explicitly needed.",
        10,
    )


def f_new_user(name: str) -> Finding:
    return new(
        "new_user_account", "users",
        f"New user account '{name}' (created in last 7 days)",
        "Investigate whether you created this account.",
        10, {"name": name},
    )


def f_wifi_weak_auth(ssid: str, auth: str) -> Finding:
    return new(
        "wifi_weak_auth", "wifi",
        f"Saved Wi-Fi '{ssid}' uses weak encryption ({auth})",
        "WEP/Open networks are insecure — forget or upgrade.",
        15, {"ssid": ssid, "auth": auth},
    )


def f_hosts_redirect(host: str, ip: str, reason: str) -> Finding:
    return new(
        "hosts_redirect", "hosts",
        f"Hosts file redirects {host} to {ip}",
        reason,
        25, {"host": host, "ip": ip, "reason": reason},
    )


def f_arp_duplicate(mac: str, ips: list[str]) -> Finding:
    return new(
        "arp_duplicate", "network",
        f"Multiple IPs share MAC {mac}",
        "Possible ARP spoofing / MITM. Investigate.",
        20, {"mac": mac, "ips": ips},
    )


def f_unsigned_installed(name: str, publisher: str | None) -> Finding:
    return new(
        "unsigned_installed_program", "installed_programs",
        f"Installed program '{name}' has no publisher",
        "Verify the source of this installation.",
        5, {"name": name, "publisher": publisher},
    )
