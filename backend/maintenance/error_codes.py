"""Device manager error codes ported from `updater/lib/errorCodes.js`.

Pure constants + safe lookups: unknown codes never raise, they fall back to a
generic Thai message (same behaviour as the JavaScript original).
"""
from __future__ import annotations

import math
from typing import Any

ERROR_CODES: dict[int, dict[str, str]] = {
    1: {
        "text": "ยังไม่ได้กำหนดค่าอุปกรณ์",
        "hint": "เปิด Device Manager > คลิกขวาอุปกรณ์ > Update driver หรือติดตั้งไดรเวอร์จากเว็บผู้ผลิต",
    },
    3: {
        "text": "ไดรเวอร์เสียหายหรือหน่วยความจำไม่พอ",
        "hint": "รีสตาร์ตเครื่อง ถ้ายังไม่หายให้ถอนการติดตั้งไดรเวอร์ใน Device Manager แล้วติดตั้งใหม่",
    },
    10: {
        "text": "อุปกรณ์เริ่มทำงานไม่ได้",
        "hint": "กดสแกนอุปกรณ์ (pnputil /scan-devices) หรือรีสตาร์ตเครื่อง จากนั้นเปิด Device Manager > Update driver",
    },
    12: {
        "text": "ทรัพยากรระบบไม่พอ",
        "hint": "ปิดโปรแกรมที่ใช้ทรัพยากรสูงหรือเพิ่ม RAM แล้วรีสตาร์ตเครื่อง จากนั้นกดสแกนอุปกรณ์ใหม่",
    },
    14: {
        "text": "อุปกรณ์ต้องรีสตาร์ตก่อนใช้งาน",
        "hint": "รีสตาร์ตเครื่องหนึ่งครั้ง แล้วกลับมาตรวจสถานะอีกครั้ง",
    },
    18: {
        "text": "ต้องติดตั้งไดรเวอร์ใหม่",
        "hint": "ถอนการติดตั้งไดรเวอร์ใน Device Manager แล้วติดตั้งจากเว็บผู้ผลิตหรือ Windows Update",
    },
    19: {
        "text": "รีจิสทรีของไดรเวอร์เสียหาย",
        "hint": "ถอนการติดตั้งไดรเวอร์และติดตั้งใหม่ ถ้ายังไม่หายให้ใช้ System Restore",
    },
    21: {
        "text": "Windows กำลังลบอุปกรณ์ออกจากระบบ",
        "hint": "รอให้ระบบลบเสร็จแล้วรีสตาร์ตเครื่อง จากนั้นกดสแกนอุปกรณ์ใหม่",
    },
    22: {
        "text": "อุปกรณ์ถูกปิดใช้งาน",
        "hint": "เปิด Device Manager > คลิกขวาอุปกรณ์ > Enable device",
    },
    24: {
        "text": "อุปกรณ์ไม่ได้ติดตั้งหรือทำงานไม่ถูกต้อง",
        "hint": "ตรวจว่าอุปกรณ์เสียบอยู่ แล้วเปิด Device Manager > Update driver",
    },
    28: {
        "text": "ยังไม่ได้ติดตั้งไดรเวอร์",
        "hint": "เปิด Device Manager > คลิกขวาอุปกรณ์ > Update driver หรือติดตั้งไดรเวอร์จากเว็บผู้ผลิต",
    },
    29: {
        "text": "เฟิร์มแวร์ให้ทรัพยากรไม่ครบ",
        "hint": "อัปเดต BIOS/เฟิร์มแวร์จากเว็บผู้ผลิต หรือเปลี่ยนช่องเสียบ/การ์ด",
    },
    31: {
        "text": "Windows โหลดไดรเวอร์ไม่ได้",
        "hint": "ถอนการติดตั้งไดรเวอร์แล้วติดตั้งใหม่ หรืออัปเดต Windows",
    },
    32: {
        "text": "ไดรเวอร์ถูกปิดใช้งาน (service ถูก disable)",
        "hint": "เปิด Device Manager > Update driver หรือเปิด service ของไดรเวอร์ใน Services",
    },
    37: {
        "text": "ไดรเวอร์เริ่มต้นทำงานไม่สำเร็จ",
        "hint": "ถอนการติดตั้งไดรเวอร์แล้วติดตั้งใหม่ หรือติดตั้งไดรเวอร์เวอร์ชันก่อนหน้าจากเว็บผู้ผลิต",
    },
    39: {
        "text": "ไดรเวอร์หรือรีจิสทรีเสียหาย",
        "hint": "ถอนการติดตั้งไดรเวอร์และติดตั้งใหม่ ถ้ายังไม่หายให้ใช้ System Restore",
    },
    43: {
        "text": "ไดรเวอร์แจ้งว่าอุปกรณ์ล้มเหลว",
        "hint": "ตรวจสาย/ช่องเสียบ รีสตาร์ตเครื่อง แล้วอัปเดตไดรเวอร์จากเว็บผู้ผลิต",
    },
    45: {
        "text": "อุปกรณ์ไม่ได้เชื่อมต่ออยู่ตอนนี้",
        "hint": "ตรวจว่าอุปกรณ์เสียบอยู่จริง แล้วกดสแกนอุปกรณ์ใหม่",
    },
    46: {
        "text": "Windows กำลังปิดระบบจึงเข้าถึงอุปกรณ์ไม่ได้",
        "hint": "รีสตาร์ตเครื่องแล้วตรวจสถานะอีกครั้ง",
    },
    47: {
        "text": "อุปกรณ์ถูกถอดออกและรอการนำออกอย่างปลอดภัย",
        "hint": "ถอดอุปกรณ์ออกให้เรียบร้อยแล้วเสียบใหม่ จากนั้นกดสแกนอุปกรณ์",
    },
    48: {
        "text": "ไดรเวอร์ถูกบล็อกเพราะมีปัญหาที่ทราบแล้ว",
        "hint": "อัปเดตไดรเวอร์หรือ Windows ให้เป็นเวอร์ชันล่าสุดจากเว็บผู้ผลิต",
    },
    52: {
        "text": "ไม่ได้ลงนามดิจิทัล",
        "hint": "ติดตั้งไดรเวอร์ที่ลงนามดิจิทัลจากเว็บผู้ผลิต หรือตรวจสอบนโยบายลายเซ็นไดรเวอร์ของ Windows",
    },
}

FALLBACK_TEXT = "รหัสข้อผิดพลาด {code}"
FALLBACK_HINT = "ค้นหา Code {code} ใน Device Manager"

NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
NOT_IMPLEMENTED_TEXT = "ยังไม่ได้ติดตั้งการทำงานนี้ในสเตจ scaffold"
NOT_IMPLEMENTED_HINT = "รอ MERGE-003/004 หรืออัปเดตโมดูล maintenance ก่อนใช้งาน"


def count() -> int:
    """Number of ported device error codes."""
    return len(ERROR_CODES)


def _as_int(code: Any) -> int | None:
    if isinstance(code, bool):
        return int(code)
    try:
        return int(code)
    except (TypeError, ValueError):
        pass
    try:
        value = float(code)
    except (TypeError, ValueError):
        return None
    return int(value) if math.isfinite(value) else None


def describe(code: Any) -> dict[str, str]:
    """Return `{"text": ..., "hint": ...}` — never raises (unknown codes fall back)."""
    if code == NOT_IMPLEMENTED:
        return {"text": NOT_IMPLEMENTED_TEXT, "hint": NOT_IMPLEMENTED_HINT}
    number = _as_int(code)
    if number is None or number == 0:
        return {"text": "", "hint": ""}
    entry = ERROR_CODES.get(number)
    if entry is not None:
        return {"text": entry["text"], "hint": entry["hint"]}
    return {
        "text": FALLBACK_TEXT.format(code=number),
        "hint": FALLBACK_HINT.format(code=number),
    }


def text(code: Any) -> str:
    """Short message for a code (empty string when the code is 0/invalid)."""
    return describe(code)["text"]


def hint(code: Any) -> str:
    """Remediation hint for a code (empty string when the code is 0/invalid)."""
    return describe(code)["hint"]
