<script setup lang="ts">
import { computed, useId } from 'vue'

interface Props {
  label: string
  value: string
  unit?: string
  accent?: 'cyan' | 'violet' | 'lime' | 'amber'
  icon?: string
  delta?: string | null
  deltaTone?: 'good' | 'bad' | 'flat'
  caption?: string
  subtitle?: string
  spark?: number[]
}

const props = withDefaults(defineProps<Props>(), {
  unit: '',
  accent: 'cyan',
  icon: '',
  delta: null,
  deltaTone: 'flat',
  caption: '',
  subtitle: '',
  spark: () => [],
})

const SPARK_W = 100
const SPARK_H = 32
const SPARK_PAD = 2

const gradId = `stat-spark-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

const cleanSpark = computed<number[]>(() =>
  (props.spark ?? []).filter((v) => typeof v === 'number' && Number.isFinite(v)),
)

const hasSpark = computed(() => cleanSpark.value.length >= 2)

const linePoints = computed(() => {
  const values = cleanSpark.value
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min
  const last = values.length - 1
  return values
    .map((v, i) => {
      const t = range > 0 ? (v - min) / range : 0.5
      const x = (i / last) * SPARK_W
      const y = SPARK_H - SPARK_PAD - t * (SPARK_H - SPARK_PAD * 2)
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
})

const areaPoints = computed(() => {
  if (!linePoints.value) return ''
  return `0,${SPARK_H} ${linePoints.value} ${SPARK_W},${SPARK_H}`
})
</script>

<template>
  <article
    class="stat-tile"
    :class="`accent-${accent}`"
    :data-testid="`stat-tile-${label.toLowerCase()}`"
    :data-accent="accent"
  >
    <header class="stat-head">
      <div class="stat-head-left">
        <span class="stat-accent-bar" aria-hidden="true"></span>
        <span v-if="icon" class="stat-icon" aria-hidden="true">{{ icon }}</span>
        <span class="stat-label">{{ label }}</span>
      </div>

      <svg
        v-if="hasSpark"
        class="stat-spark"
        viewBox="0 0 100 32"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient :id="gradId" x1="0" y1="0" x2="0" y2="1">
            <stop class="spark-stop-top" offset="0%" />
            <stop class="spark-stop-bottom" offset="100%" />
          </linearGradient>
        </defs>
        <polygon class="spark-area" :points="areaPoints" :fill="`url(#${gradId})`" />
        <polyline class="spark-line" :points="linePoints" />
      </svg>
    </header>

    <div class="stat-value-row">
      <span class="stat-value">{{ value }}</span>
      <span v-if="unit" class="stat-unit">{{ unit }}</span>
    </div>

    <p v-if="subtitle" class="stat-subtitle">{{ subtitle }}</p>

    <footer class="stat-foot">
      <span v-if="delta" class="stat-delta" :class="`tone-${deltaTone}`">{{ delta }}</span>
      <span v-if="caption" class="stat-caption">{{ caption }}</span>
    </footer>
  </article>
</template>

<style scoped>
.stat-tile {
  position: relative;
  overflow: hidden;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.stat-tile::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--tile-accent), transparent 85%);
  opacity: 0.9;
}

.stat-tile:hover {
  border-color: var(--border-strong);
  box-shadow: 0 0 0 1px var(--accent-glow);
}

.accent-cyan { --tile-accent: var(--accent); }
.accent-violet { --tile-accent: var(--accent-3); }
.accent-lime { --tile-accent: var(--accent-2); }
.accent-amber { --tile-accent: var(--accent-4); }

.stat-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.stat-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.stat-accent-bar {
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--tile-accent);
  flex: none;
}

.stat-icon {
  font-size: 14px;
  line-height: 1;
  color: var(--tile-accent);
}

.stat-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat-spark {
  width: 96px;
  height: 32px;
  flex: none;
  overflow: visible;
}

.spark-line {
  fill: none;
  stroke: var(--tile-accent);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.spark-area {
  stroke: none;
}

.spark-stop-top {
  stop-color: var(--tile-accent);
  stop-opacity: 0.2;
}

.spark-stop-bottom {
  stop-color: var(--tile-accent);
  stop-opacity: 0;
}

.stat-value-row {
  display: flex;
  align-items: baseline;
  min-width: 0;
}

.stat-value {
  font-family: var(--font-mono);
  font-size: 40px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

.stat-unit {
  font-family: var(--font-mono);
  font-size: 16px;
  color: var(--muted);
  margin-left: 6px;
}

.stat-subtitle {
  font-size: 11px;
  color: var(--muted);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  min-width: 0;
}

.stat-delta {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.stat-delta.tone-good { color: var(--good); }
.stat-delta.tone-bad { color: var(--bad); }
.stat-delta.tone-flat { color: var(--muted); }

.stat-caption {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
