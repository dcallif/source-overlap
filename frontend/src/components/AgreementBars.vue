<template>
  <section class="agreement" aria-labelledby="agreement-title">
    <div class="section-head">
      <h2 id="agreement-title">Agreement</h2>
      <p>Each mark is a publisher. Open one to read the quote behind it.</p>
    </div>

    <p v-if="!claims.length" class="empty">No claims were extracted.</p>

    <article
      v-for="claim in claims"
      :key="claim.id"
      class="claim"
      :class="`tone-${toneFor(claim)}`"
    >
      <div class="claim-head">
        <h3>{{ claim.text }}</h3>
        <p class="claim-summary">{{ summaryFor(claim) }}</p>
      </div>

      <div class="strip" aria-hidden="true">
        <span
          v-for="segment in segmentsFor(claim)"
          :key="segment.source.id"
          :class="`seg-${segment.stance}`"
          :style="{ flexGrow: 1 }"
        ></span>
      </div>

      <div class="segments" role="group" :aria-label="`Sources for: ${claim.text}`">
        <button
          v-for="segment in segmentsFor(claim)"
          :key="segment.source.id"
          type="button"
          class="segment"
          :class="`stance-${segment.stance}`"
          :aria-expanded="isOpen(claim, segment.source)"
          :aria-label="`${segment.source.publisher} ${stanceLabel(segment.stance)}: ${claim.text}`"
          @click="toggle(claim, segment.source)"
        >
          <span class="seg-letter">{{ labels[segment.source.id] }}</span>
          <span class="seg-publisher" :title="segment.source.publisher">
            {{ segment.source.publisher }}
          </span>
          <span class="seg-mark" aria-hidden="true">{{
            markFor(segment.stance)
          }}</span>
        </button>
      </div>

      <div
        v-if="openedSegment(claim)"
        class="evidence"
        :class="`stance-${openedSegment(claim).stance}`"
      >
        <div class="evidence-head">
          <span class="evidence-publisher">{{
            openedSegment(claim).source.publisher
          }}</span>
          <span class="evidence-stance">{{
            stanceLabel(openedSegment(claim).stance)
          }}</span>
        </div>
        <blockquote v-if="openedSegment(claim).quote">
          “{{ openedSegment(claim).quote }}”
        </blockquote>
        <p v-else class="evidence-empty">
          No quote was captured for this source.
        </p>
        <p
          v-if="openedSegment(claim).quote && !openedSegment(claim).verified"
          class="evidence-note"
        >
          The quote could not be verified against the source text.
        </p>
        <a
          :href="openedSegment(claim).source.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          Open {{ openedSegment(claim).source.publisher }}
        </a>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  claims: { type: Array, required: true },
  sources: { type: Array, required: true },
  stances: { type: Array, required: true },
})

const open = ref(null)

const labels = computed(() =>
  Object.fromEntries(
    props.sources.map((source, index) => [
      source.id,
      String.fromCharCode(65 + index),
    ])
  )
)

const stanceMap = computed(() => {
  const map = {}
  for (const stance of props.stances) {
    map[`${stance.claim_id}:${stance.source_id}`] = stance
  }
  return map
})

function segmentsFor(claim) {
  return props.sources.map((source) => {
    const stance = stanceMap.value[`${claim.id}:${source.id}`]
    return {
      source,
      stance: stance?.stance || 'not_mentioned',
      quote: stance?.quote || '',
      verified: Boolean(stance?.quote_verified),
    }
  })
}

function keyFor(claim, source) {
  return `${claim.id}:${source.id}`
}

function isOpen(claim, source) {
  return open.value === keyFor(claim, source)
}

function toggle(claim, source) {
  const key = keyFor(claim, source)
  open.value = open.value === key ? null : key
}

function openedSegment(claim) {
  if (!open.value || !open.value.startsWith(`${claim.id}:`)) return null
  return segmentsFor(claim).find((s) => keyFor(claim, s.source) === open.value) || null
}

function toneFor(claim) {
  if (claim.status === 'consensus') return 'agree'
  if (claim.status === 'contested') return 'mixed'
  if (claim.status === 'contradicted') return 'disagree'
  if (claim.status === 'single_source') return 'mixed'
  return 'unknown'
}

function summaryFor(claim) {
  const support = claim.support_publisher_count ?? 0
  const contradict = claim.contradict_publisher_count ?? 0
  if (contradict > 0 && support > 0) {
    return `${support} agree, ${contradict} disagree.`
  }
  if (contradict > 0) {
    return `${contradict} independent ${
      contradict === 1 ? 'publisher contradicts' : 'publishers contradict'
    } this.`
  }
  if (support >= 2) {
    return `${support} independent publishers agree.`
  }
  if (support === 1) {
    return 'One publisher covers this; not yet corroborated.'
  }
  return 'No retrieved source addresses this.'
}

function markFor(stance) {
  if (stance === 'supports') return '✓'
  if (stance === 'contradicts') return '✗'
  return '·'
}

function stanceLabel(stance) {
  if (stance === 'supports') return 'supports'
  if (stance === 'contradicts') return 'contradicts'
  return 'does not address'
}
</script>

<style scoped>
.agreement {
  margin-top: 36px;
  padding-top: 22px;
  border-top: 1px solid var(--rule);
}

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.section-head h2 {
  font-size: 26px;
}

.section-head p {
  font-size: 13px;
  color: var(--ink-2);
  max-width: 46ch;
}

.empty {
  font-size: 14px;
  color: var(--ink-2);
  padding: 18px 0;
}

.claim {
  padding: 20px 0 22px;
  border-top: 1px solid var(--rule);
}

.claim-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px 24px;
  flex-wrap: wrap;
}

.claim-head h3 {
  font-size: 20px;
  line-height: 1.35;
  max-width: 52ch;
}

.claim-summary {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.tone-agree .claim-summary {
  color: var(--agree);
}

.tone-disagree .claim-summary {
  color: var(--disagree);
}

.tone-mixed .claim-summary {
  color: var(--mixed);
}

.tone-unknown .claim-summary {
  color: var(--ink-2);
}

.strip {
  display: flex;
  gap: 2px;
  height: 7px;
  margin-top: 14px;
}

.strip span {
  min-width: 2px;
}

.seg-supports {
  background: var(--agree);
}

.seg-contradicts {
  background: var(--disagree);
}

.seg-not_mentioned {
  background: var(--unknown-soft);
}

.segments {
  display: flex;
  flex-wrap: wrap;
  gap: 0 20px;
}

.segment {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 40px;
  padding: 6px 0;
  border: 0;
  border-bottom: 2px solid var(--rule);
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.segment:hover,
.segment[aria-expanded='true'] {
  background: var(--surface-2);
}

.segment.stance-supports {
  border-bottom-color: var(--agree);
}

.segment.stance-contradicts {
  border-bottom-color: var(--disagree);
}

.seg-letter {
  font-size: 10px;
  font-weight: 600;
  color: var(--ink-2);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 1px 4px;
}

.seg-publisher {
  font-size: 12px;
  max-width: 30ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.seg-mark {
  font-size: 12px;
  font-weight: 700;
}

.stance-supports .seg-mark {
  color: var(--agree);
}

.stance-contradicts .seg-mark {
  color: var(--disagree);
}

.stance-not_mentioned .seg-mark {
  color: var(--ink-2);
}

.evidence {
  margin-top: 14px;
  padding: 14px 16px;
  background: var(--surface-2);
  border-left: 2px solid var(--rule-strong);
}

.evidence.stance-supports {
  border-left-color: var(--agree);
}

.evidence.stance-contradicts {
  border-left-color: var(--disagree);
}

.evidence-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.evidence-publisher {
  font-size: 13px;
  font-weight: 600;
}

.evidence-stance {
  font-size: 12px;
  color: var(--ink-2);
}

blockquote {
  margin: 10px 0 0;
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 17px;
  line-height: 1.5;
  max-width: 58ch;
}

.evidence-empty {
  margin-top: 8px;
  font-size: 13px;
  color: var(--ink-2);
}

.evidence-note {
  margin-top: 8px;
  font-size: 12px;
  color: var(--mixed);
}

.evidence a {
  display: inline-block;
  margin-top: 10px;
  font-size: 12px;
}
</style>
