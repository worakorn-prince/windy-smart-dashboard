# MAINTENANCE-MODULE — แผนรวมโมดูล Maintenance (MERGE-001)

> สถานะ: **implemented (release v0.3.0)** — โค้ดจริงอยู่ที่ `backend/maintenance/` + หน้า `/maintenance`
> ขอบเขต: พอร์ตความสามารถของโปรเจกต์ `updater` (Node.js) เข้ามาเป็นโมดูลใน `Dashboard` (Python FastAPI + Vue3/TS)
> หมายเหตุ: `relaunch` ปิดตั้งแต่ตั้งใจ (`501 RELAUNCH_DISABLED` ตาม CHANGELOG 0.3.0)

---

## 1) Goals / Non-goals

### Goals
1. **รวมความสามารถ"งานบำรุงรักษา" (maintenance) เข้า Dashboard** ให้เป็นหน้าเดียวใน SPA เดิม เพื่อไม่ต้องเปิด 2 โปรเซส (Dashboard :8000 + updater :3100)
2. **รักษามาตรฐานความปลอดภัยเดิมของ updater ครบถ้วน 100%** (ดู checklist หัวข้อ 6) ได้แก่:
   - allowlist ค่าคงที่ + spawn แบบ array (ไม่ผ่าน shell string)
   - ห้าม auto-install / ห้ามรันคำสั่งอิสระจากผู้ใช้
   - ต้องมี confirm + บันทึก log history ทุก action
   - bind `127.0.0.1` เท่านั้น
   - กัน CSRF และ Host header injection
3. **รวมศูนย์ auth กับ admin token เดิมของ Dashboard**: ใช้ `require_admin` + header `X-Admin-Token` (ฟังก์ชัน `require_admin` ใน `backend/main.py`) เป็นด่านเดียว ไม่เพิ่มกลไก auth ใหม่
4. **ใช้ SQLite/ประวัติชุดเดียวกับ Dashboard** ที่มีอยู่ (`backend/history.py` — WAL + lock + retention ใน `_get_conn`/retention sweep) แทน history แบบ JSON ไฟล์ของ updater (`lib/history.js`, atomic write)
5. ให้ฟีเจอร์ฝั่ง UI ที่ดีของ updater คงอยู่: sort + `aria-sort`, tab keyboard nav, tooltip คอลัมน์ปัญหา, confirm ก่อนลบ, force refresh, admin banner + UAC (ทั้งหมดใน `public/app.js` ของ updater)

### Non-goals (รอบนี้ไม่ทำ)
1. ไม่ทำ **auto-update / auto-install** แพ็กเกจใด ๆ ทั้งสิ้น (ห้ามเด็ดขาด — สอดคล้อง review เดิมของ updater)
2. ไม่ทำ remote access / เปิดให้เข้าจาก LAN หรือ internet (ยัง bind `127.0.0.1`)
3. ไม่ทำ multi-user / role หลายระดับ (มี admin token เดียวเหมือนเดิม)
4. ไม่ย้าย Windows API ทั้งหมดของ Dashboard (`backend/security/winapi.py`) ไปรวมกับ maintenance — คนละโดเมน แต่ใช้ helper ร่วมกันได้
5. ไม่แตะพฤติกรรมของ routes `/api/security/*` ใน `backend/main.py` ที่มีอยู่
6. ไม่ทำ scheduler/daemon อัตโนมัติ (ทุก action ต้องมาจากผู้ใช้กดยืนยัน)

---

## 2) ADR — เลือกแนวทางรวมโมดูล

### บริบท
Dashboard มี backend FastAPI (`backend/main.py` — app object, routes `/api/system`, `/api/sensors/status`, `/api/history`, `/api/speedtest`, `/api/security/*`, SPA fallback) และ frontend Vue3+TS+Vite (`App.vue`, `pages/Security.vue`, `stores/security.ts`).
updater เป็น Node.js (`server.js`) ที่ทำงานคนละ runtime — ไม่สามารถ `require` ข้ามภาษาได้ ต้องเลือกวิธีอินทิเกรต

### ทางเลือก

| # | แนวทาง | ข้อดี | ข้อเสีย | สรุป |
|---|--------|-------|---------|------|
| **A** | **พอร์ตเป็น Python module** (`backend/maintenance/`) แล้วเรียกผ่าน FastAPI route ใหม่ | runtime เดียว, ใช้ auth/history/SQLite เดิมร่วมกัน, bind 127.0.0.1 จุดเดียว, ไม่ต้องมีโปรเซสที่สอง, ทดสอบด้วย `python -m unittest` ได้ตาม workflow ปัจจุบัน | ต้องพอร์ตโค้ด JS→Python ทั้งชุด (งานมากสุด), เสี่ยง behavior drift ถ้าไม่เขียน parity test | **เลือก A** |
| **B** | **Embed iframe** ชี้ไป updater :3100 ที่ยังรันแยก | งานน้อยสุด, ของเดิมไม่ต้องแก้ | ต้องรัน 2 โปรเซส/2 พอร์ต, auth ซ้อน 2 ชุด, CSRF/Host guard ต้องคุม 2 จุด, history แยก 2 ที่, UX สับสน (ซ้ำซ้อนกับ Dashboard) | ไม่เลือก |
| **C** | **ไม่รวม** — คง updater แยกไว้ | ไม่มีความเสี่ยง migration | เป้าหมายหลัก (รวมศูนย์) ไม่บรรลุ, ต้องดูแล 2 codebase ตลอดไป | ไม่เลือก |

### Decision
**เลือก A — พอร์ตเป็น Python module ใต้ `backend/maintenance/`** โดย:
- ใช้ **namespace `/api/maintenance/*`** (หลีกเลี่ยง collision กับ `/api/system` เดิม)
- ใช้ auth เดิม `require_admin` + `X-Admin-Token`
- เก็บ `ALLOWED_ACTIONS` / `ALLOWED_TARGETS` เป็นค่าคงที่ในโมดูล Python (พอร์ตจาก `lib/updater.js`, `lib/cleaner.js`)
- เก็บ cache semantics ของ updater (scanner 30s `lib/scanner.js`; system 60s `lib/system.js`) เพื่อไม่ให้พฤติกรรมเปลี่ยน
- **คงอ้างอิงรหัสข้อผิดพลาด 22 รหัส** จาก `lib/errorCodes.js` ให้ครบ (พอร์ตเป็น dict ค่าคงที่) — *แก้จาก 25: MERGE-002 ยืนยันกับต้นทางแล้วว่ามี 22 รหัส (นับจากตารางจริง)*

### Consequences
- ต้องมี **parity test** เทียบผลลัพธ์ Python กับ JS เดิมในจุดสำคัญ (parsing, error codes, allowlist) ก่อนปิดงาน
- updater เดิมจะถูกเปลี่ยนสถานะเป็น **legacy/อ้างอิง** — ห้ามลบจนกว่า parity test ผ่าน
- ถ้าอนาคตต้องการกลับไปแบบ B ให้ทำได้ผ่าน adapter ชั้น route เท่านั้น (ออกแบบให้ route เป็น thin layer)

---

## 3) Route collision + Endpoint table

### ปัญหา collision
- Dashboard มี route `/api/system` อยู่แล้วใน `backend/main.py` และ updater ต้องการข้อมูล system/relaunch จึง **ห้ามใช้ `/api/system` ซ้ำ** — ต้องใช้ `/api/maintenance/system`
- route `/api/history` ของ Dashboard ใช้สำหรับ history อื่นอยู่แล้ว → maintenance ใช้ `/api/maintenance/history`
- namespace ใหม่ทั้งหมดต้องอยู่ใต้ `/api/maintenance/*` และต้องอยู่ **ก่อน** SPA fallback ใน `backend/main.py`
- ต้องเพิ่ม `/api/maintenance` เข้า **CORS allowlist** ตามแนวทาง CORS middleware ใน `backend/main.py` (ถ้า SPA เสิร์ฟจาก origin เดียวกัน ไม่ต้องเพิ่ม origin ใหม่ แต่ต้องตรวจให้ endpoint ใหม่ไม่ถูก block)

### Endpoint table

| Method | Path (ใหม่) | ที่มา (updater) | ต้อง auth | หมายเหตุ |
|--------|-------------|-----------------|-----------|----------|
| GET | `/api/maintenance/status` | `lib/system.js` (cache 60s) | ไม่ | อ่านสถานะระบบ (read-only) |
| GET | `/api/maintenance/scan` | `lib/scanner.js` (cache 30s) | ไม่ | ผลสแกน + tooltip ปัญหา |
| GET | `/api/maintenance/history` | `lib/history.js` | ไม่ | อ่านประวัติการกระทำ |
| POST | `/api/maintenance/action` | `lib/updater.js` (`ALLOWED_ACTIONS`) | **ใช่** | body ต้องอยู่ใน allowlist เท่านั้น |
| POST | `/api/maintenance/clean` | `lib/cleaner.js` (`ALLOWED_TARGETS`) | **ใช่** | ต้องมี confirm + log |
| POST | `/api/maintenance/export` | `lib/export.js` | **ใช่** | ส่งออกข้อมูล (ไม่รันคำสั่ง) — สร้าง CSV (BOM+CRLF) / JSON ใน `maintenance/export.py` เอง ส่งกลับเป็น response ไม่เขียนดิสก์ |
| POST | `/api/maintenance/relaunch` | `lib/system.js` (relaunch) | **ใช่** | เลี่ยงพอร์ต 3100 เดิม → ใช้กลไกของ Dashboard (launcher `run.ps1`, หัวข้อ "How to start" ใน `README.md`) |

> หมายเหตุ: endpoint ที่ "ไม่ต้อง auth" ยังคงต้องถูกป้องกันด้วย Host check + CSRF guard (ดูหัวข้อ 6) และอ่านจาก localhost เท่านั้น
> หมายเหตุ CORS: โหมด dev ใช้ Vite proxy `/api` และ `/ws` → `127.0.0.1:8000` (หัวข้อ "Development mode" ใน `README.md`) และโหมด prod เป็น same-origin → โดยทั่วไปไม่ต้องเพิ่ม origin ใหม่ใน allowlist (CORS middleware ใน `backend/main.py`) แต่ต้องยืนยันว่า path ใหม่ไม่ถูกบล็อก
> **สำคัญ**: frontend store เดิมอย่าง `stores/security.ts` ยิง `fetch('/api/...')` แบบ **ไม่ส่ง `X-Admin-Token`** — ต้องตัดสินใจเรื่องการแนบ token (ดูคำถามข้อ 2)

---

## 4) Backend design — `backend/maintenance/`

โครงไฟล์และหน้าที่ (พอร์ตจาก updater โดยตรง):

```
backend/maintenance/
├── __init__.py          # export public API ของโมดูล
├── router.py            # (ใหม่) FastAPI APIRouter รวม endpoint /api/maintenance/*
├── powershell.py        # <- lib/powershell.js      (เรียก PowerShell อย่างปลอดภัย)
├── scanner.py           # <- lib/scanner.js         (cache 30s, tooltip ปัญหา)
├── error_codes.py       # <- lib/errorCodes.js      (22 รหัส เป็นค่าคงที่)
├── actions.py           # <- lib/updater.js         (ALLOWED_ACTIONS + validate)
├── cleaner.py           # <- lib/cleaner.js         (ALLOWED_TARGETS + validate)
├── history.py           # <- lib/history.js         (ห่อ backend/history.py)
├── export.py            # <- lib/export.js
└── system.py            # <- lib/system.js          (cache 60s, relaunch)
```

### หน้าที่/แนวปฏิบัติสำคัญ
- **powershell.py**: พอร์ตกลไก `_run_powershell()` จาก `backend/security/winapi.py` (`asyncio.create_subprocess_exec` + `asyncio.wait_for` + `kill`) และใช้ `_parse_json_list()` ร่วมกัน เพื่อลดโค้ดซ้ำ — **เรียกด้วย argument array เสมอ ไม่สร้าง command string**
- **actions.py / cleaner.py**: ตรวจค่าที่รับเข้ามา **ต้องเทียบกับ allowlist ค่าคงที่ก่อนทุกครั้ง** แล้วจึง map ไปเป็น argument array; ถ้าไม่อยู่ใน allowlist → ปฏิเสธด้วย error code ที่ถูกต้อง ห้าม fallback ไปรันอะไรก็ได้
- **history.py**: เขียนผ่าน SQLite เดิม (`backend/history.py` — WAL + lock + retention ใน `_get_conn`/retention sweep) **ทุก action ที่เปลี่ยนแปลงระบบต้องมี record** (who/what/before/after/result/timestamp)
- **error_codes.py**: พอร์ตครบ **22 รหัส** พร้อมข้อความไทย/อังกฤษ ให้ตรงกับ `lib/errorCodes.js` เพื่อให้ frontend map ได้เหมือนเดิม
- **router.py**: เป็น **thin layer** — ตรวจ auth (`require_admin`), validate body, เรียก service, คืน response; ไม่มี business logic
- **export.py**: สร้าง CSV (BOM + CRLF) และ JSON ภายในโมดูลเอง แล้วส่งกลับเป็น response — **ไม่เขียนไฟล์ลงดิสก์** (ตัดความเสี่ยง path traversal) และไม่ผูกกับ `backend/exporters/` ซึ่งเป็นคนละโดเมน

### Auth / config
- ใช้ `require_admin` + header `X-Admin-Token` (ฟังก์ชัน `require_admin` ใน `backend/main.py`) และค่า `ADMIN_TOKEN` จาก `backend/config.py`
- ค่าคอนฟิกที่อ้างอิง: `HOST=127.0.0.1`, `PORT=8000`, `HISTORY_DB`, `CACHE_DIR` (`backend/config.py`); ชื่อ env override ตามตาราง Configuration ใน `README.md` (`DASH_HOST`, `DASH_PORT`)
- ต้องรักษา invariant: **bind `127.0.0.1` เท่านั้น** (หัวข้อเปิดของ `README.md`) และ cache DB อยู่ที่ `backend/.cache/` (WAL, หัวข้อ "Metrics history" ใน `README.md`)

### Testing
- ชุดเทสต์เดิมเป็น **pytest** ที่ `backend/tests/` (หัวข้อ "Testing" ใน `README.md`) — มี `conftest.py`, `test_api_smoke.py`, `test_parsers.py`, `test_history.py`, `test_alerts.py`, `test_hw_sensors.py`
- โมดูลใหม่ต้องเพิ่มเทสต์ใน `backend/tests/` แนวเดียวกัน และรันด้วย `python -m pytest tests -q`
- **ใช้ `test_api_smoke.py` เป็นฐาน** สำหรับ smoke test ของ `/api/maintenance/*`

---

## 5) Frontend design — `Maintenance.vue` + components + store

### ที่มา/ของเดิม (ยืนยันจากโค้ดจริง)
- SPA โครง Vue3 + TS + Vite + **Pinia**; หน้าอยู่ใน `frontend/src/pages/` — `Security.vue` เป็นตัวอย่างที่ดี: import store + การ์ด, เรียก `store.connect()` ใน `onMounted`, มี banner info และจัดวางด้วย class `grid` / `full-row`
- store แนวเดียวกับ `stores/security.ts` (`defineStore('...', () => {...})` + `fetch('/api/...')`)
- component แยกโฟลเดอร์ตามโดเมน: `components/security/*`, `components/dashboard/*` (ดู "Project structure" ใน `README.md`)
- ตัวช่วยที่ใช้ซ้ำได้: `composables/useWebSocket`, directive `autoTip` สำหรับ tooltip ข้อความถูกตัด
- router/เมนูอยู่ที่ `frontend/src/main.ts` — **ไม่ใช่ `App.vue`** (`App.vue` เป็น layout + global styles)

### ของใหม่
```
frontend/src/
├── pages/Maintenance.vue                  # หน้าใหม่ (โครงเดียวกับ Security.vue)
├── stores/maintenance.ts                  # Pinia store (แนวเดียวกับ stores/security.ts)
└── components/maintenance/
    ├── MaintenanceTable.vue               # ตาราง + sort + aria-sort (พอร์ต public/app.js)
    ├── MaintenanceToolbar.vue             # refresh / force refresh (public/app.js)
    ├── MaintenanceActions.vue             # ปุ่ม action + confirm ก่อนรัน (public/app.js)
    ├── MaintenanceAdminBanner.vue         # admin banner + UAC (public/app.js)
    ├── MaintenanceHistory.vue             # แสดงประวัติ (อ่านจาก /api/maintenance/history)
    └── MaintenanceIssuesCard.vue          # คอลัมน์ปัญหา + tooltip (public/app.js)
```

### พฤติกรรมที่ต้องพอร์ตให้ครบ (parity กับ updater)
| ฟีเจอร์ | ต้นทาง | ปลายทาง |
|---------|--------|---------|
| sort + `aria-sort` | `public/app.js` | `MaintenanceTable.vue` |
| เก็บ state ใน localStorage | `public/app.js` | `stores/maintenance.ts` (แนวเดียวกับที่ Dashboard ใช้เก็บ dark mode / series chips) |
| admin banner + UAC | `public/app.js` | `MaintenanceAdminBanner.vue` (แนวเดียวกับ banner ใน `Security.vue`) |
| confirm ก่อนลบ | `public/app.js` | `MaintenanceActions.vue` |
| force refresh (ข้าม cache) | `public/app.js` | `MaintenanceToolbar.vue` |
| tooltip คอลัมน์ปัญหา | `public/app.js` | ใช้ directive `autoTip` เดิม แทนการเขียนใหม่ |
| tab keyboard nav | `public/app.js` | `MaintenanceTable.vue` / `MaintenanceActions.vue` |

### ต้องเชื่อมกับของเดิม
- เพิ่ม route + เมนูใน `frontend/src/main.ts` ให้เข้าถึงหน้า Maintenance ได้
- ใช้ `useWebSocket` (`composables/useWebSocket`) ถ้าต้องการ live push ของงานบำรุงรักษา — **ไม่บังคับ** ในรอบแรก (ใช้ polling + force refresh ไปก่อน)
- **รักษา accessibility เดิม**: `aria-sort`, keyboard nav, focus management ต้องไม่ถอยหลัง

---

## 6) Security parity checklist

เกณฑ์: ทุกข้อต้อง "มีเหมือน/ดีกว่า" ของ updater เดิม มิฉะนั้นห้าม merge

| # | มาตรการ | updater มีที่ไหน | Dashboard มีอยู่แล้ว | จะบังคับใช้อย่างไรใน maintenance |
|---|---------|------------------|----------------------|-----------------------------------|
| 1 | Bind `127.0.0.1` เท่านั้น | `server.js` (bind) | `backend/config.py` (`HOST=127.0.0.1`) | ใช้ค่า config เดิม ไม่เพิ่ม host ใหม่ |
| 2 | Host header check | `server.js` | ยังไม่มีในรูปแบบนี้ | เพิ่ม middleware/dependency ตรวจ `Host` เฉพาะ `/api/maintenance/*` |
| 3 | CSRF guard | `server.js` | ยังไม่มีในรูปแบบนี้ | บังคับ: POST ต้องมี custom header + ตรวจ Origin/Referer |
| 4 | Admin auth | updater มี admin/UAC (`public/app.js`) | `require_admin` + `X-Admin-Token` (ฟังก์ชัน `require_admin` ใน `backend/main.py`) | ทุก POST ของ maintenance ต้องผ่าน `require_admin`; **store ใหม่ต้องแนบ header เอง** เพราะ store เดิม (`stores/security.ts`) ไม่ได้แนบ token — ต้องยืนยันว่าการไม่แนบเป็นเพราะ endpoint เดิมไม่ถูก gate |
| 5 | Allowlist ค่าคงที่ | `lib/updater.js`, `lib/cleaner.js` | — (Dashboard ไม่มี allowlist กลางมาก่อน) | พอร์ต allowlist เป็นค่าคงที่แยกไฟล์ + validate ก่อนทุกครั้ง |
| 6 | Spawn แบบ array (ไม่ผ่าน shell string) | `lib/powershell.js` | `_run_powershell` ใน `backend/security/winapi.py` | ใช้ `create_subprocess_exec` + array เท่านั้น |
| 7 | Timeout + kill process | `lib/powershell.js` | `_run_powershell` ใน `backend/security/winapi.py` (`wait_for`+`kill`) | ใช้ helper เดียวกัน (timeout คงที่จาก config) |
| 8 | ห้าม auto-install | นโยบายเดิมของ updater | — | เอกสารนี้ระบุเป็น Non-goal + ไม่มี endpoint ใดติดตั้ง |
| 9 | Confirm ก่อนทำลายข้อมูล | `public/app.js` | — | UI ต้องมี confirm dialog ก่อน POST clean/action |
| 10 | Log history ทุก action | `lib/history.js` (atomic write) | `backend/history.py` (WAL+lock+retention) | เขียน SQLite ทุก action สำเร็จ+ล้มเหลว |
| 11 | Cache เพื่อลดภาระ | scanner 30s (`scanner.js`), system 60s (`system.js`) | มี `CACHE_DIR` (`config.py`) | คงค่า TTL เดิม + force refresh ได้ (`app.js`) |
| 12 | Error codes มาตรฐาน | `lib/errorCodes.js` (22 รหัส) | — | พอร์ตครบ 22 รหัส ห้ามย่อ |
| 13 | Export ปลอดภัย | `lib/export.js` | สร้าง CSV/JSON เอง (ไม่มี exporter กลางที่ใช้ได้ตรงโดเมน) | สร้างในหน่วยความจำ + ไม่เขียนดิสก์ → ไม่มี path traversal; ยังไม่กัน formula injection (ดู notes) |

**เกณฑ์ผ่าน**: ทุกแถวต้องมีสถานะ "ครบ" + มีเทสต์ยืนยันอย่างน้อยข้อ 2,3,4,5,6,9 (เขียนใน `backend/tests/` รันด้วย `python -m pytest tests -q` ตามหัวข้อ "Testing" ใน `README.md`)

---

## 7) Task breakdown + Acceptance + ประมาณเวลา

### MERGE-002 — Scaffold + Security guards (โครง + ด่านความปลอดภัย)
- สร้าง `backend/maintenance/` ตามหัวข้อ 4 (ไฟล์เปล่า/โครง) + `router.py` ลงทะเบียนใน `main.py` ก่อน SPA fallback
- เพิ่ม Host check + CSRF guard + ผูก `require_admin` กับทุก POST
- พอร์ต `error_codes.py` (22 รหัส) จาก `lib/errorCodes.js`
- **Acceptance**: endpoint `/api/maintenance/status` ตอบได้; POST ที่ไม่มี token → 403; POST ที่ Host ผิด → ปฏิเสธ; ทดสอบด้วย `python -m pytest tests -q` ผ่าน โดยใช้ `backend/tests/test_api_smoke.py` เป็นฐานเทสต์
- **ประมาณ**: 0.5–1 วัน

### MERGE-003 — Backend features (พอร์ต logic)
- พอร์ต `scanner.py` (cache 30s), `system.py` (cache 60s, relaunch), `actions.py` (`ALLOWED_ACTIONS`), `cleaner.py` (`ALLOWED_TARGETS`), `export.py`, `history.py`
- รวม helper PowerShell ให้ใช้ `_run_powershell` ของ `backend/security/winapi.py` ร่วมกัน
- **Acceptance**: ทุก endpoint ทำงานตรงกับ updater; allowlist ปฏิเสธค่านอกลิสต์; history ถูกเขียนทุก action; parity test error codes ผ่าน 25/25; ทดสอบด้วย `python -m pytest tests -q` ผ่าน
- **ประมาณ**: 1.5–2.5 วัน

### MERGE-004 — Frontend (หน้า + component + store)
- สร้าง `pages/Maintenance.vue`, `stores/maintenance.ts`, `components/maintenance/*` ตามหัวข้อ 5
- พอร์ต sort/`aria-sort`, keyboard nav, tooltip, localStorage, confirm, force refresh, admin banner + UAC
- เพิ่มเมนู/route ใน `frontend/src/main.ts`
- **Acceptance**: ทุกฟีเจอร์ในตารางหัวข้อ 5 ทำงาน; sort ประกาศ `aria-sort` ถูกต้อง; keyboard nav ใช้ได้; confirm ขึ้นก่อนลบ; force refresh ข้าม cache ได้; เพิ่ม/ปรับเทสต์ใน `backend/tests/` ต่อยอดจาก `backend/tests/test_api_smoke.py` และรันด้วย `python -m pytest tests -q` ผ่าน
- **ประมาณ**: 1.5–2 วัน

### MERGE-005 — Parity test + เอกสาร + ตัด legacy
- เขียน parity test เทียบผล Python กับ JS เดิมในจุดสำคัญ; อัปเดต `README.md` (และ docs ที่เกี่ยวข้อง)
- ระบุสถานะ `updater` = legacy (ยังไม่ลบ)
- **Acceptance**: ชุดเทสต์ผ่านทั้งหมด; เอกสารตรงกับสภาพจริง; checklist หัวข้อ 6 ผ่านครบ
- **ประมาณ**: 0.5–1 วัน

**รวมประมาณ: 4–6.5 วันทำงาน**

---

## 8) ความเสี่ยง + Rollback

| ความเสี่ยง | ระดับ | ผลกระทบ | แนวทางลด/รับมือ | Rollback |
|-----------|-------|---------|-----------------|----------|
| พอร์ต JS→Python แล้ว behavior drift | สูง | ผลลัพธ์ไม่ตรงเดิม (เช่น sort/error code) | parity test ก่อน merge; คงค่า TTL/const ตามต้นทาง | ปิด endpoint `/api/maintenance/*` แล้วกลับไปใช้ updater เดิม |
| ลืม guard CSRF/Host | สูง | ช่องโหว่ security ลดลงจากเดิม | checklist หัวข้อ 6 + เทสต์บังคับข้อ 2,3,4 | revert commit MERGE-002 |
| Route ใหม่กลบ SPA fallback ใน `backend/main.py` | กลาง | SPA พัง/404 | ลงทะเบียน router ก่อน fallback + เทสต์เส้นทาง SPA | ย้าย/ลบ router registration |
| PowerShell timeout/hang | กลาง | ค้าง process | ใช้ `wait_for`+`kill` จาก `_run_powershell` ใน `backend/security/winapi.py` ทุกครั้ง | ปิดฟีเจอร์ที่เรียก PS |
| History เขียนชนกัน (SQLite) | กลาง | ข้อมูลเพี้ยน | ใช้ WAL + lock + retention เดิม (`backend/history.py`) | อ่านอย่างเดียว (disable write) |
| Port collision (relaunch 3100 เดิม) | ต่ำ | relaunch ผิดพอร์ต | ใช้กลไก Dashboard ไม่ใช้พอร์ต updater | ปิดฟีเจอร์ relaunch |
| Frontend a11y ถอยหลัง | ต่ำ | ผู้ใช้ keyboard ใช้งานไม่ได้ | เทสต์ sort/aria + keyboard nav | revert component |
| Frontend ไม่เคยส่ง `X-Admin-Token` มาก่อน | สูง | ถ้า gate endpoint ใหม่ด้วย token ผู้ใช้อาจเจอ 403 โดยไม่รู้สาเหตุ | ต้องมีข้อความบน UI อธิบายวิธีตั้ง/แนบ token + ใช้ค่า default ที่ปลอดภัย (ปฏิเสธเมื่อไม่ชัดเจน ไม่ fallback เปิดโล่ง) | ปิด gate เฉพาะ endpoint ที่ยังไม่ต้อง auth (เฉพาะ localhost) |
| ขอบเขตบาน (ทำ auto-update หลุดเข้ามา) | กลาง | ละเมิดนโยบายความปลอดภัย | Non-goals หัวข้อ 1 ห้าม auto-install | ปฏิเสธ PR ส่วนนั้น |

---

## 9) คำถามให้ผู้ใช้ตัดสิน (≤5 ข้อ)

1. **ยืนยันแนวทาง ADR A** (พอร์ตเป็น Python module) หรือต้องการพิจารณา B (iframe) อีกครั้ง?
2. **Endpoint ที่ไม่ต้อง auth** (`status` / `scan` / `history`) — ยอมรับได้ไหม หรือต้องการให้ต้องใช้ `X-Admin-Token` ทุก endpoint? **หมายเหตุ**: frontend store เดิม (`frontend/src/stores/security.ts`) **ไม่ได้แนบ `X-Admin-Token`** เลย → ต้องตัดสินใจว่า endpoint ใหม่ของ maintenance จะ **บังคับ token** หรือ **ใช้เฉพาะ localhost** (ถ้าบังคับ token ต้องแก้ store ใหม่ให้แนบ header + แจ้งผู้ใช้เมื่อ 403)
3. **ค่า TTL cache** — คงตาม updater (scanner 30s, system 60s) หรือปรับใหม่?
4. **`updater` เดิม** — เก็บเป็น legacy ไว้กี่รอบ release ก่อนลบ? หรือเก็บถาวรเพื่ออ้างอิง?
5. **ขอบเขต MERGE-002..005** — ลำดับ/การแบ่งงานโอเคไหม หรือต้องการรวม/แยกบาง step?

---

## Implementation notes & deviations

สถานะจริง: implemented (MERGE-001..006a + HARDEN-001/002) — parity test `tests/test_parity_updater.py`
ผ่าน และ `python -m pytest tests -q` = **92 passed**, `npm run build` = 124 modules

ความต่างจาก updater เดิม 8 ข้อ (เจตนา):

1. Error codes มี 22 รหัส (ต้นทางมี 22 ไม่ใช่ 25)
2. `open-devmgmt` ถูกตัดออก → ตอบ `UNSUPPORTED_ACTION`
3. `relaunch` ปิดถาวร → `501 RELAUNCH_DISABLED`
4. เพิ่ม `GET /api/maintenance/history` (updater เดิมไม่มี)
5. History เก็บใน SQLite ตาราง `maintenance_actions` (`HISTORY_DB`) ไม่ใช่ JSON
6. ~~Cleanup ไม่มี endpoint สรุปขนาดแยก~~ → **แก้ไขใน HARDEN-001**: คืน `GET /api/maintenance/clean/summary` (read-only, ไม่ลบไฟล์) เพื่อให้ผู้ใช้เห็นขนาดก่อนกดล้าง
7. **ชื่อฟิลด์ response เปลี่ยน**: `device` → `name`, `errorCode` → `problemCode` และเพิ่ม `class` (ค่าคงที่ `"driver"`) เพื่อเข้ากับรูปแบบ store ฝั่ง Vue
8. Export สร้าง CSV/JSON ในหน่วยความจำ (BOM + CRLF) — ไม่ใช้ `backend/exporters/` และไม่เขียนไฟล์ลงดิสก์

เพิ่มเติมจากงาน HARDEN-001/002 (หลังรีวิว MERGE-006):

9. **CSV formula injection** — ช่องที่ขึ้นต้นด้วย `=`, `+`, `-`, `@`, tab หรือ CR จะถูกเติม `'` ข้างหน้า
   ก่อน CSV escaping (`export._neutralize`) เพื่อกันการเปิดไฟล์ใน Excel แล้วรันสูตร
10. **`testserver` ไม่อยู่ใน production allowlist** — อนุญาตเฉพาะเมื่อ env `DASH_TEST_MODE=1`
    (`guards._allowed_hosts()` อ่าน env ทุกครั้งที่เรียก ไม่ผูกกับลำดับ import)
11. **UX หน้า `/maintenance`** — RAM/ดิสก์/ขนาดขยะแสดงเป็นหน่วยอ่านง่าย (`utils/format.ts`),
    มีส่วน "ขนาดขยะก่อนล้าง" จาก `clean/summary`, และข้อความ 403 แยกกรณี admin/host ชัดเจน

Mapping ไฟล์จริง:

| ส่วน | ไฟล์ |
|------|------|
| Guards (host allowlist / CSRF / admin) | `backend/maintenance/guards.py` |
| Error codes (22 รหัส) | `backend/maintenance/error_codes.py` |
| PowerShell runner | `backend/maintenance/powershell.py` |
| Scanner / system cache (30 s / 60 s) | `backend/maintenance/scanner.py`, `backend/maintenance/system.py` |
| Actions (`wu-scan`, `pnputil-scan`) | `backend/maintenance/actions.py` |
| Cleaner (`user-temp`, `windows-temp`, `recycle-bin`) | `backend/maintenance/cleaner.py` |
| History (SQLite `maintenance_actions`) | `backend/maintenance/history.py` |
| Export (CSV/JSON) | `backend/maintenance/export.py` |
| Router (8 endpoints) | `backend/maintenance/router.py` |
| Frontend route + หน้า | `frontend/src/main.ts`, `frontend/src/pages/Maintenance.vue` |
| Components | `frontend/src/components/maintenance/{MaintenanceTable,MaintenancePanel,MaintenanceHistory,MaintenanceAdminBanner}.vue` |
| Store | `frontend/src/stores/maintenance.ts` |

ข้อห้าม: โมดูลนี้ไม่ auto-install / auto-update เด็ดขาด — `wu-scan` และ
`pnputil-scan` เป็น read-only scan, `clean` ต้องส่ง `confirm: true`, และ `relaunch` ปิดถาวร
