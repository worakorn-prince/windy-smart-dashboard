# Windy Smart Dashboard

> 🇬🇧 English: [README.md](README.md)

แดชบอร์ดเว็บแบบเรียลไทม์สำหรับตรวจสอบสถานะเครื่องคอมพิวเตอร์ของคุณเอง (CPU, RAM,
ดิสก์, เครือข่าย, โปรเซสที่ใช้ทรัพยากรสูงสุด, ข้อมูลระบบ, วัดความเร็วอินเทอร์เน็ต)
พร้อมด้วย **โมดูลตรวจสอบความปลอดภัย (security audit)** ที่ค้นหาจุดอ่อนบนเครื่อง:
พอร์ตที่เปิดอยู่, โปรเซสที่กำลังlisten, สถานะ Windows Defender, การล็อกอินที่ล้มเหลว,
การถูกเปลี่ยนเส้นทางในไฟล์ hosts, เบาะแสการโจมตี ARP spoofing, การเชื่อมต่อออก
(outbound) ที่น่าสงสัย และอื่น ๆ

พัฒนาด้วย FastAPI (Python 3.12) + Vue 3 / TypeScript / Vite

> ⚠️ แดชบอร์ดผูกกับ `127.0.0.1` เท่านั้น — เข้าใช้งานได้จากเครื่องนี้เครื่องเดียว
> ไม่เปิดให้เครือข่ายเข้าถึง ซึ่งเป็นการตั้งใจและเป็นฟีเจอร์ด้านความปลอดภัย

## 🪟 ระบบปฏิบัติการที่รองรับและข้อกำหนด

**ใช้ได้เฉพาะ Windows 10 / 11 เท่านั้น** โปรเจกต์นี้ไม่สามารถย้ายไปใช้บนระบบ
ปฏิบัติการอื่นได้ และไม่ได้ถูกทดสอบ (และไม่คาดว่าจะรันได้) บน Linux หรือ macOS
เนื่องจากพึ่งพาส่วนที่เฉพาะเจาะจงของ Windows ดังนี้:

- สคริปต์ตัวเรียกแบบ PowerShell (`run.ps1` / `run.bat`)
- **LibreHardwareMonitorLib** (in-process COM) สำหรับอุณหภูมิ CPU/GPU/ดิสก์
  และความเร็วพัดลม
- **Windows Firewall** (กฎบล็อก/ปลดบล็อก), สถานะ **Windows Defender**,
  และ **Security event log** (การล็อกอินล้มเหลว)
- การแจ้งเตือนแบบ **Native Windows Toast**
- `clr_loader` / `pythonnet` สำหรับโหลดไลบรารีฮาร์ดแวร์ `.NET`

บน Windows ส่วน backend (FastAPI + psutil) และ frontend (Vue/Vite) เป็นแค่
Python/Node ธรรมดา ซึ่งสามารถรันได้ทุกที่ แต่การเชื่อมต่อกับแพลตฟอร์มข้างต้น
เป็นของ Windows เท่านั้น จึงสรุปได้ว่าแอปทั้งหมดรันได้บน Windows เท่านั้น

### เงื่อนไขเบื้องต้น
- Python 3.10+ อยู่ใน `PATH`
- Node.js 18+ อยู่ใน `PATH`
- (ไม่บังคับ, สำหรับเซนเซอร์) LibreHardwareMonitor — `winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor`
- (สำหรับฟีเจอร์ความปลอดภัยเต็มรูปแบบ) รันในโหมด **Administrator**

---

## ✨ ฟีเจอร์

### แดชบอร์ด
- เปอร์เซ็นต์การใช้งาน CPU (รวม + แยกตามคอร์) และความถี่
- หน่วยความจำ (RAM + swap)
- การใช้งานดิสก์แยกตาม partition + อัตราอ่าน/เขียน
- การ์ดเครือข่าย (Network interfaces) + อัตรา upload/download แบบสด
- โปรเซส 10 อันดับแรก (เรียงลำดับตาม CPU/RAM ได้)
- ข้อมูลระบบ (hostname, OS, หน่วยประมวลผล, uptime, เวลาเปิดเครื่อง)
- วัดความเร็วอินเทอร์เน็ต **แบบกดปุ่ม** (ใช้แบนด์วิดท์ ไม่ได้โพลล์ตลอด)
  ต่อกับ endpoints ฟรีของ Cloudflare `speed.cloudflare.com` (ไม่ต้องมี API key
  ไม่มี rate limit)
- วัดความหน่วง (latency) แบบ ping ไปยังเป้าหมายที่กำหนดได้
- **ประวัติ metrics** — ทุกค่าถูกสุ่มเก็บลง SQLite ท้องถิ่นทุก 10 วินาที
  และแสดงเป็นกราฟในช่วง **1 ชม. / 6 ชม. / 24 ชม.** รวมถึงอุณหภูมิ
  (CPU/GPU/ดิสก์) และการใช้พลังงาน (CPU W / GPU W) มีปุ่มสลับซีรีส์และแกน Y หลายแกน
- **การใช้พลังงานแบบสด** — การ์ดแยกแสดงกำลังไฟฟ้ารวม ณ ปัจจุบัน (CPU + GPU)
  พร้อมแยกตามส่วนประกอบและตามการ์ด GPU แต่ละตัว

### ความปลอดภัย
- **ตรวจสอบแบบ on-demand** — สร้างรายงานที่มีการให้คะแนนความเสี่ยง (risk score)
- **สตรีมเหตุการณ์สด** — ดันเหตุการณ์ผ่าน WebSocket (พอร์ตใหม่, การเชื่อมต่อออก
  ไปประเทศเสี่ยงหรือ Tor exit node, การล็อกอินล้มเหลว, การเปลี่ยนสถานะ Defender)
- **การให้คะแนนความเสี่ยง** (low / medium / high / critical) จากฮิวริสติก 10+
  ตัว (เช่น การเปิด RDP, listener ที่ไม่ได้เซ็นชื่อ, Defender ปิด ฯลฯ)
- **ปุ่มดำเนินการ** — ฆ่าโปรเซสตาม PID, บล็อก IP ผ่าน Windows Firewall,
  ดูรายการและเลิกบล็อกกฎ
- **ตรวจสอบ geoIP** ผ่าน ip-api.com พร้อมแคชที่รองรับ rate limit
- **ตรวจจับ Tor exit node** (รีเฟรชวันละครั้ง)
- **รายชื่อประเทศเสี่ยง (watchlist)** — แก้ไขได้ใน UI และถูกบันทึกไว้
- **ส่งออกรายงานการตรวจสอบ** เป็น PDF / HTML / JSON

### การแจ้งเตือน (Alerts)
- **การแจ้งเตือนตามเกณฑ์** พร้อมการยืนยันว่าผิดเกณฑ์ต่อเนื่องกันหลายรอบ
  (ป้องกันแจ้งเตือนหลอกจากการกระชากชั่วคราว) และมี cooldown ต่อกฎ:
  อุณหภูมิ CPU/GPU, การใช้งาน RAM, ระดับดิสก์ที่เต็ม
- **การแจ้งเตือนแบบ Toast บน Windows** (ไม่ต้องติดตั้งเพิ่ม) พร้อมสแต็ก toast
  ในแอปบนทุกหน้า

> ℹ️ ฟีเจอร์ความปลอดภัยบางส่วนต้องรันในโหมด Administrator:
> อ่าน Security event log (การล็อกอินล้มเหลว), สร้างกฎบล็อก firewall,
> และฆ่าโปรเซสของผู้ใช้อื่น UI จะแสดงแบนเนอร์เมื่อเป็นกรณีนี้
> ส่วนฟีเจอร์ที่ไม่ใช้ admin ยังคงทำงานได้

---

## 🌡️ อุณหภูมิฮาร์ดแวร์ (CPU/GPU/ดิสก์/พัดลม)

Windows ไม่เปิดเผยเซนเซอร์ฮาร์ดแวร์ดิบให้โปรแกรมปกติอ่านได้ แดชบอร์ดนี้ใช้วิธี
อ่านผ่าน **LibreHardwareMonitorLib** ที่โหลดใน-process โดยตรง (ไม่ต้องเปิดแอป GUI
ค้างไว้)

การเตรียมการ:

```powershell
# ติดตั้งครั้งเดียว
winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor

# แค่รัน — run.ps1 จะยกสิทธิ์เป็น Administrator ให้อัตโนมัติ (มี UAC ครั้งเดียว) เพื่ออ่านเซนเซอร์
.\run.ps1
```

หมายเหตุ:
- หากไม่มีสิทธิ์ admin ส่วนอื่นยังคงทำงาน — การ์ดต่าง ๆ จะแสดง
  "Temperature unavailable"
- `start-sensors.ps1` สามารถเปิด/ตรวจสอบอินสแตนซ์ LibreHardwareMonitor แบบ
  standalone ได้ หากคุณต้องการใช้เส้นทาง GUI
- AMD iGPU (Vega) ไม่มี diode วัดอุณหภูมิของตัวเองในที่นี้ — แดชบอร์ดจะใช้
  อุณหภูมิ GFX ของ CPU แทน

---

## 📂 โครงสร้างโปรเจกต์

```
Dashboard/
├── backend/
│   ├── main.py              FastAPI app, จุดเชื่อมต่อ WebSocket, routes
│   ├── config.py            การตั้งค่า + ช่วงเวลา (intervals)
│   ├── metrics.py           metrics ระบบจาก psutil
│   ├── history.py           ประวัติ metrics (SQLite: ตัวสุ่มตัวอย่าง + query)
│   ├── alerts.py            การแจ้งเตือนตามเกณฑ์ + ตัวส่ง Windows Toast
│   ├── sensors_lhm.py       การเชื่อมต่อ LibreHardwareMonitorLib (อุณหภูมิ/พัดลม)
│   ├── speedtest_worker.py  วัดความเร็วอินเทอร์เน็ตแบบ on-demand
│   ├── tests/               ชุดทดสอบ pytest (alerts, history, parsers)
│   ├── requirements.txt
│   ├── security/
│   │   ├── audit.py         ตรวจสอบแบบ on-demand + กฎการหาข้อสรุป (findings)
│   │   ├── monitor.py       ตัวโพลล์พื้นหลังแบบ async → เหตุการณ์ WS
│   │   ├── actions.py       ฆ่าโปรเซส / บล็อก IP / ดูรายการกฎ
│   │   ├── findings.py      คลาส Finding + ให้คะแนนความเสี่ยง
│   │   ├── geoip.py         ดูข้อมูล ip-api.com + รายการ Tor exit
│   │   └── winapi.py        ตัวห่อหุ้ม PowerShell (Defender, logins ฯลฯ)
│   ├── exporters/
│   │   └── __init__.py      ตัวเขียนรายงาน PDF / HTML / JSON
│   └── .cache/              แคช geoip, tor exits, รายงานที่สร้างขึ้น
└── frontend/
    ├── package.json
    ├── vite.config.ts       proxy /api และ /ws → 127.0.0.1:8000
    ├── tsconfig.json
    └── src/
        ├── main.ts          เริ่มแอป + router
        ├── App.vue          ไลเอาต์ + สไตล์全局
        ├── pages/
        │   ├── Dashboard.vue
        │   └── Security.vue
        ├── components/
        │   ├── dashboard/   CpuCard, RamCard, DiskCard, NetworkCard,
        │   │                 GpuCard, AdaptersCard, HistoryCard,
        │   │                 ProcessesCard, SystemCard, SpeedtestCard
        │   └── security/    AuditCard, PortsCard, ConnectionsCard,
        │                     DefenderCard, FailedLoginsCard,
        │                     SecurityEventsLog, SettingsPanel,
        │                     BlockedRulesCard
        ├── composables/      useWebSocket, ฟังก์ชันจัดรูปแบบ (format)
        ├── directives/       autoTip (tooltip เมื่อเอาเมาส์ชี้ข้อความที่ถูกตัด)
        └── stores/          metrics.ts, history.ts, security.ts (Pinia)
```

---

## 📈 ประวัติ metrics

ตัวสุ่มตัวอย่าง (sampler) เบื้องหลังจะเขียนแถวเดียวของ metrics สเกลาร์ราคาถูก
ลง `backend/.cache/history.db` (SQLite, โหมด WAL) ทุก `HISTORY_SAMPLE_INTERVAL`
วินาที การ์ด **History** บนแดชบอร์ดจะ query ค่าเฉลี่ยแบบถัง (bucketed)
(~360 จุดสูงสุด) สำหรับช่วงที่เลือก

- ช่วงเวลา: `1h` (ถัง 10 วินาที), `6h` (60 วินาที), `24h` (240 วินาที)
- ซีรีส์: CPU/RAM/swap %, อุณหภูมิสูงสุด CPU/GPU/ดิสก์, การใช้พลังงาน CPU W / GPU W,
  ทราฟฟิกเครือข่ายและดิสก์ (MB/s)
- แถวที่เก่ากว่า `HISTORY_RETENTION_HOURS` จะถูกลบอัตโนมัติ
  (ใช้พื้นที่ดิสก์ ~<1 MB/วัน)
- อุณหภูมิ/พัดลม เป็น `NULL` เมื่อไม่ได้รันแบบยกระดับ (elevated) — กราฟจะแสดง
  ช่องว่างพร้อมคำใบ้
- บนโน้ตบุ๊ก AMD หลายรุ่น พัดลมจะหยุดหมุนสนิทตอนว่าง (zero-RPM cooling)
  ซีรีส์พัดลมจะว่างจนกว่าจะมีโหลดให้หมุน

---

## 🚀 เริ่มต้นอย่างรวดเร็ว (สคริปต์เดียว)

```powershell
# จาก shell ปกติ — ติดตั้ง dependencies, build frontend, เริ่ม server
# (รันจาก repo root คือโฟลเดอร์ที่มี run.ps1 อยู่)
.\run.ps1
```

เปิด **http://127.0.0.1:8000** ในเบราว์เซอร์

ตัวเลือกเพิ่มเติม:

| Flag        | ทำอะไร                                        |
|-------------|-----------------------------------------------|
| `-Dev`      | รัน backend (8000) และ frontend HMR (5173) ในสองหน้าต่าง |
| `-Install`  | ติดตั้ง/ติดตั้งใหม่ dependencies ฝั่ง backend + frontend |
| `-Clean`    | ล้าง `backend\.cache` และ `__pycache__` ของ Python (คง deps ไว้) |

สำหรับฟีเจอร์ความปลอดภัยเต็มรูปแบบ (ล็อกอินล้มเหลว, กฎบล็อก firewall,
การฆ่าโปรเซสที่มีสิทธิ์) `run.ps1` จะยกสิทธิ์รันใหม่เป็น Administrator ให้อัตโนมัติ
(มี UAC ครั้งเดียว) — แค่รัน `.\run.ps1` ตามปกติ

### การติดตั้งเอง (ทางเลือก)

หากต้องการรันทีละขั้นตอนเอง:

```powershell
# 1. ติดตั้ง dependencies ฝั่ง backend
cd backend
python -m pip install -r requirements.txt

# 2. build frontend (โหมด production)
cd ..\frontend
npm install
npm run build

# 3. รัน server
cd ..\backend
python main.py
```

---

## 🔧 โหมดพัฒนา (hot reload)

ระหว่างการพัฒนามีสองโปรเซส:

```powershell
# Terminal 1 — backend
cd backend
python main.py

# Terminal 2 — frontend แบบ HMR
cd ..\frontend
npm run dev
```

เปิด **http://localhost:5173** — Vite จะ proxy `/api` และ `/ws` ไปยัง
`127.0.0.1:8000` ให้อัตโนมัติ

---

## 🔌 อ้างอิง API

| Method | Path                          | วัตถุประสงค์                              |
|--------|-------------------------------|-------------------------------------------|
| GET    | `/` (และทุกพาธที่ไม่ใช่ API)  | SPA frontend (เสิร์ฟจาก `frontend/dist`)  |
| GET    | `/api/system`                 | สแนปชอตระบบเริ่มต้น                       |
| GET    | `/api/history?range=1h\|6h\|24h`| ประวัติ metrics แบบถัง (~360 จุด)      |
| POST   | `/api/speedtest`              | ทริกเกอร์วัดความเร็วอินเทอร์เน็ต         |
| GET    | `/api/security/suspicious`    | ดูรหัสประเทศที่ถูกแฟล็กอยู่               |
| PUT    | `/api/security/suspicious`    | ตั้งค่ารายชื่อประเทศเสี่ยงใหม่           |
| POST   | `/api/security/audit`         | รันการตรวจสอบแบบ on-demand; คืนรายงานเต็ม |
| POST   | `/api/security/kill`          | ฆ่าโปรเซสตาม PID (body: `{pid}`)         |
| POST   | `/api/security/block`         | เพิ่มกฎบล็อก Windows firewall (`{ip}`)    |
| POST   | `/api/security/unblock`       | ลบกฎบล็อก (`{rule_name}`)                |
| GET    | `/api/security/blocked`       | ดูกฎ `WindySmartDashboard_block_*` ทั้งหมด |
| POST   | `/api/security/export`        | ส่งออกรายงานการตรวจสอบ (body: `{fmt, report}`) |
| WS     | `/ws/metrics`                 | ดัน metrics สด (1 Hz)                     |
| WS     | `/ws/security`                | ดันเหตุการณ์ความปลอดภัยสด                |

---

## ⚙️ การตั้งค่า (Configuration)

การตั้งค่าอยู่ใน `backend/config.py` และสามารถแปลงผ่าน environment variables ได้:

| Variable                   | ค่าเริ่มต้น | คำอธิบาย                              |
|----------------------------|---------|------------------------------------------|
| `DASH_HOST`                | 127.0.0.1 | โฮสต์ที่ผูก (คงไว้ที่ `127.0.0.1` เพื่อความปลอดภัย) |
| `DASH_PORT`                | 8000    | พอร์ตที่ผูก                                |
| `DASH_METRICS_INTERVAL`    | 1.0     | ช่วงเวลาดันข้อมูล (วินาที)                 |
| `DASH_PROCESS_INTERVAL`    | 3.0     | ช่วงเวลาดันโปรเซส Top-N (วินาที)          |
| `DASH_PING_TARGET`         | 1.1.1.1 | เป้าหมายสำหรับวัดความหน่วงแบบ TCP connect |
| `DASH_HISTORY_INTERVAL`    | 10.0    | ช่วงเวลาสุ่มตัวอย่างประวัติ (วินาที)      |
| `DASH_HISTORY_RETENTION`   | 24      | ชั่วโมงของประวัติที่เก็บไว้                |
| `DASH_HISTORY_MAX_POINTS`  | 360     | จำนวนจุดสูงสุดต่อ `/api/history`          |
| `DASH_ALERTS`              | 1       | ตั้งเป็น `0` เพื่อปิดการแจ้งเตือน         |
| `DASH_ALERT_CPU_TEMP`      | 85      | เกณฑ์อุณหภูมิ CPU แจ้งเตือน (°C)          |
| `DASH_ALERT_GPU_TEMP`      | 85      | เกณฑ์อุณหภูมิ GPU แจ้งเตือน (°C)          |
| `DASH_ALERT_RAM_PCT`       | 95      | เกณฑ์การใช้งาน RAM แจ้งเตือน (%)          |
| `DASH_ALERT_DISK_PCT`      | 90      | เกณฑ์การใช้งานดิสก์แจ้งเตือน (%)          |
| `DASH_ALERT_SUSTAINED`     | 3       | จำนวนรอบที่ผิดเกณฑ์ต่อเนื่องก่อนแจ้งเตือน  |
| `DASH_ALERT_COOLDOWN`      | 300     | วินาทีระหว่างการแจ้งเตือนซ้ำต่อกฎ         |

---

## 🧪 การทดสอบ (Testing)

ชุดทดสอบฝั่ง backend (pytest) ครอบคลุมเครื่องยนต์แจ้งเตือน (alert engine),
การทำถังประวัติ (history bucketing), และตัวช่วยแปลง (parsing helpers):

```powershell
cd backend
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

ตรวจสอบโค้ด (lint) ฝั่ง backend ได้ตลอดเวลาด้วย:

```powershell
cd backend
.\.venv\Scripts\ruff.exe check .
```

---

## 🛡️ ขอบเขตและข้อจำกัด

แดชบอร์ดนี้ตรวจสอบเฉพาะ **เครื่อง本地 (local machine)** เท่านั้น ไม่ได้สแกน
โฮสต์อื่น เจาะระบบเครือข่าย จับข้อมูลรับรอง (credential) หรือทำการโจมตีใด ๆ
โมดูลความปลอดภัยเป็นเครื่องมือตรวจสอบ/ติดตามสดเชิงรับ (defensive) สำหรับการ
ตรวจเช็คตัวเอง ปุ่มดำเนินการ (ฆ่าโปรเซส, บล็อก IP) ทำงานบนเครื่องนี้เท่านั้น

บน Windows 10/11 ที่ไม่ได้รันในโหมด Administrator ฟีเจอร์เหล่านี้จะถูกจำกัด:

- ประวัติการล็อกอินล้มเหลว (Security log ต้องการ admin)
- สร้าง/ลบกฎบล็อก firewall
- ฆ่าโปรเซสที่เป็นของผู้ใช้อื่น

ฟีเจอร์อื่น ๆ (metrics, การตรวจสอบ, geoIP, การตรวจจับ TOR) ทำงานได้โดยไม่ต้อง
ยกระดับสิทธิ์ UI จะแสดงแบนเนอร์ให้ทราบ

---

## 📓 หมายเหตุ

- ฟรีเทียร์ ip-api.com ให้ ~40 req/นาที; การ lookup ถูกแคช 10 นาทีต่อ IP
  และรองรับ rate limit อย่างนุ่มนวล
- รายการ Tor exit จะรีเฟรชวันละครั้งจาก
  `https://check.torproject.org/torbulkexitlist` และแคชไว้ในเครื่อง
- รายงานจะถูกบันทึกลง `backend/.cache/reports/` ด้วยเมื่อส่งออก

---

## 📜 สัญญาอนุญาต (License)

เผยแพร่ภายใต้ [สัญญาอนุญาต MIT](LICENSE) ใช้ได้ด้วยความเสี่ยงของคุณเอง
อย่าใช้งานโมดูลตรวจสอบความปลอดภัยกับระบบที่คุณไม่ได้เป็นเจ้าของ
