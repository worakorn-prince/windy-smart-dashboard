<script setup lang="ts">
import { computed } from 'vue'
import { ADMIN_TOKEN_HINT, useMaintenanceStore } from '@/stores/maintenance'

const store = useMaintenanceStore()

const tokenIssue = computed(() => /401|403|token|unauthori|ผู้ดูแล/i.test(store.error))
const showBanner = computed(() => !store.isAdmin || tokenIssue.value)
</script>

<template>
  <div v-if="showBanner" class="banner muted small" role="status">
    <span v-if="!store.isAdmin">
      ℹ️ การสแกนไดรเวอร์และล้างไฟล์ต้องรันเซิร์ฟเวอร์ด้วยสิทธิ์ผู้ดูแลระบบ (Administrator) เพื่อผลลัพธ์ครบถ้วน
    </span>
    <span v-if="tokenIssue" class="token-hint">
      🔑 {{ ADMIN_TOKEN_HINT }}
      <span class="muted">(คีย์: dashboard:adminToken)</span>
    </span>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.token-hint { color: var(--warn); }
</style>
