<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import AlertToasts from '@/components/AlertToasts.vue'
</script>

<template>
  <div class="app-shell">
    <header class="nav">
      <RouterLink to="/" class="brand">🌬️ Windy Smart Dashboard</RouterLink>
      <nav>
        <RouterLink to="/" active-class="active">Dashboard</RouterLink>
        <RouterLink to="/security" active-class="active">Security</RouterLink>
      </nav>
    </header>
    <main class="content">
      <RouterView />
    </main>
    <AlertToasts />
  </div>
</template>

<style>
:root {
  --bg: #0f1020;
  --panel: #1a1b2e;
  --panel-2: #232440;
  --border: #2d2f55;
  --text: #e6e6ea;
  --muted: #a0a0c0;
  --accent: #7c9cff;
  --good: #5fd97c;
  --warn: #ffd75f;
  --bad: #ff6b6b;
  --crit: #ff4545;
  --info: #6fd0ff;
}

* { box-sizing: border-box; }

html, body, #app { height: 100%; margin: 0; }

body {
  font-family: 'Segoe UI', 'Inter', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
}

.app-shell { min-height: 100%; display: flex; flex-direction: column; }

.nav {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: linear-gradient(180deg, #14152a, #0f1020);
  border-bottom: 1px solid var(--border);
}

.nav .brand {
  color: var(--text);
  text-decoration: none;
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.5px;
}

.nav nav { display: flex; gap: 8px; }

.nav a {
  color: var(--muted);
  text-decoration: none;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 600;
  transition: all 0.15s ease;
}

.nav a:hover { color: var(--text); background: var(--panel-2); }
.nav a.active { color: var(--text); background: var(--panel-2); }

.content { flex: 1; padding: 20px; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  overflow: hidden;
  min-width: 0;
}

.card h3 {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  gap: 12px;
  flex-wrap: wrap;
}

.row .label { 
  color: var(--muted); 
  flex-shrink: 0;
  min-width: 0;
}
.row .value { 
  font-variant-numeric: tabular-nums; 
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  word-break: break-all;
}

.progress {
  height: 8px;
  background: var(--panel-2);
  border-radius: 4px;
  overflow: hidden;
  margin: 4px 0;
  width: 100%;
}
.progress > div {
  height: 100%;
  background: var(--accent);
  transition: width 0.5s ease;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  table-layout: fixed;
}

table th, table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

table th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }

button {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 12px;
  cursor: pointer;
  font-weight: 600;
  white-space: nowrap;
}

button:hover:not(:disabled) { background: var(--border); }
button:disabled { opacity: 0.5; cursor: not-allowed; }

button.primary { background: var(--accent); color: #0a0a1a; border-color: var(--accent); }
button.danger { background: var(--bad); color: #fff; border-color: var(--bad); }
button.warn { background: var(--warn); color: #1a1a1a; border-color: var(--warn); }

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  white-space: nowrap;
}

.badge.info { background: var(--info); color: #0a1a2a; }
.badge.low { background: var(--good); color: #0a2a14; }
.badge.medium { background: var(--warn); color: #2a1f0a; }
.badge.high { background: var(--bad); color: #2a0a0a; }
.badge.critical { background: var(--crit); color: #fff; }

.sev-info { color: var(--info); }
.sev-low { color: var(--good); }
.sev-medium { color: var(--warn); }
.sev-high { color: var(--bad); }
.sev-critical { color: var(--crit); font-weight: 700; }

.muted { color: var(--muted); }
.small { font-size: 11px; }

.kbd {
  font-family: 'JetBrains Mono', monospace;
  background: var(--panel-2);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  display: inline-block;
}

.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.text-wrap {
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.card-scroll {
  max-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
}

.card-scroll::-webkit-scrollbar {
  width: 6px;
}
.card-scroll::-webkit-scrollbar-track {
  background: var(--panel-2);
  border-radius: 3px;
}
.card-scroll::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
.card-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}
</style>
