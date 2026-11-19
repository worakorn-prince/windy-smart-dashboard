# API Reference — Windy Smart Dashboard

Local-only HTTP/WebSocket API ของแดชบอร์ด (FastAPI) เอกสารนี้สรุป endpoint ที่มีจริง
ใน `backend/main.py` + `backend/maintenance/router.py` + `backend/viewer_api.py`

## เปิดเอกสารอัตโนมัติ

รันแอปแล้วเปิด:

| URL | รายละเอียด |
|-----|------------|
| `http://127.0.0.1:8000/docs` | Swagger UI (ลองยิง request ได้) |
| `http://127.0.0.1:8000/redoc` | ReDoc (อ่านสคีมาแบบอ่านง่าย) |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI 3 schema (ใช้ generate client) |

`info.title` = `Windy Smart Dashboard`, `info.version` = `APP_VERSION` ใน `backend/main.py`
(ปัจจุบัน `0.6.2`) — ตรงกับฟิลด์ `version` ของ `GET /api/version`

> ⚠️ **Bind `127.0.0.1` เท่านั้น** — เซิร์ฟเวอร์ฟังเฉพาะ loopback ไม่เปิดให้เครื่องอื่นในเน็ตเวิร์ก
> เข้าถึง (โดยดีไซน์) ถ้าต้องการเข้าจากระยะไกลให้ใช้ SSH tunnel / port-forward ผ่าน loopback

## Auth model

| ระดับ | เงื่อนไข |
|-------|----------|
| `-` (public) | เรียกได้จาก loopback โดยไม่ต้องมี token |
| `admin` | ถ้าตั้ง `DASH_ADMIN_TOKEN` ต้องส่ง header `X-Admin-Token: <token>`; ถ้าไม่ตั้ง อนุญาตเฉพาะ request จาก loopback (`127.0.0.1` / `::1`) |
| `loopback` | รับเฉพาะ request ที่มาจาก loopback |
| `loopback+admin` | ต้องมาจาก loopback **และ** ผ่าน admin (maintenance write ยังต้องมี CSRF guard ด้วย) |

## Endpoints

### Core / monitoring

| Method | Path | Auth | คำอธิบาย |
|--------|------|------|----------|
| GET | `/api/version` | - | ชื่อแอป, `version`, `python`, `platform`, `port` (สำหรับ health check ภายนอก) |
| GET | `/api/system` | - | snapshot ระบบ: system / cpu / ram / gpu |
| GET | `/api/sensors/status` | - | สถานะ LibreHardwareMonitor (sanitized: available / elevated / state / reason / message) |
| GET | `/api/history?range=5m\|1h\|6h\|24h` | - | ประวัติ metrics แบบ bucketed (~360 จุด); range อื่นได้ 422 |
| GET | `/api/processes/{pid}` | - | รายละเอียดโปรเซส + tree 3 ระดับ + listening ports |
| GET | `/api/processes/{pid}/history?limit=60` | - | sample CPU/RAM ของโปรเซส (`limit` 1–240), เก่า→ใหม่ |
| GET | `/api/health/disk` | - | usage ต่อ volume, SMART health, พยากรณ์วันดิสก์เต็ม |
| POST | `/api/speedtest` | - | รัน speed test แบบ synchronous แล้ว broadcast ผลไป `/ws/metrics` |

### Alerts

| Method | Path | Auth | คำอธิบาย |
|--------|------|------|----------|
| GET | `/api/alerts/rules` | - | กฎแจ้งเตือนที่ใช้งานจริง + channels |
| PUT | `/api/alerts/rules` | - | แทนที่กฎ + channels (validate, hot-reload; ผิดรูปแบบได้ 400) |
| POST | `/api/alerts/test` | admin | ส่ง alert ทดสอบผ่านทุก channel ที่เปิดอยู่ (`title`, `message` เป็น optional) คืนรายชื่อ channel ที่ส่ง |
| POST | `/api/alerts/notify` | admin | รับ alert จากภายนอก (เช่น `scripts/compare.py`) ต้องส่ง header `X-Requested-With: windy-dashboard` — broadcast `type: alert` ไป `/ws/metrics` แล้ว dispatch ผ่าน channels |

### Security

| Method | Path | Auth | คำอธิบาย |
|--------|------|------|----------|
| GET | `/api/security/suspicious` | - | รายการ country code ที่ตั้งเป็นน่าสงสัย + ค่า default |
| PUT | `/api/security/suspicious` | - | override รายการประเทศ (`{"countries": ["RU", ...]}`) |
| POST | `/api/security/audit` | - | รัน audit ทันที คืน report เต็ม |
| GET | `/api/security/audit/schedule` | - | อ่านคอนฟิก audit ตามเวลา + `last_run` / `next_due` |
| PUT | `/api/security/audit/schedule` | - | แก้คอนฟิก audit ตามเวลา (`enabled`, `intervalHours`) validate, hot-reload (ผิดรูปแบบได้ 400) |
| POST | `/api/security/audit/schedule/run` | admin | รัน audit ทันทีและบันทึกผลย่อ (ต้องส่ง header `X-Requested-With: windy-dashboard`) |
| GET | `/api/security/audits?limit=20` | admin | ผล audit ตามเวลาที่บันทึกไว้ (`limit` 1–200), ใหม่→เก่า |
| POST | `/api/security/kill` | admin | kill โปรเซส (`{"pid": 123, "force": false}`) |
| POST | `/api/security/block` | admin | เพิ่ม firewall block rule (`{"ip": "1.2.3.4"}`, IP ผิดได้ 422) |
| POST | `/api/security/unblock` | admin | ลบ block rule (`{"rule_name": "..."}`) |
| GET | `/api/security/blocked` | - | list rule `WindySmartDashboard_block_*` ทั้งหมด |
| GET | `/api/security/events?limit=50` | admin | เหตุการณ์ความปลอดภัยที่บันทึกไว้ (`limit` 1–200), ใหม่→เก่า |
| POST | `/api/security/export` | - | export audit (`{"fmt": "json\|html\|pdf", "report": {...}}`) เป็นไฟล์ download |

### Reports

| Method | Path | Auth | คำอธิบาย |
|--------|------|------|----------|
| POST | `/api/reports/generate` | admin | สร้างรายงาน HTML (`{"days": 1\|7}`, ค่าอื่นได้ 400) แล้ว prune ของเก่า |
| GET | `/api/reports` | admin | list รายงานที่สร้างแล้ว, ใหม่→เก่า |
| GET | `/api/reports/schedule` | admin | อ่านตารางเวลาสร้างรายงานอัตโนมัติ + `nextRun` (timestamp ครั้งถัดไป) |
| PUT | `/api/reports/schedule` | admin | ตั้งตารางเวลา (`enabled`, `intervalHours` 0.25–168, `days`) validate + persist แล้ว reschedule loop ทันที (ต้องส่ง header `X-Requested-With: windy-dashboard`; ผิดรูปแบบได้ 400, persist ไม่สำเร็จได้ 500) |
| GET | `/api/reports/{name}` | admin | ดาวน์โหลดรายงานหนึ่งไฟล์ (ชื่อต้องตรง pattern, กัน path traversal) |

### Maintenance (`/api/maintenance`)

| Method | Path | Auth | คำอธิบาย |
|--------|------|------|----------|
| GET | `/status` | loopback | ข้อมูลระบบสำหรับหน้า maintenance |
| GET | `/scan` | loopback | สแกนอุปกรณ์/สภาพระบบ (`?refresh=1` บังคับสแกนใหม่) |
| GET | `/history` | loopback | ประวัติการทำงานของ maintenance (`?limit=100` cap ที่ 500) |
| GET | `/startup` | loopback | รายการโปรแกรมที่รันตอน boot เครื่อง |
| POST | `/startup/toggle` | loopback+admin | เปิด/ปิดรายการ startup ตาม `id` — ต้องส่ง `{"confirm": "startup"}` มาด้วย (มี CSRF guard) |
| GET | `/windows-update` | loopback | สถานะ Windows Update ของเครื่อง |
| POST | `/windows-update/scan` | loopback+admin | สั่งสแกน Windows Update (มี CSRF guard) |
| GET | `/clean/summary` | loopback | สรุปพื้นที่ที่ล้างได้ก่อนยืนยัน |
| POST | `/action` | loopback+admin | รัน action เดี่ยว (มี CSRF guard) |
| POST | `/clean` | loopback+admin | ล้างไฟล์ตามที่เลือก (มี CSRF guard) |
| POST | `/export` | loopback+admin | export devices/history เป็น csv/json (มี CSRF guard) |
| POST | `/relaunch` | loopback+admin | relaunch แอป คืน 202 (มี CSRF guard) |

### Viewer (`/api/viewer`)

| Method | Path | Auth | คำอธิบาย |
|--------|------|------|----------|
| GET | `/single` | - | dataset scopeboard รายโปรเจกต์ (ไม่มีไฟล์ dataset ได้ 404 `NO_DATA`) |
| GET | `/all` | - | dataset รวมทุกโปรเจกต์ (ไม่มีไฟล์ dataset ได้ 404 `NO_DATA`) |
| GET | `/status` | - | สถานะไฟล์ dataset ทั้งสองชุด (`exists` / `size` / `modified`) |
| POST | `/rebuild` | admin | รัน `scripts/export_json.py` (+ `aggregate.py` ถ้า `{"aggregate": true}`) แล้วคืนสถานะล่าสุด — ต้องส่ง header `X-Requested-With: windy-dashboard`; สคริปต์ล้มได้ 502 |

## WebSockets

| Path | ทิศทาง | Envelope |
|------|--------|----------|
| `/ws/metrics` | server → client | `{"type": "processes" \| "system" \| "metrics" \| "speedtest_result" \| "alert", ...}` |
| `/ws/security` | server → client | `{"type": "hello" \| "security_event", ...}` |

- ทุกข้อความเป็น JSON object ที่มีฟิลด์ `type` ระบุชนิดเสมอ (frontend ใช้ `type` เป็นตัวแยก handler)
- `/ws/metrics` greeting หลัง connect ส่ง 3 ข้อความตามลำดับ: `processes` → `system` → `metrics`
  (full snapshot) แล้วจึงเพิ่ม client เข้าชุด broadcast — live deltas เป็น object บางส่วน
  จึงต้องรอ full snapshot ก่อนกัน frontend state เสียหาย
- หลัง greeting: `metrics` (live snapshot) ~1 Hz และ full snapshot ใหม่ทุก ~30 วิ
  (`METRICS_FULL_INTERVAL`), นอกจากนี้มี `speedtest_result` / `alert` broadcast ตามเหตุการณ์
- full snapshot คำนวณผ่าน single-flight snapshot cache — เปิดหน้าพร้อมกันหลาย client
  ก็คำนวณครั้งเดียวต่อช่วง (soft TTL = interval, hard TTL = 3×interval สำหรับ greeting,
  มี lock ต่อ event loop กันคำนวณซ้อน) และ pre-warm ที่ startup สำหรับ processes/system snapshot
- `/ws/security` ส่ง `hello` (พร้อม `suspicious_countries`) แล้วตามด้วย event ใหม่
- client ไม่ต้องส่งข้อความ; socket จะเปิดค้างจนกว่าจะ disconnect

## ตัวอย่าง

```powershell
curl.exe http://127.0.0.1:8000/api/version
curl.exe "http://127.0.0.1:8000/api/history?range=6h"
curl.exe -X POST http://127.0.0.1:8000/api/reports/generate `
  -H "Content-Type: application/json" -H "X-Admin-Token: $env:DASH_ADMIN_TOKEN" `
  -d '{\"days\": 1}'
```

## หมายเหตุการดูแลเอกสาร

- `docs/API.md` เป็นเอกสารที่เขียนด้วยมือ — เมื่อเพิ่ม/แก้ endpoint ให้อัปเดตตารางนี้
  และ bump `APP_VERSION` ใน `backend/main.py` เมื่อเป็น breaking change
- สคีมาที่ `/openapi.json` คือ source of truth ของ signature; เทสต์ `backend/tests/test_openapi.py`
  ตรวจว่า path สำคัญยังอยู่ในสคีมาและ catch-all ของ SPA ไม่หลุดเข้าไป
