<template>
  <div class="matrix-wrap">
    <p class="hint">
      Rows are claims pulled from your question. Columns are sources.
      <span class="key"><i class="mark ok">✓</i> supports</span>
      <span class="key"><i class="mark no">✗</i> contradicts</span>
      <span class="key"><i class="mark na">·</i> not mentioned</span>
    </p>

    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th class="claim-col">Claim</th>
            <th v-for="source in sources" :key="source.id" class="src-col">
              <span v-if="labelFor(source.id)" class="badge">{{
                labelFor(source.id)
              }}</span>
              <span class="src-name" :title="`${source.publisher} — ${source.title}`">
                {{ source.publisher }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="claim in claims" :key="claim.id">
            <tr class="claim-row" :class="{ open: open === claim.id }" @click="toggle(claim.id)">
              <td class="claim-col">
                <div class="claim-text">{{ claim.text }}</div>
                <span class="pill" :class="statusPill(claim.status).cls">
                  {{ statusPill(claim.status).label }}
                </span>
              </td>
              <td
                v-for="source in sources"
                :key="source.id"
                class="cell"
                :class="stanceClass(claim.id, source.id)"
                :title="cellTitle(claim.id, source.id)"
              >
                <span class="mark">{{ mark(claim.id, source.id) }}</span>
              </td>
            </tr>
            <tr v-if="open === claim.id" class="evidence-row">
              <td :colspan="sources.length + 1">
                <div class="evidence">
                  <template v-if="evidenceFor(claim.id).length">
                    <div
                      v-for="item in evidenceFor(claim.id)"
                      :key="item.source_id"
                      class="evidence-item"
                    >
                      <div class="evidence-head">
                        <span class="pill" :class="item.stance === 'supports' ? 'green' : 'red'">
                          {{ item.stance }}
                        </span>
                        <strong>{{ publisher(item.source_id) }}</strong>
                        <span class="small muted">
                          confidence {{ Math.round((item.confidence || 0) * 100) }}%
                          <template v-if="item.quote && !item.quote_verified">
                            · unverified quote
                          </template>
                        </span>
                      </div>
                      <blockquote v-if="item.quote">“{{ item.quote }}”</blockquote>
                    </div>
                  </template>
                  <p v-else class="muted small">
                    No source in this set clearly addresses this claim.
                  </p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  claims: { type: Array, required: true },
  sources: { type: Array, required: true },
  stances: { type: Array, required: true },
  venn: { type: Object, default: null },
})

const STATUS = {
  consensus: { label: 'consensus', cls: 'green' },
  contested: { label: 'contested', cls: 'amber' },
  contradicted: { label: 'contradicted', cls: 'red' },
  single_source: { label: 'single source', cls: 'violet' },
  unaddressed: { label: 'unaddressed', cls: 'grey' },
}

const open = ref(null)

const lookup = computed(() => {
  const map = {}
  for (const stance of props.stances) {
    if (!map[stance.claim_id]) map[stance.claim_id] = {}
    map[stance.claim_id][stance.source_id] = stance
  }
  return map
})

const vennLabels = computed(() => {
  const map = {}
  for (const source of props.venn?.sources || []) map[source.id] = source.label
  return map
})

const publisherById = computed(() =>
  Object.fromEntries(props.sources.map((s) => [s.id, s.publisher]))
)

function stanceOf(claimId, sourceId) {
  return lookup.value[claimId]?.[sourceId]
}

function stanceClass(claimId, sourceId) {
  return stanceOf(claimId, sourceId)?.stance || 'not_mentioned'
}

function mark(claimId, sourceId) {
  const stance = stanceClass(claimId, sourceId)
  if (stance === 'supports') return '✓'
  if (stance === 'contradicts') return '✗'
  return '·'
}

function cellTitle(claimId, sourceId) {
  const item = stanceOf(claimId, sourceId)
  if (!item || item.stance === 'not_mentioned') return 'Not mentioned'
  return item.quote || item.stance
}

function evidenceFor(claimId) {
  return props.stances.filter(
    (s) => s.claim_id === claimId && s.stance !== 'not_mentioned'
  )
}

function publisher(sourceId) {
  return publisherById.value[sourceId] || sourceId
}

function labelFor(sourceId) {
  return vennLabels.value[sourceId] || ''
}

function statusPill(status) {
  return STATUS[status] || STATUS.unaddressed
}

function toggle(claimId) {
  open.value = open.value === claimId ? null : claimId
}
</script>

<style scoped>
.hint {
  margin: 0 0 0.6rem;
  font-size: 0.8rem;
  color: var(--muted);
}

.key {
  margin-left: 0.5rem;
  white-space: nowrap;
}

.mark {
  font-style: normal;
  font-weight: 700;
}

.mark.ok {
  color: var(--green);
}
.mark.no {
  color: var(--red);
}
.mark.na {
  color: var(--muted);
}

.scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

thead th {
  position: sticky;
  top: 0;
  background: var(--panel);
  text-align: left;
  padding: 0.45rem 0.5rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--muted);
  vertical-align: bottom;
}

.claim-col {
  min-width: 220px;
  max-width: 320px;
}

.src-col {
  width: 64px;
  text-align: center !important;
}

.src-name {
  display: block;
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  display: inline-block;
  font-size: 0.65rem;
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0 0.28rem;
  margin-bottom: 0.2rem;
}

.claim-row {
  cursor: pointer;
  border-bottom: 1px solid rgba(37, 50, 82, 0.6);
}

.claim-row:hover {
  background: rgba(255, 255, 255, 0.025);
}

.claim-row.open {
  background: rgba(94, 234, 212, 0.04);
}

td {
  padding: 0.5rem;
  vertical-align: top;
}

.claim-text {
  margin-bottom: 0.35rem;
}

.cell {
  text-align: center;
  font-size: 1rem;
  border-left: 1px solid rgba(37, 50, 82, 0.5);
}

.cell.supports {
  background: rgba(52, 211, 153, 0.14);
  color: var(--green);
}
.cell.contradicts {
  background: rgba(251, 113, 133, 0.14);
  color: var(--red);
}
.cell.not_mentioned {
  color: var(--muted);
}

.evidence-row td {
  background: rgba(0, 0, 0, 0.18);
  padding: 0.6rem 0.8rem 0.9rem;
}

.evidence {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.evidence-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

blockquote {
  margin: 0.3rem 0 0;
  padding-left: 0.7rem;
  border-left: 2px solid var(--border);
  color: var(--muted);
  font-size: 0.82rem;
}
</style>
