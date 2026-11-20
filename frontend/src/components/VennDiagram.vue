<template>
  <div class="venn">
    <p class="hint">
      Each circle is one source. Overlapping regions hold claims that multiple
      sources support. Click a region to inspect it.
    </p>

    <svg viewBox="0 0 520 400" role="img" aria-label="Venn diagram of source agreement">
      <g v-if="indexes.length">
        <circle
          v-for="(circle, i) in geom.circles"
          :key="`c${i}`"
          :cx="circle.cx"
          :cy="circle.cy"
          :r="circle.r"
          class="circle"
          :style="{
            fill: colors[i],
            stroke: colors[i],
            fillOpacity: hovered === i || selectedCircle === i ? 0.26 : 0.13,
            strokeOpacity: hovered === i || selectedCircle === i ? 1 : 0.55,
          }"
          @mouseenter="hovered = i"
          @mouseleave="hovered = null"
          @click="selectedCircle = selectedCircle === i ? null : i"
        />
      </g>

      <g
        v-for="(pos, key) in geom.labels"
        v-show="indexes.length"
        :key="key"
        class="region"
        :class="{ active: selected === key, empty: count(key) === 0 }"
        :transform="`translate(${pos[0]}, ${pos[1]})`"
        @click="select(key)"
      >
        <title>{{ regionName(key) }} — {{ count(key) }} claim(s)</title>
        <circle r="17" />
        <text text-anchor="middle" dominant-baseline="central">{{ count(key) }}</text>
      </g>

      <g v-if="!indexes.length" class="empty-state">
        <text x="260" y="200" text-anchor="middle">No sources to compare</text>
      </g>
    </svg>

    <div class="legend">
      <span
        v-for="(source, i) in venn.sources"
        :key="source.id"
        class="legend-item"
        :title="`${source.publisher} — ${source.title}`"
      >
        <span class="dot" :style="{ background: colors[i] }"></span>
        <strong>{{ source.label }}</strong>
        <span class="legend-name">{{ source.publisher }}</span>
        <span class="legend-title">{{ source.title }}</span>
      </span>
    </div>

    <p v-if="venn.sources.length < 3" class="hint small">
      Only {{ venn.sources.length }} source(s) could be compared; a Venn diagram
      needs at least two.
    </p>

    <div class="detail">
      <div v-if="selected" class="detail-block">
        <h4>{{ regionName(selected) }}</h4>
        <p v-if="!selectedClaims.length" class="muted small">
          No claims fall in this region.
        </p>
        <ul v-else class="claim-list">
          <li v-for="claim in selectedClaims" :key="claim.id">
            <span class="pill" :class="statusPill(claim.status).cls">
              {{ statusPill(claim.status).label }}
            </span>
            <span>{{ claim.text }}</span>
            <span v-if="supportLetters(claim)" class="small muted">
              supported by {{ supportLetters(claim) }}
            </span>
            <span v-if="contradictLetters(claim)" class="small muted">
              · contradicted by {{ contradictLetters(claim) }}
            </span>
          </li>
        </ul>
      </div>
      <p v-else class="muted small">
        No region selected. Click a numbered region in the diagram.
      </p>
    </div>

    <div v-if="outsideClaims.length" class="detail-block outside">
      <h4>Not supported by any of these sources</h4>
      <ul class="claim-list">
        <li v-for="claim in outsideClaims" :key="claim.id">
          <span class="pill" :class="statusPill(claim.status).cls">
            {{ statusPill(claim.status).label }}
          </span>
          <span>{{ claim.text }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  venn: { type: Object, required: true },
  claims: { type: Array, required: true },
})

const colors = ['#38bdf8', '#a78bfa', '#f472b6']

const GEOMETRY = {
  1: {
    circles: [{ cx: 260, cy: 180, r: 130 }],
    labels: { '1': [260, 180] },
  },
  2: {
    circles: [
      { cx: 200, cy: 190, r: 115 },
      { cx: 320, cy: 190, r: 115 },
    ],
    labels: { '10': [150, 150], '01': [370, 150], '11': [260, 150] },
  },
  3: {
    circles: [
      { cx: 180, cy: 150, r: 100 },
      { cx: 340, cy: 150, r: 100 },
      { cx: 260, cy: 265, r: 100 },
    ],
    labels: {
      '100': [112, 118],
      '010': [408, 118],
      '001': [260, 345],
      '110': [260, 92],
      '101': [168, 240],
      '011': [352, 240],
      '111': [260, 175],
    },
  },
}

const STATUS = {
  consensus: { label: 'consensus', cls: 'green' },
  contested: { label: 'contested', cls: 'amber' },
  contradicted: { label: 'contradicted', cls: 'red' },
  single_source: { label: 'single source', cls: 'violet' },
  unaddressed: { label: 'unaddressed', cls: 'grey' },
}

const selected = ref(null)
const selectedCircle = ref(null)
const hovered = ref(null)

const indexes = computed(() => props.venn.sources.map((_, i) => i))
const geom = computed(() => GEOMETRY[indexes.value.length] || GEOMETRY[3])
const claimsById = computed(() =>
  Object.fromEntries(props.claims.map((c) => [c.id, c]))
)

function count(key) {
  return (props.venn.regions?.[key] || []).length
}

function claimsFor(key) {
  return (props.venn.regions?.[key] || [])
    .map((id) => claimsById.value[id])
    .filter(Boolean)
}

function select(key) {
  selected.value = selected.value === key ? null : key
}

function regionName(key) {
  const bits = key.split('')
  const labels = props.venn.sources
    .filter((_, i) => bits[i] === '1')
    .map((s) => s.label)
  if (!labels.length) return 'Outside all circles'
  if (labels.length === props.venn.sources.length && labels.length > 1) {
    return `All sources (${labels.join(' + ')})`
  }
  return `${labels.join(' + ')} only`
}

function statusPill(status) {
  return STATUS[status] || STATUS.unaddressed
}

function supportLetters(claim) {
  return props.venn.sources
    .filter((s) => claim.support_sources.includes(s.id))
    .map((s) => s.label)
    .join(', ')
}

function contradictLetters(claim) {
  return props.venn.sources
    .filter((s) => claim.contradict_sources.includes(s.id))
    .map((s) => s.label)
    .join(', ')
}

const selectedClaims = computed(() =>
  selected.value ? claimsFor(selected.value) : []
)

const outsideClaims = computed(() =>
  (props.venn.outside || []).map((id) => claimsById.value[id]).filter(Boolean)
)
</script>

<style scoped>
.venn {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.hint {
  margin: 0;
  font-size: 0.8rem;
  color: var(--muted);
}

svg {
  width: 100%;
  height: auto;
  overflow: visible;
}

.circle {
  transition: fill-opacity 0.18s ease, stroke-opacity 0.18s ease;
  cursor: pointer;
}

.region {
  cursor: pointer;
}

.region circle {
  fill: var(--panel-2);
  stroke: var(--border);
  stroke-width: 1.5;
  transition: fill 0.15s ease, stroke 0.15s ease;
}

.region text {
  fill: var(--text);
  font-size: 13px;
  font-weight: 700;
  pointer-events: none;
}

.region:hover circle {
  stroke: var(--accent);
}

.region.active circle {
  fill: rgba(94, 234, 212, 0.2);
  stroke: var(--accent);
}

.region.empty circle {
  fill: rgba(255, 255, 255, 0.02);
}

.region.empty text {
  fill: var(--muted);
}

.empty-state text {
  fill: var(--muted);
  font-size: 14px;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  font-size: 0.8rem;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  max-width: 100%;
}

.legend-name {
  color: var(--muted);
}

.legend-title {
  color: var(--muted);
  opacity: 0.7;
  max-width: 22ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.legend-item {
  max-width: 100%;
}

.legend-item {
  max-width: 100%;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}

.detail {
  border-top: 1px solid var(--border);
  padding-top: 0.6rem;
}

.detail-block + .detail-block {
  margin-top: 0.7rem;
}

.detail-block h4 {
  font-size: 0.85rem;
  margin-bottom: 0.45rem;
}

.claim-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.claim-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.45rem;
  font-size: 0.85rem;
}

.outside {
  border-top: 1px dashed var(--border);
  padding-top: 0.6rem;
}
</style>
