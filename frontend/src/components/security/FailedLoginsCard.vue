<script setup lang="ts">
import { computed } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()

interface FailedLogin {
  TimeCreated: string
  TargetUser: string
  LogonType: number
  IpAddress: string
  Workstation: string
  FailureReason: string
}

const failed = computed<FailedLogin[]>(() => store.audit?.data?.failed_logins ?? [])
</script>

<template>
  <div class="card">
    <h3>Failed Logins (last 100)</h3>
    <p class="muted small" v-if="!failed.length">None — or audit hasn't run, or admin needed to read.</p>
    <table v-else>
      <thead>
        <tr>
          <th>Time</th>
          <th>User</th>
          <th>IP</th>
          <th>Workstation</th>
          <th>Type</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(l, i) in failed" :key="i">
          <td class="value small">{{ new Date(l.TimeCreated).toLocaleString() }}</td>
          <td v-auto-tip>{{ l.TargetUser }}</td>
          <td class="kbd">{{ l.IpAddress }}</td>
          <td class="muted small" v-auto-tip :data-fulltext="`${l.Workstation} — ${l.FailureReason}`">{{ l.Workstation }}</td>
          <td class="value">{{ l.LogonType }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.kbd { font-family: monospace; font-size: 11px; }
</style>