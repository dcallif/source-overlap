<template>
  <section
    v-if="status.requires_connector || status.connected"
    class="local-model"
    aria-labelledby="local-model-title"
  >
    <div class="model-head">
      <div>
        <p class="model-kicker">Local model</p>
        <h2 id="local-model-title">
          {{
            status.connected
              ? 'Your model is connected'
              : 'Connect your own model'
          }}
        </h2>
      </div>
      <span class="model-pill" :class="stateClass">{{ stateLabel }}</span>
    </div>

    <template v-if="!status.connected">
      <p class="model-copy">
        Run the connector on the computer where LM Studio is running. It
        connects out to this site, so you do not need to open any ports.
      </p>

      <div class="command-row">
        <code>{{
          pairing ? pairing.command : 'Preparing a pairing code…'
        }}</code>
        <button
          class="button command-copy"
          type="button"
          :disabled="!pairing"
          @click="copyCommand"
        >
          {{ copied ? 'Copied' : 'Copy' }}
        </button>
      </div>

      <p v-if="pairing" class="model-meta">
        Pairing code <strong>{{ pairing.code }}</strong>
        <span>· expires in {{ minutesLeft }} min</span>
      </p>

      <div class="model-actions">
        <button
          class="button primary"
          type="button"
          :disabled="loading"
          @click="$emit('pair')"
        >
          Generate a new code
        </button>
        <span class="model-hint">
          Start LM Studio's local server on port 1234 first.
        </span>
      </div>

      <p class="model-note">
        Install the connector once from the repository:
        <code>python -m pip install ./connector</code>
      </p>
    </template>

    <template v-else>
      <div class="model-live">
        <label class="sr-only" for="local-model-select">Local model</label>
        <select
          id="local-model-select"
          class="field"
          :value="status.model || ''"
          :disabled="!status.models.length || loading"
          @change="chooseModel"
        >
          <option v-if="!status.models.length" value="">
            No models loaded
          </option>
          <option
            v-for="model in status.models"
            :key="model"
            :value="model"
          >
            {{ model }}
          </option>
        </select>
        <button
          class="link-button"
          type="button"
          :disabled="loading"
          @click="$emit('disconnect')"
        >
          Disconnect
        </button>
      </div>

      <p v-if="!status.lm_studio" class="model-warning">
        The connector is running, but LM Studio is not reachable. Start its
        local server and load a model.
      </p>
      <p v-else-if="!status.models.length" class="model-warning">
        LM Studio is running, but no model is loaded.
      </p>
      <p v-else-if="status.last_error" class="model-warning">
        {{ status.last_error }}
      </p>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  status: { type: Object, required: true },
  pairing: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['pair', 'select', 'disconnect'])

const copied = ref(false)

const stateLabel = computed(() => {
  if (!props.status.connected) return 'Not connected'
  if (!props.status.lm_studio) return 'LM Studio offline'
  if (!props.status.models.length) return 'No model loaded'
  return 'Connected'
})

const stateClass = computed(() => {
  if (!props.status.connected) return 'idle'
  return props.status.lm_studio && props.status.models.length ? 'ok' : 'bad'
})

const minutesLeft = computed(() => {
  if (!props.pairing?.expires_at) return 0
  const remaining = new Date(props.pairing.expires_at).getTime() - Date.now()
  return Math.max(0, Math.ceil(remaining / 60000))
})

async function copyCommand() {
  if (!props.pairing?.command) return
  try {
    await navigator.clipboard.writeText(props.pairing.command)
    copied.value = true
    window.setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch {
    copied.value = false
  }
}

function chooseModel(event) {
  emit('select', event.target.value)
}
</script>

<style scoped>
.local-model {
  margin-top: 28px;
  padding: 20px 22px;
  border: 1px solid var(--rule-strong);
  border-left: 3px solid var(--cobalt);
  background: var(--surface);
}

.model-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.model-kicker {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-2);
}

.model-head h2 {
  margin-top: 4px;
  font-size: 22px;
}

.model-pill {
  border: 1px solid var(--rule);
  border-radius: 999px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-2);
  white-space: nowrap;
}

.model-pill.ok {
  border-color: var(--agree);
  color: var(--agree);
}

.model-pill.bad {
  border-color: var(--disagree);
  color: var(--disagree);
}

.model-copy {
  margin-top: 12px;
  max-width: 62ch;
  font-size: 14px;
  line-height: 1.6;
  color: var(--ink-2);
}

.command-row {
  display: flex;
  align-items: stretch;
  gap: 8px;
  margin-top: 14px;
}

.command-row code {
  flex: 1 1 auto;
  min-width: 0;
  overflow-x: auto;
  padding: 11px 12px;
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  background: var(--paper);
  color: var(--ink);
  font-size: 12px;
  white-space: nowrap;
}

.command-copy {
  min-height: 40px;
  padding: 0 14px;
  font-size: 12px;
}

.model-meta {
  margin-top: 9px;
  font-size: 12px;
  color: var(--ink-2);
}

.model-meta strong {
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.model-actions .button {
  min-height: 40px;
  font-size: 13px;
}

.model-hint {
  font-size: 12px;
  color: var(--ink-2);
}

.model-note {
  margin-top: 12px;
  font-size: 12px;
  color: var(--ink-2);
}

.model-note code {
  padding: 2px 5px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: var(--paper);
  color: var(--ink);
  font-size: 11px;
}

.model-live {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.model-live .field {
  flex: 1 1 280px;
  max-width: 440px;
  min-height: 40px;
}

.model-warning {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--disagree);
}

@media (max-width: 680px) {
  .command-row {
    flex-wrap: wrap;
  }

  .command-copy {
    flex: 0 0 auto;
  }
}
</style>
