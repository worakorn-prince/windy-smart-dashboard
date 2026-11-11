# UI Design System — "pulse" dark system-monitor

เอกสารนี้อธิบาย design system ของ Windy Smart Dashboard หลังงาน redesign (UI-401…UI-406)
ใช้เป็น reference เวลาสร้างหน้า/คอมโพเนนต์ใหม่ เพื่อไม่ให้สี ระยะ หรือโครงสร้างหลุดจากธีมหลัก

**Reference image**: `C:\Users\Prince\Desktop\0010.PNG` (pulse system monitor — dark navy + cyan/lime/violet)
**Scope**: frontend เท่านั้น (Vue 3 + TypeScript + Vite) — backend ไม่เกี่ยวข้อง

## 1. แนวทางภาพรวม

- **Pulse dark system-monitor** — พื้นหลัง navy-black เข้ม (`--bg: #070b14`) การ์ดลอยขึ้นมาด้วย
  `--panel` + เส้นขอบบาง `--border` และมี glow สี cyan ตอน hover
- ตัวเลขทุกตัวใช้ `--font-mono` + `font-variant-numeric: tabular-nums` เพื่อให้อ่านแนวตั้งแล้วตรงกัน
- สี accent 4 ตัวใช้แยกหมวด metric: cyan = CPU, lime = RAM, violet = GPU, amber = POWER
- ยังคงรองรับ light theme ผ่าน `:root[data-theme='light']` (สลับด้วยปุ่ม `data-testid="theme-toggle"`)

## 2. Design tokens

ไฟล์จริง: `frontend/src/styles/tokens.css` (ค่าด้านล่างคัดลอกมาจากไฟล์นี้โดยตรง)

| Token | Dark (`:root`) | Light (`:root[data-theme='light']`) | ใช้กับ |
|---|---|---|---|
| `--bg` | `#070b14` | `#f3f6fb` | พื้นหลังหน้า |
| `--bg-elev` | `#0b111d` | `#ffffff` | sidebar / surface ที่ยกขึ้น |
| `--panel` | `#0e1524` | `#ffffff` | พื้นการ์ด |
| `--panel-2` | `#131c2e` | `#e9eef7` | แถวใน, hover, chip |
| `--border` | `#1b2740` | `#d5dded` | เส้นขอบการ์ด |
| `--border-strong` | `#24334f` | `#bcc8de` | เส้นขอบเน้น |
| `--text` | `#e8eef8` | `#0d1526` | ข้อความหลัก |
| `--text-dim` | `#93a3bd` | `#47536b` | ข้อความรอง |
| `--muted` | `#64748b` | `#64748b` | ข้อความระดับสาม / axis label |
| `--accent` | `#22d3ee` | `#0891b2` | cyan — accent หลัก, nav active, CPU |
| `--accent-2` | `#a3e635` | `#4d7c0f` | lime — RAM / ค่าบวก |
| `--accent-3` | `#a78bfa` | `#6d28d9` | violet — GPU |
| `--accent-4` | `#fbbf24` | `#b45309` | amber — POWER |
| `--good` | `#4ade80` | `#16a34a` | สถานะดี |
| `--warn` | `#fbbf24` | `#b45309` | สถานะเตือน |
| `--bad` | `#f87171` | `#dc2626` | สถานะผิดปกติ |
| `--crit` | `#ef4444` | `#b91c1c` | สถานะวิกฤต |
| `--grid-line` | `#16203a` | `#dbe3f0` | เส้นกริดกราฟ |
| `--info` | `#38bdf8` | `#0369a1` | ข้อมูลทั่วไป |
| `--radius-card` | `10px` | `10px` | มุมการ์ด |
| `--radius-ctl` | `8px` | `8px` | มุมปุ่ม/คอนโทรล |
| `--radius-pill` | `999px` | `999px` | pill / badge / chip |
| `--sidebar-w` | `200px` | `200px` | ความกว้าง sidebar |
| `--font-sans` | `'Inter', 'Segoe UI', system-ui, …` | เหมือนกัน | ข้อความทั่วไป |
| `--font-mono` | `'JetBrains Mono', ui-monospace, …` | เหมือนกัน | ตัวเลข / label |
| `--accent-soft` | `rgba(34, 211, 238, .06)` | `rgba(8, 145, 178, .07)` | พื้นหลัง hover |
| `--on-accent` | `#04121a` | `#04121a` | ตัวอักษรบนพื้น `--accent` |
| `--on-warn` | `#1a1203` | `#1a1203` | ตัวอักษรบนพื้น `--accent-4` |
| `--accent-glow` | `rgba(34, 211, 238, .18)` | `rgba(8, 145, 178, .22)` | เงา glow ตอน hover |

Typography: body ใช้ `--font-sans` 14px / line-height 1.45, ตัวเลขและ label ใช้ `--font-mono`
Radius: การ์ด 10px, คอนโทรล 8px, pill 999px
Glow: `box-shadow: 0 0 0 1px var(--accent-glow)` เมื่อ hover การ์ด

## 3. App shell

ไฟล์จริง: `frontend/src/App.vue`

```
┌──────────┬────────────────────────────────────────────┐
│ sidebar  │  topbar (actions + theme toggle)           │
│  200px   ├────────────────────────────────────────────┤
│  fixed   │  content  (padding 20px)                   │
└──────────┴────────────────────────────────────────────┘
```

- `aside.sidebar` (`data-testid="sidebar"`) — fixed ซ้าย, กว้าง `var(--sidebar-w)` = 200px, พื้น `--bg-elev`
  - brand block: `<RouterLink class="brand" aria-label="Windy Smart Dashboard">` + `brand-mark` gradient cyan→violet
  - nav group `MONITOR` (`data-testid="side-nav"`): Dashboard / Security / Maintenance / Viewer
  - nav group `SYSTEM` (`data-testid="side-nav-system"`): การแจ้งเตือน + badge จำนวน (`data-testid="side-nav-alert-count"`)
  - device card (`data-testid="device-card"`) ปักล่างด้วย `margin-top: auto`: hostname, OS, Python + จุดเขียว pulse
- `div.app-main` — `topbar` (sticky, `margin-left: var(--sidebar-w)`) + `main.content` (padding 20px, margin-left เท่ากัน)
- Breakpoints
  - `@media (max-width: 900px)` → `.app-shell { --sidebar-w: 64px }`, sidebar แคบลง, ซ่อน brand text /
    nav group label / device text, จัด nav ให้อยู่กลาง
  - `@media (max-width: 640px)` → `.grid` เป็น 1 คอลัมน์, ลด padding การ์ด/topbar/content, ตาราง font 11px

## 4. Components ใหม่ (dashboard)

### `StatTile.vue` — `frontend/src/components/dashboard/StatTile.vue`

การ์ด KPI ใบเดียว: accent bar + icon + label, sparkline SVG (มุมขวาบน), ตัวเลขใหญ่ + หน่วย, subtitle, footer (delta + caption)

| Prop | Type | Default | ความหมาย |
|---|---|---|---|
| `label` | `string` | required | ชื่อ metric (ใช้สร้าง `data-testid="stat-tile-{label.toLowerCase()}"`) |
| `value` | `string` | required | ค่าที่จัดรูปแบบแล้ว (เช่น `'68'`, `'24.0'`, `'—'`) |
| `unit` | `string?` | `''` | หน่วยต่อท้ายค่า (`%`, `GB`, `W`) — ไม่แสดงเมื่อว่าง |
| `accent` | `'cyan' \| 'violet' \| 'lime' \| 'amber'` | `'cyan'` | สี accent ของ tile |
| `icon` | `string?` | `''` | glyph/emoji เล็กหน้าชื่อ metric |
| `delta` | `string \| null` | `null` | ข้อความ delta (เช่น `'+8 จุดเดิมสูงสุด'`) |
| `deltaTone` | `'good' \| 'bad' \| 'flat'` | `'flat'` | โทนสีของ delta |
| `caption` | `string?` | `''` | ข้อความท้ายการ์ด (เช่น `'อัปเดตล่าสุด 1 นาทีที่แล้ว'`) |
| `subtitle` | `string?` | `''` | บรรทัดรองใต้ตัวเลข (ชื่อ CPU/GPU, `'จากทั้งหมด 32 GB · ใช้ 75%'`) |
| `spark` | `number[]?` | `[]` | ชุดข้อมูล sparkline — วาดเมื่อมี ≥ 2 จุด |

หมายเหตุ: sparkline เป็น SVG เขียนเอง (`viewBox="0 0 100 32"`) ใช้ `useId()` สร้าง gradient id
จึงไม่ต้อง assert id ใน test — assert แค่ว่ามี `svg`

### `StatRow.vue` — `frontend/src/components/dashboard/StatRow.vue`

แถว KPI 4 ใบ อ่านค่าจาก `useMetricsStore()` โดยตรง (ไม่รับ prop)

- CPU: `store.cpu.overall` → `.toFixed(0)` + `%`, accent cyan, spark = `store.cpuHistory`
- GPU: ค่าเฉลี่ย `store.gpu.gpus[].gpu_usage_percent` → `.toFixed(0)` + `%`, accent violet
- RAM: `store.ram.used` → `.toFixed(1)` + `GB`, accent lime, spark = `store.ramHistory`
- POWER: `store.cpu.power_watts` + ผลรวม `store.gpu.gpus[].power_draw_watts` → `.toFixed(0)` + `W`, accent amber
- ค่าเป็น `null` → แสดง `'—'` ไม่มีหน่วยและไม่มี sparkline
- grid: 4 คอลัมน์ → 2 คอลัมน์ (`max-width: 1100px`) → 1 คอลัมน์ (`max-width: 640px`)
- root: `data-testid="stat-row"`

## 5. Palette ของกราฟ (HistoryCard)

ไฟล์จริง: `frontend/src/components/dashboard/HistoryCard.vue` (`SERIES_DEFS`)

| Series | Label | สี |
|---|---|---|
| `cpu_pct` | CPU % | `#22d3ee` cyan |
| `ram_pct` | RAM % | `#a3e635` lime |
| `swap_pct` | Swap % | `#4ade80` green |
| `cpu_temp` | CPU °C | `#fbbf24` amber |
| `gpu_temp` | GPU °C | `#a78bfa` violet |
| `disk_temp_max` | Disk °C | `#f97316` orange |
| `cpu_power_w` | CPU W | `#f472b6` pink |
| `gpu_power_w` | GPU W | `#fb923c` orange-light |
| `net_recv_bps` | Net ↓ MB/s | `#38bdf8` sky |
| `net_sent_bps` | Net ↑ MB/s | `#818cf8` indigo |
| `disk_read_bps` | Disk R MB/s | `#34d399` emerald |
| `disk_write_bps` | Disk W MB/s | `#f87171` red |

Range tabs: `5m` (`5 นาที`), `1h` (`1 ชม.`), `6h` (`6 ชม.`), `24h` (`24 ชม.`)
Area fill ใช้ gradient จากสีของ series (alpha 0.18 → 0), grid/axis อ่านจาก `--grid-line` / `--muted`
ผ่าน `getComputedStyle` ตอน `render()` เพื่อให้ตาม theme ที่สลับอยู่ (palette ของเส้นเป็นค่าคงที่ใน `SERIES_DEFS`)

## 6. กฎการใช้งาน

1. **ห้าม hard-code สี** ในคอมโพเนนต์/หน้าใหม่ — ใช้ `var(--…)` จาก `tokens.css` เท่านั้น
   (ยกเว้น palette ของกราฟที่ประกาศเป็นค่าคงที่ใน `SERIES_DEFS` ตามข้อ 5)
2. ต้องรองรับ `data-theme="light"` — ห้ามเขียนสีที่ทำให้ light theme อ่านไม่ออก และห้ามลบ selector
   `:root[data-theme='light']`
3. **ต้องคง `data-testid` เดิมทั้งหมด** — E2E และ vitest อ้างถึง (`sidebar`, `side-nav`, `device-card`,
   `theme-toggle`, `dashboard-head`, `stat-row`, `stat-tile-*`, `primary-zone`, `secondary-zone`,
   `layout-*`, `process-count`, `power-total`, `history-tabs`, …)
4. ตัวเลข/metric ใช้ `--font-mono` + `tabular-nums`; label หมวดใช้ uppercase + letter-spacing
5. พื้นผิว hierarchy: `--bg` → `--bg-elev` (sidebar) → `--panel` (การ์ด) → `--panel-2` (แถวใน/hover)
6. Responsive: ต้องไม่พังที่ 900px และ 640px (sidebar collapse + grid 1 คอลัมน์)
7. เพิ่ม metric ใหม่ในแถว KPI → เพิ่ม tile ใน `StatRow.vue` และคง `data-testid="stat-tile-<label>"`

## 7. วิธี verify

รันจากโฟลเดอร์ `frontend/`:

```powershell
npx vue-tsc --noEmit     # typecheck
npm run test             # vitest (unit)
npm run build            # vue-tsc + vite build
npx playwright test      # E2E (webServer auto-start: backend + vite dev)
```

E2E ต้องผ่านครบ: shell/sidebar, KPI row, history 5m tab, theme toggle, security/maintenance pages
