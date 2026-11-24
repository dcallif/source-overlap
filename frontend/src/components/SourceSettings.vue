<template>
  <section class="source-settings" :class="{ compact }">
    <details>
      <summary class="settings-summary">
        <span class="settings-title">Source feeds</span>
        <span class="settings-count">{{ enabledCount }} active</span>
      </summary>

      <div class="settings-body">
        <p class="settings-copy">
          Each question is searched across these feeds. Turn any off, or add a
          public RSS or Atom feed of your own.
        </p>

        <ul class="feed-list">
          <li
            v-for="source in sources"
            :key="source.id"
            class="feed"
            :class="{ off: !source.enabled }"
          >
            <div class="feed-info">
              <div class="feed-heading">
                <span class="feed-label">{{ source.label }}</span>
                <span class="feed-tag">{{
                  source.kind === 'encyclopedia'
                    ? 'Encyclopedia'
                    : source.builtin
                      ? 'News search'
                      : source.locked
                        ? 'Preset feed'
                        : 'Custom feed'
                }}</span>
              </div>
              <p class="feed-desc">{{ source.description }}</p>
            </div>

            <div class="feed-actions">
              <label class="switch">
                <input
                  type="checkbox"
                  :checked="source.enabled"
                  :disabled="loading"
                  :aria-label="`${source.enabled ? 'Disable' : 'Enable'} ${source.label}`"
                  @change="
                    $emit('toggle', {
                      id: source.id,
                      enabled: $event.target.checked,
                    })
                  "
                />
                <span class="switch-track" aria-hidden="true"></span>
              </label>
              <button
                v-if="!source.builtin && !source.locked"
                class="remove"
                type="button"
                :disabled="loading"
                :aria-label="`Remove ${source.label}`"
                @click="$emit('remove', source.id)"
              >
                Remove
              </button>
            </div>
          </li>
        </ul>

        <form class="add-feed" @submit.prevent="submit">
          <label class="sr-only" for="new-feed-url">RSS feed URL</label>
          <input
            id="new-feed-url"
            v-model="url"
            class="field url-field"
            type="url"
            placeholder="https://example.com/feed.xml"
            :disabled="loading || limitReached"
          />
          <label class="sr-only" for="new-feed-label">Feed label</label>
          <input
            id="new-feed-label"
            v-model="label"
            class="field label-field"
            type="text"
            placeholder="Label (optional)"
            maxlength="80"
            :disabled="loading || limitReached"
          />
          <button
            class="button"
            type="submit"
            :disabled="loading || limitReached || !url.trim()"
          >
            {{ loading ? 'Adding…' : 'Add feed' }}
          </button>
        </form>

        <p v-if="error" class="settings-error" role="alert">{{ error }}</p>
        <p v-else-if="limitReached" class="settings-hint">
          You have reached the limit of {{ maxCustom }} custom feeds.
        </p>
        <p v-else class="settings-hint">
          Public feeds only. Entries are matched against each question before
          they are used.
        </p>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  sources: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  maxCustom: { type: Number, default: 10 },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['add', 'toggle', 'remove'])

const url = ref('')
const label = ref('')

const enabledCount = computed(
  () => props.sources.filter((source) => source.enabled).length
)

const limitReached = computed(
  () =>
    props.sources.filter((source) => !source.builtin).length >= props.maxCustom
)

function submit() {
  if (!url.value.trim()) return
  emit('add', { url: url.value.trim(), label: label.value.trim() })
  url.value = ''
  label.value = ''
}
</script>

<style scoped>
.source-settings {
  margin-top: 28px;
  padding: 18px 22px;
  border: 1px solid var(--rule-strong);
  background: var(--surface);
}

.source-settings.compact {
  margin: 0;
  padding: 0;
  border: 0;
  border-top: 1px solid var(--rule);
  background: transparent;
}

.settings-summary {
  display: flex;
  align-items: baseline;
  justify-content: flex-start;
  gap: 12px;
  cursor: pointer;
  list-style: none;
}

.settings-summary::-webkit-details-marker {
  display: none;
}

.settings-summary::after {
  content: '+';
  color: var(--ink-2);
  font-size: 0.875rem;
}

details[open] .settings-summary::after {
  content: '−';
}

.settings-title {
  font-family: var(--font-serif);
  font-size: 1.25rem;
  font-weight: 500;
}

.compact .settings-title {
  font-family: var(--font-sans);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--ink-2);
}

.settings-count {
  margin-left: auto;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--ink-2);
  border: 1px solid var(--rule);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
}

.compact .settings-summary {
  padding: 14px 0 10px;
}

.settings-body {
  margin-top: 12px;
}

.compact details[open] .settings-body {
  margin-top: 4px;
}

.settings-copy {
  max-width: 62ch;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--ink-2);
}

.feed-list {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  border-top: 1px solid var(--rule);
}

.feed {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--rule);
}

.feed.off .feed-info {
  opacity: 0.55;
}

.feed-info {
  min-width: 0;
}

.feed-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.feed-label {
  font-size: 0.875rem;
  font-weight: 600;
}

.feed-tag {
  font-size: 0.625rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--ink-2);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 1px 5px;
}

.feed-desc {
  margin-top: 3px;
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--ink-2);
  max-width: 58ch;
  overflow-wrap: anywhere;
}

.feed-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
}

.switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.switch input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.switch-track {
  position: relative;
  display: inline-block;
  width: 34px;
  height: 18px;
  border: 1px solid var(--rule-strong);
  border-radius: 999px;
  background: var(--paper);
  transition: background-color 120ms ease, border-color 120ms ease;
}

.switch-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--ink-2);
  transition: transform 120ms ease, background-color 120ms ease;
}

.switch input:checked + .switch-track {
  border-color: var(--agree);
  background: var(--agree-soft);
}

.switch input:checked + .switch-track::after {
  transform: translateX(16px);
  background: var(--agree);
}

.switch input:focus-visible + .switch-track {
  outline: 2px solid var(--cobalt);
  outline-offset: 3px;
}

.switch input:disabled + .switch-track {
  opacity: 0.5;
}

.remove {
  border: 0;
  background: none;
  padding: 0;
  color: var(--disagree);
  font-size: 0.75rem;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.add-feed {
  display: flex;
  gap: 8px;
  align-items: stretch;
  margin-top: 14px;
  flex-wrap: wrap;
}

.add-feed .field {
  min-height: 2.5rem;
  font-size: 0.8125rem;
}

.url-field {
  flex: 1 1 260px;
}

.label-field {
  flex: 0 1 180px;
}

.add-feed .button {
  min-height: 2.5rem;
  font-size: 0.8125rem;
}

.settings-error {
  margin-top: 10px;
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--disagree);
}

.settings-hint {
  margin-top: 10px;
  font-size: 0.75rem;
  color: var(--ink-2);
}

@media (max-width: 680px) {
  .feed {
    flex-direction: column;
    gap: 8px;
  }

  .label-field {
    flex-basis: 100%;
  }

  .add-feed .button {
    flex: 1 1 auto;
  }
}
</style>
