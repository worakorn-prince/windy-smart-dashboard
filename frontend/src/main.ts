import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Security from './pages/Security.vue'
import { autoTip } from './directives/autoTip'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/security', name: 'security', component: Security },
  ],
})

const app = createApp(App)
app.directive('auto-tip', autoTip)
app.use(createPinia())
app.use(router)
app.mount('#app')
