<template>
  <section class="sources" aria-labelledby="sources-title">
    <div class="section-head">
      <h2 id="sources-title">Sources</h2>
      <p>Retrieved live. Open a source to read it in full.</p>
    </div>

    <p v-if="!sources.length" class="empty">No sources were retrieved.</p>

    <ol class="ledger">
      <li
        v-for="(source, index) in sources"
        :key="source.id"
        class="source"
        :class="`tone-${toneFor(source)}`"
      >
        <div class="source-top">
          <span class="source-letter">{{ letterFor(index) }}</span>
          <span class="source-publisher">{{ source.publisher }}</span>
          <span
            v-if="
              source.provider_label &&
              source.provider_label !== source.publisher
            "
            class="source-provider"
            >via {{ source.provider_label }}</span
          >
          <time v-if="source.published" :datetime="source.published">{{
            fmtDate(source.published)
          }}</time>
        </div>

        <h3 class="source-title">
          <a :href="source.url" target="_blank" rel="noopener noreferrer">{{
            source.title
          }}</a>
        </h3>

        <p class="source-snippet">{{ source.snippet }}</p>
        <p class="source-stance">{{ stanceFor(source) }}</p>
      </li>
    </ol>
  </section>
</template>

<script setup>
const props = defineProps({
  sources: { type: Array, required: true },
})

function letterFor(index) {
  return String.fromCharCode(65 + index)
}

function toneFor(source) {
  const support = source.support_count || 0
  const contradict = source.contradict_count || 0
  if (support > contradict) return 'agree'
  if (contradict > support) return 'disagree'
  if (support && contradict) return 'mixed'
  return 'unknown'
}

function stanceFor(source) {
  const support = source.support_count || 0
  const contradict = source.contradict_count || 0
  if (support && contradict) {
    return `Supported ${support} claim${
      support === 1 ? '' : 's'
    }; contradicted ${contradict}.`
  }
  if (support) {
    return `Supported ${support} claim${support === 1 ? '' : 's'}.`
  }
  if (contradict) {
    return `Contradicted ${contradict} claim${contradict === 1 ? '' : 's'}.`
  }
  return 'No direct stance on the extracted claims.'
}

function fmtDate(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
</script>

<style scoped>
.sources {
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
  font-size: 1.625rem;
}

.section-head p {
  font-size: 0.8125rem;
  color: var(--ink-2);
  max-width: 46ch;
}

.empty {
  font-size: 0.875rem;
  color: var(--ink-2);
  padding: 18px 0;
}

.ledger {
  list-style: none;
  margin: 0;
  padding: 0;
}

.source {
  padding: 18px 0 20px 14px;
  border-top: 1px solid var(--rule);
  border-left: 2px solid var(--rule);
}

.source.tone-agree {
  border-left-color: var(--agree);
}

.source.tone-disagree {
  border-left-color: var(--disagree);
}

.source.tone-mixed {
  border-left-color: var(--mixed);
}

.source-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.source-letter {
  font-size: 0.625rem;
  font-weight: 600;
  color: var(--ink-2);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 1px 4px;
}

.source-publisher {
  font-size: 0.75rem;
  font-weight: 600;
}

.source-provider {
  font-size: 0.6875rem;
  color: var(--ink-2);
}

.source-top time {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.source-title {
  margin-top: 6px;
  font-size: 1.1875rem;
  line-height: 1.35;
  max-width: 62ch;
}

.source-title a {
  color: var(--ink);
  text-decoration: none;
}

.source-title a:hover {
  color: var(--cobalt);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.source-snippet {
  margin-top: 6px;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--ink-2);
  max-width: 70ch;
}

.source-stance {
  margin-top: 8px;
  font-size: 0.75rem;
  font-weight: 600;
}

.source.tone-agree .source-stance {
  color: var(--agree);
}

.source.tone-disagree .source-stance {
  color: var(--disagree);
}

.source.tone-mixed .source-stance {
  color: var(--mixed);
}

.source.tone-unknown .source-stance {
  color: var(--ink-2);
}
</style>
