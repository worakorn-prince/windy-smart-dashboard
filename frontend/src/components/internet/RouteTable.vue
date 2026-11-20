<script setup lang="ts">
import { computed } from 'vue'
import type { RouteEntry } from '@/stores/internet'

const props = defineProps<{
  routes: RouteEntry[]
  defaultGateway: string | null
  gatewayInterfaceIndex: number | null
}>()

const sortedRoutes = computed(() => {
  return [...props.routes].sort((a, b) => {
    if (a.is_default && !b.is_default) return -1
    if (!a.is_default && b.is_default) return 1
    return a.destination.localeCompare(b.destination)
  })
})

const gateway_interface_index = computed(() => props.gatewayInterfaceIndex)

function formatDestination(route: RouteEntry): string {
  if (route.is_default) return 'default'
  return `${route.destination}/${route.prefix_length}`
}

function getProtocolLabel(protocol: number): string {
  const protocols: Record<number, string> = {
    1: 'LOCAL',
    2: 'NETMGMT',
    3: 'ICMP',
    4: 'EGP',
    5: 'GGP',
    6: 'HELLO',
    7: 'RIP',
    8: 'IS-IS',
    9: 'ES-IS',
    10: 'CISCO',
    11: 'BBN',
    12: 'OSPF',
    13: 'BGP',
    255: 'OTHER',
  }
  return protocols[protocol] ?? `UNKNOWN(${protocol})`
}

function getOriginLabel(origin: number): string {
  const origins: Record<number, string> = {
    0: 'OTHER',
    1: 'MANUAL',
    2: 'WELL_KNOWN',
    3: 'DHCP',
    4: 'BOOTP',
    5: 'RA',
  }
  return origins[origin] ?? `UNKNOWN(${origin})`
}

function isDefaultRoute(route: RouteEntry): boolean {
  return route.is_default
}
</script>

<template>
  <div class="route-table" data-testid="route-table">
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Destination</th>
            <th>Next Hop</th>
            <th>Interface</th>
            <th>Metric</th>
            <th>Protocol</th>
            <th>Age</th>
            <th>Origin</th>
            <th>Default</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="route in sortedRoutes"
            :key="`${route.destination}-${route.prefix_length}-${route.interface_index}`"
            :class="{ 'default-route': isDefaultRoute(route) }"
            :data-testid="`route-row-${route.destination}-${route.prefix_length}`"
          >
            <td class="destination-col">
              <span class="destination" :class="{ 'is-default': isDefaultRoute(route) }">{{ formatDestination(route) }}</span>
            </td>
            <td class="next-hop-col">
              <span v-if="route.next_hop" class="next-hop">{{ route.next_hop }}</span>
              <span v-else class="on-link">on-link</span>
            </td>
            <td class="interface-col">
              <span class="interface-index" :data-testid="`route-iface-${route.interface_index}`">Interface {{ route.interface_index }}</span>
            </td>
            <td class="metric-col">{{ route.metric }}</td>
            <td class="protocol-col">{{ getProtocolLabel(route.protocol) }}</td>
            <td class="age-col">{{ route.age }}s</td>
            <td class="origin-col">{{ getOriginLabel(route.origin) }}</td>
            <td class="default-col">
              <span v-if="isDefaultRoute(route)" class="default-badge" data-testid="route-default-badge">DEFAULT</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!props.routes?.length" class="empty-state" data-testid="route-table-empty">
      <p>ไม่มีเส้นทาง (Route table empty)</p>
    </div>

    <div class="table-footer" v-if="props.routes?.length">
      <span class="route-count">{{ props.routes.length }} routes</span>
      <span v-if="props.defaultGateway" class="gateway-info" data-testid="route-default-gateway">
        Default Gateway: {{ props.defaultGateway }} {{ gateway_interface_index !== null ? `(Interface ${gateway_interface_index})` : '' }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.route-table {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th, td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

th {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  font-weight: 600;
  background: var(--panel-2);
  position: sticky;
  top: 0;
  white-space: nowrap;
}

tr:hover td {
  background: var(--panel-2);
}

tr.default-route td {
  background: rgba(34, 211, 238, 0.05);
}

.destination {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
}

.destination.is-default {
  color: var(--accent);
  font-weight: 600;
}

.next-hop {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text);
}

.on-link {
  font-size: 11px;
  color: var(--muted);
  font-style: italic;
}

.interface-index {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  color: var(--text-dim);
}

.metric-col,
.age-col {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
  text-align: right;
  width: 70px;
}

.protocol-col,
.origin-col {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: uppercase;
  white-space: nowrap;
}

.default-badge {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 6px;
  background: linear-gradient(135deg, var(--accent), var(--accent-3));
  color: var(--on-accent);
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.default-col { width: 80px; text-align: center; }

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--muted);
}

.route-count { font-family: var(--font-mono); }

.gateway-info {
  font-family: var(--font-mono);
  color: var(--text-dim);
}

@media (max-width: 640px) {
  th, td {
    padding: 8px 8px;
    font-size: 11px;
  }
}
</style>