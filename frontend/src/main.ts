import './styles/tokens.css'
import './styles/base.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Security from './pages/Security.vue'
import Maintenance from './pages/Maintenance.vue'
import Viewer from './pages/Viewer.vue'
import { autoTip } from './directives/autoTip'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/security', name: 'security', component: Security },
    { path: '/maintenance', name: 'maintenance', component: Maintenance },
    { path: '/viewer', name: 'viewer', component: Viewer },
  ],
})

const app = createApp(App)
app.directive('auto-tip', autoTip)
app.use(createPinia())
app.use(router)
app.mount('#app')

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
