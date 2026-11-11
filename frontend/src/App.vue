<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import AlertToasts from '@/components/AlertToasts.vue'
import { useMetricsStore } from '@/stores/metrics'

const store = useMetricsStore()

const theme = ref<'dark' | 'light'>(localStorage.getItem('dash-theme') === 'light' ? 'light' : 'dark')

function applyTheme() {
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('dash-theme', theme.value)
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  applyTheme()
}

applyTheme()

const hostname = computed(() => store.system?.hostname ?? '—')
const os = computed(() => store.system?.os_name || store.system?.os || '—')
const python = computed(() => (store.system?.python_version ? `Python ${store.system.python_version}` : '—'))
const alertCount = computed(() => store.alerts.length)

store.connect()
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" data-testid="sidebar">
      <RouterLink to="/" class="brand" aria-label="Windy Smart Dashboard">
        <span class="brand-mark" aria-hidden="true">▨</span>
        <div class="brand-text">
          <strong>Windy</strong>
          <span>SMART DASHBOARD</span>
        </div>
      </RouterLink>

      <header class="nav">
        <nav class="side-nav" data-testid="side-nav">
          <p class="nav-group">MONITOR</p>
          <RouterLink to="/" exact-active-class="is-active" data-testid="side-nav-dashboard">Dashboard</RouterLink>
          <RouterLink to="/security" exact-active-class="is-active" data-testid="side-nav-security">Security</RouterLink>
          <RouterLink to="/maintenance" exact-active-class="is-active" data-testid="side-nav-maintenance">Maintenance</RouterLink>
          <RouterLink to="/viewer" exact-active-class="is-active" data-testid="side-nav-viewer">Viewer</RouterLink>
        </nav>
      </header>

      <nav class="side-nav-system" data-testid="side-nav-system">
        <p class="nav-group">SYSTEM</p>
        <RouterLink to="/security" exact-active-class="is-alerts-active" class="nav-with-badge" data-testid="side-nav-alerts">
          <span>การแจ้งเตือน</span>
          <span class="nav-badge" data-testid="side-nav-alert-count">{{ alertCount }}</span>
        </RouterLink>
      </nav>

      <div class="device-card" data-testid="device-card">
        <span class="device-dot" aria-hidden="true"></span>
        <div>
          <strong>{{ hostname }}</strong>
          <span>{{ os }}</span>
          <span>{{ python }}</span>
        </div>
      </div>
    </aside>

    <div class="app-main">
      <header class="topbar">
        <slot name="actions" />
        <button
          type="button"
          data-testid="theme-toggle"
          class="theme-toggle"
          :aria-label="theme === 'dark' ? 'สลับเป็นธีมสว่าง' : 'สลับเป็นธีมมืด'"
          :aria-pressed="theme === 'light'"
          @click="toggleTheme"
        >
          {{ theme === 'dark' ? '☀️ สว่าง' : '🌙 มืด' }}
        </button>
      </header>
      <main class="content">
        <RouterView />
      </main>
    </div>

    <AlertToasts />
  </div>
</template>

<style>
.app-shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-w);
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  background: var(--bg-elev);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: 30;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 4px 18px;
  color: var(--text);
}

.brand-mark {
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--accent), var(--accent-3));
  color: var(--on-accent);
  font-size: 16px;
  font-weight: 800;
  box-shadow: 0 0 18px var(--accent-glow);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
  min-width: 0;
}

.brand-text strong {
  font-size: 15px;
  letter-spacing: .01em;
}

.brand-text > span {
  font-size: 9px;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--muted);
}

.side-nav,
.side-nav-system {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-group {
  margin: 20px 0 0;
  padding: 0 12px 6px;
  font-size: 11px;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--muted);
}

.side-nav a,
.side-nav-system a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-ctl);
  color: var(--text-dim);
  font-size: 13px;
  font-weight: 500;
  transition: background 0.15s ease, color 0.15s ease;
}

.side-nav a:hover,
.side-nav-system a:hover {
  background: var(--accent-soft);
  color: var(--text);
}

.side-nav a.is-active {
  background: var(--panel-2);
  color: var(--accent);
  box-shadow: inset 2px 0 0 var(--accent);
}

.side-nav-system a.is-alerts-active {
  color: var(--accent-3);
}

.nav-with-badge {
  justify-content: space-between;
}

.nav-badge {
  min-width: 20px;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--accent-4);
  color: var(--on-warn);
  font-size: 10px;
  font-weight: 700;
  text-align: center;
}

.device-card {
  margin-top: auto;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.device-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--good);
  animation: pulse 2s infinite;
}

.device-card strong {
  display: block;
  font-size: 12px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-card > div span {
  display: block;
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(74, 222, 128, .55);
  }

  70% {
    box-shadow: 0 0 0 7px rgba(74, 222, 128, 0);
  }

  100% {
    box-shadow: 0 0 0 0 rgba(74, 222, 128, 0);
  }
}

.app-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  min-height: 56px;
  padding: 10px 20px;
  margin-left: var(--sidebar-w);
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}

.theme-toggle {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  padding: 6px 12px;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}

.theme-toggle:hover {
  background: var(--panel-2);
  border-color: var(--border-strong);
  color: var(--text);
}

.content {
  flex: 1 1 auto;
  min-width: 0;
  padding: 20px;
  margin-left: var(--sidebar-w);
}

@media (max-width: 900px) {
  .app-shell {
    --sidebar-w: 64px;
  }

  .sidebar {
    padding: 14px 8px;
    align-items: center;
  }

  .brand {
    padding: 0 0 14px;
  }

  .brand-text,
  .nav-group,
  .device-card > div {
    display: none;
  }

  .side-nav,
  .side-nav-system {
    width: 100%;
  }

  .side-nav a,
  .side-nav-system a {
    justify-content: center;
    padding: 10px 8px;
    font-size: 12px;
  }

  .nav-with-badge {
    justify-content: center;
  }

  .nav-badge {
    display: none;
  }

  .device-card {
    justify-content: center;
    padding: 10px 4px;
  }

  .device-dot {
    margin-top: 0;
  }

  .content {
    padding: 14px;
  }
}

@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .card {
    padding: 12px;
  }

  .topbar {
    padding: 8px 12px;
  }

  .content {
    padding: 10px;
  }

  table {
    font-size: 11px;
  }
}
</style>
