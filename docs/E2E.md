# E2E Smoke Tests — Playwright

ชุดทดสอบ E2E แบบ smoke (`frontend/e2e/smoke.spec.ts`) รันกับแอปทั้งระบบจริง
(**backend FastAPI :8000** + **Vite dev server :5173**) ไม่ได้ mock ข้อมูล
ใช้ `@playwright/test` + Chromium project เดียว

## สิ่งที่ครอบคลุม

| เทสต์ | สิ่งที่ตรวจ |
|-------|-------------|
| `API smoke › /api/version` | `GET /api/version` คืน 200, `name` = `windy-smart-dashboard`, `version` เป็น semver, มี `port` |
| `Shell and dashboard › brand, nav links, primary zone` | เห็น brand "Windy Smart Dashboard", nav 3 ลิงก์ (Dashboard/Security/Maintenance), `[data-testid="primary-zone"]` มี `.card` ≥ 3, มี `secondary-zone` |
| `Shell and dashboard › layout toolbar` | `[data-testid="layout-toolbar"]` → กด `layout-toggle` แล้ว `layout-panel` + `layout-row-cpu` / `layout-row-gpu` ปรากฏ, กดซ้ำแล้ว panel หาย |
| `Theme toggle` | กด `[data-testid="theme-toggle"]` → `<html data-theme>` เปลี่ยน dark→light, ค่า `dash-theme` ถูกเก็บใน localStorage และคงอยู่หลัง reload |
| `Security page` | `/security` เห็น heading `Live Security Events` และ `Security Event History` |
| `Maintenance page` | `/maintenance` เห็น h2 `Maintenance`, heading `Scheduled reports`, `เปิดพร้อม Windows` (startup) และการ์ด `[data-testid="windows-update-card"]` ที่มี h3 "Windows Update & Pending Reboot", ปุ่ม `Scan now` และ badge `pending-reboot-badge` |

เทสต์ทั้งหมด **ไม่พึ่ง hardware sensor / สิทธิ์ Administrator** — ค่าที่อ่านไม่ได้จะแสดง N/A แต่โครงหน้า (heading, testid) ยังต้องมี

## สิ่งที่ต้องมีก่อนรัน

1. **Node 20+** และ `frontend/node_modules`
   ```powershell
   cd frontend
   npm ci
   ```
2. **Venv ที่ root ของโปรเจกต์** (`.venv`) พร้อม dependency ของ backend
   เพราะ `webServer` ของ Playwright เรียก `.venv\Scripts\python.exe backend\main.py`
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   ```
3. **Chromium ของ Playwright**
   ```powershell
   cd frontend
   npx playwright install chromium
   ```
   (ครั้งแรกจะโหลดจาก CDN ~130 MB; ถ้าเน็ตบล็อก ให้ติดตั้งด้วยเครื่องที่โหลดได้แล้วคัดลอก
   `%LOCALAPPDATA%\ms-playwright` ไปไว้ที่เครื่องปลายทาง)

## วิธีรัน

```powershell
cd frontend
npm run test:e2e          # = npx playwright test
npx playwright test --list   # ดูรายชื่อเทสต์ ไม่เปิด browser
npx playwright test --ui     # โหมด UI (debug แบบ interactive)
npx playwright test --headed --workers=1
npx playwright test -g "Theme toggle"   # รันเฉพาะเทสต์ที่ชื่อตรง
npm run test:e2e:report      # เปิด HTML report ล่าสุด
```

> ส่ง flag ผ่าน npm script ไม่ได้บน npm 12 (`npm run test:e2e -- --list` จะถูก npm กินเอง)
> — เรียก `npx playwright ...` ตรง ๆ เมื่อต้องใส่ flag

Playwright จะเปิด server ให้เอง 2 ตัวตาม `frontend/playwright.config.ts`:

| server | คำสั่ง | health URL | timeout |
|--------|--------|------------|---------|
| backend | `.venv\Scripts\python.exe backend\main.py` (cwd = repo root) | `http://127.0.0.1:8000/api/version` | 120 s |
| frontend | `npm run dev -- --host 127.0.0.1` (cwd = `frontend`) | `http://127.0.0.1:5173` | 120 s |

- `reuseExistingServer: !process.env.CI` → ในเครื่องถ้าเปิด backend/vite ค้างไว้อยู่แล้ว Playwright จะใช้ตัวเดิม
- **สังเกต `--host 127.0.0.1` ของ Vite**: บน Windows Vite ผูกกับ `localhost` = `::1` เท่านั้น
  ทำให้ `http://127.0.0.1:5173` ถูก refuse ถ้าไม่ pin IPv4 — ถ้ารัน `npm run dev` เองแบบไม่มี flag นี้
  ต้องหยุดก่อน (หรือเข้า `http://localhost:5173`) ไม่งั้น Playwright จะพยายามสตาร์ท server ใหม่แล้วชน `strictPort`

## Debug

- `trace: 'retain-on-failure'` + `screenshot: 'only-on-failure'` (เปิดเมื่อ fail เท่านั้น ไม่กินพื้นที่ตอนผ่าน)
- ดู trace: `npx playwright show-trace test-results/<test-folder>/trace.zip`
- HTML report: `frontend/playwright-report/index.html` (`npm run test:e2e:report`)
- เปิด logger ของ server ที่ Playwright spawn: ใส่ `DEBUG=pw:webserver` (เพิ่ม `stdout: 'pipe'` แล้วใน config)
- อยากเห็นเบราว์เซอร์จริง: `npx playwright test --headed --workers=1`

## Env ที่ใช้

| ตัวแปร | ค่า | ผล |
|--------|-----|-----|
| `CI` | `true` | `retries=1`, `workers=1`, `reuseExistingServer=false`, `forbidOnly=true`, reporter เพิ่ม HTML |
| `DASH_PORT` | default `8000` | port ของ backend — ถ้าเปลี่ยน ต้องแก้ `baseURL` ของ proxy ฝั่ง Vite ด้วย (vite.config.ts fix ที่ 8000) |
| `DASH_HOST` | default `127.0.0.1` | bind address ของ backend |
| `DASH_TEST_MODE` | `1` | ปลดล็อก `testserver` ใน allowlist ของ maintenance guard — **ไม่จำเป็น** สำหรับ smoke ชุดนี้ ใช้เฉพาะเวลาเขียนเทสต์ที่ยิง action ของ maintenance |

## CI

job `e2e-smoke` (`.github/workflows/ci.yml`, `windows-latest`) ทำตามลำดับ:

1. checkout + setup Python 3.12 (cache pip → `backend/requirements*.txt`)
2. `python -m venv .venv` แล้วติดตั้ง `backend/requirements.txt` ลง venv
   (เพื่อให้คำสั่งใน `playwright.config.ts` ใช้ path เดียวกับในเครื่อง)
3. setup Node 20 (cache npm → `frontend/package-lock.json`) + `npm ci`
4. `npx playwright install --with-deps chromium`
5. `npm run test:e2e` (env `CI=true`, `DASH_PORT=8000`)
6. อัปโหลด artifact `playwright-report` (+ `test-results`) **เมื่อ fail เท่านั้น**

## ข้อจำกัดที่รู้อยู่

- **ไม่มี hardware sensor ใน CI** — LibreHardwareMonitor ต้องรันแบบ Administrator เครื่อง runner ไม่มี
  ค่า temp/power/GPU จะเป็น `None`/N/A; เทสต์จึงไม่ assert ค่าตัวเลขจาก sensor
- **API ที่ต้องสิทธิ์ admin** (`/api/security/events`, reports, maintenance actions) ไม่ถูกเรียกในชุด smoke
  เพราะขึ้นกับ quirk ของสิทธิ์บน runner
- WebSocket `/ws/metrics`, `/ws/security` ต้องมีจริงเพื่อให้หน้าโหลด แต่เทสต์ตรวจเฉพาะ DOM ที่ render ออกมา
- เทสต์ theme พึ่ง `localStorage` (context ใหม่ทุกเทสต์) — ไม่ปนกันข้ามเทสต์
- `frontend/playwright-report/` และ `frontend/test-results/` เป็น artifact ที่เกิดตอนรัน
  ควรอยู่ใน `.gitignore` (ยังไม่ถูกเพิ่มในงานนี้เพื่อไม่แตะไฟล์นอกขอบเขต)
