import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Security from './pages/Security.vue'
import Maintenance from './pages/Maintenance.vue'
import { autoTip } from './directives/autoTip'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/security', name: 'security', component: Security },
    { path: '/maintenance', name: 'maintenance', component: Maintenance },
  ],
})

const app = createApp(App)
app.directive('auto-tip', autoTip)
app.use(createPinia())
app.use(router)
app.mount('#app')
