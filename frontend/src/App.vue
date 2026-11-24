<template>
  <div class="app">
    <header class="topbar">
      <div class="shell topbar-inner">
        <a class="brand" href="/" aria-label="Source Overlap home">
          <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
          <span>Source Overlap</span>
        </a>
        <div class="topbar-actions">
          <button
            class="health"
            :class="healthClass"
            type="button"
            :title="healthTitle"
            @click="handleHealthClick"
          >
            <span class="dot" aria-hidden="true"></span>
            <span>{{ healthLabel }}</span>
          </button>
          <button
            class="theme-toggle"
            type="button"
            :aria-label="
              isDark ? 'Switch to light mode' : 'Switch to dark mode'
            "
            :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
            @click="toggleTheme"
          >
            <svg
              v-if="isDark"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="4"></circle>
              <path
                d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"
              ></path>
            </svg>
            <svg
              v-else
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z"></path>
            </svg>
          </button>
        </div>
      </div>
    </header>

    <main class="shell">
      <section v-if="!result && !loading && !error" class="hero">
        <div class="hero-copy">
          <h1>What do the sources say?</h1>
          <p class="lede">
            Ask a question. We compare independent publishers and show exactly
            where they agree, and where they don't.
          </p>

          <LocalModelPanel
            v-if="showModelPanel"
            :status="session"
            :pairing="pairing"
            :loading="sessionBusy"
            :using-public="publicActive"
            @pair="refreshPairing"
            @select="chooseModel"
            @disconnect="disconnectLocalModel"
          />

          <form class="ask" @submit.prevent="ask(false)">
            <label class="field-label" for="question">Your question</label>
            <div class="ask-row">
              <input
                id="question"
                v-model="question"
                class="field"
                type="text"
                placeholder="e.g. Did the WHO declare coffee a carcinogen?"
                :disabled="loading"
              />
              <select
                v-model.number="maxSources"
                class="field"
                :disabled="loading"
                aria-label="Number of sources"
              >
                <option :value="4">4 sources</option>
                <option :value="6">6 sources</option>
                <option :value="8">8 sources</option>
              </select>
              <button
                class="button primary"
                type="submit"
                :disabled="loading || !question.trim() || !modelReady"
              >
                Compare sources
              </button>
            </div>
            <p class="hint">
              We compare independent publishers, not just count links.
            </p>
          </form>

          <div class="examples">
            <span class="examples-label">Try one</span>
            <button
              v-for="example in examples"
              :key="example"
              class="example"
              type="button"
              :disabled="loading"
              @click="useExample(example)"
            >
              {{ example }}
            </button>
          </div>

          <p v-if="publicActive && !showModelPanel" class="provider-note">
            Using the public model ({{ publicInfo.model }}). Question and source
            text are sent to {{ publicInfo.label }}.
            <button class="link-button" type="button" @click="openLocalModel">
              Use your own local model
            </button>
          </p>
        </div>

        <aside class="specimen" aria-label="Example result">
          <p class="specimen-kicker">Example</p>
          <p class="specimen-claim">
            NVIDIA released its first GPU in 1999.
          </p>
          <div class="specimen-strip" aria-hidden="true">
            <span></span><span></span><span></span><span></span>
          </div>
          <div class="specimen-sources" aria-hidden="true">
            <span>Wikipedia</span><span>Wccftech</span><span>VideoCardz</span
            ><span>TechSpot</span>
          </div>
          <p class="specimen-note">Independent publishers agree on 1999.</p>
        </aside>
      </section>

      <section
        v-if="!result && !loading && !error"
        class="landing-method"
        aria-labelledby="landing-method-title"
      >
        <h2 id="landing-method-title" class="landing-method-title">
          The method
        </h2>
        <dl class="method-points">
          <div>
            <dt>Retrieved live</dt>
            <dd>Recent news and Wikipedia are searched for each question.</dd>
          </div>
          <div>
            <dt>Counted by publisher</dt>
            <dd>Two links from the same outlet count once.</dd>
          </div>
          <div>
            <dt>Read with care</dt>
            <dd>A result reflects retrieved coverage, not absolute truth.</dd>
          </div>
        </dl>
      </section>

      <SourceSettings
        v-if="!result && !loading && !error"
        :sources="sourceCatalog"
        :loading="sourcesLoading"
        :error="sourcesError"
        :max-custom="sourceMax"
        @add="addSource"
        @toggle="toggleSource"
        @remove="removeSource"
      />

      <section v-if="result || loading || error" class="ask-compact">
        <LocalModelPanel
          v-if="showModelPanel"
          :status="session"
          :pairing="pairing"
          :loading="sessionBusy"
          :using-public="publicActive"
          @pair="refreshPairing"
          @select="chooseModel"
          @disconnect="disconnectLocalModel"
        />
        <form class="ask" @submit.prevent="ask(false)">
          <div class="ask-row">
            <label class="sr-only" for="question-compact">Your question</label>
            <input
              id="question-compact"
              v-model="question"
              class="field"
              type="text"
              placeholder="Ask a question"
              :disabled="loading"
            />
            <select
              v-model.number="maxSources"
              class="field"
              :disabled="loading"
              aria-label="Number of sources"
            >
              <option :value="4">4 sources</option>
              <option :value="6">6 sources</option>
              <option :value="8">8 sources</option>
            </select>
            <button
              class="button primary"
              type="submit"
              :disabled="loading || !question.trim() || !modelReady"
            >
              Compare sources
            </button>
          </div>
        </form>
        <button
          v-if="result"
          class="link-button"
          type="button"
          :disabled="loading"
          @click="ask(true)"
        >
          Run again
        </button>
        <button
          v-if="publicActive && !showModelPanel"
          class="link-button"
          type="button"
          :disabled="loading"
          @click="openLocalModel"
        >
          Use your own local model
        </button>
      </section>

      <section v-if="error" class="notice" role="alert">
        <h1 class="notice-title">{{ errorTitle }}</h1>
        <p>{{ error }}</p>
        <div class="notice-steps">
          <template v-if="isConnectorError">
            <p>The connection between this site and your computer stopped.</p>
            <ol>
              <li>Open the Local model panel and create a new pairing code.</li>
              <li>Run the source-overlap-connect command again.</li>
              <li>Keep that terminal open while you use the site.</li>
            </ol>
          </template>
          <template v-else-if="isPublicError">
            <p>The public model could not answer this request.</p>
            <ol>
              <li>Wait a moment and try again; the free endpoint is rate-limited.</li>
              <li>Connect your own local model for more reliable answers.</li>
              <li>
                Or set PUBLIC_LLM_URL and PUBLIC_LLM_MODEL in backend/.env and
                restart the backend.
              </li>
            </ol>
          </template>
          <template v-else-if="isTimeout">
            <p>The model took too long to answer.</p>
            <ol>
              <li>
                Wait for the model to finish loading in LM Studio, then try
                again.
              </li>
              <li>Load a smaller model if the current one is too large.</li>
              <li v-if="!session?.requires_connector">
                Or raise LM_TIMEOUT in backend/.env and restart the backend.
              </li>
            </ol>
          </template>
          <template v-else-if="isLlmError">
            <p>To fix the local model connection:</p>
            <ol>
              <li>Open LM Studio and load a model.</li>
              <li>Start the local server on port 1234.</li>
              <li>Press Compare sources again.</li>
            </ol>
          </template>
        </div>
      </section>

      <section v-if="loading" class="progress" aria-live="polite">
        <h1 class="progress-title">Checking the sources</h1>
        <ol class="stage-list">
          <li
            v-for="(item, index) in stages"
            :key="item.key"
            :class="stageState(index)"
          >
            <span class="stage-mark" aria-hidden="true"></span>
            <span class="stage-label">{{ item.label }}</span>
            <span
              v-if="index === currentStageIndex && stageMessage"
              class="stage-detail"
            >
              {{ stageMessage }}
            </span>
          </li>
        </ol>
      </section>

      <section v-if="result" class="results">
        <div class="reading">
          <VerdictCard :result="result" />
          <AgreementBars
            :claims="result.claims"
            :sources="result.sources"
            :stances="result.stances"
          />
          <SourcesPanel :sources="result.sources" />
        </div>

        <aside class="rail">
          <section class="rail-block">
            <h2 class="rail-title">At a glance</h2>
            <dl class="stats">
              <div>
                <dt>Sources</dt>
                <dd>{{ result.metrics.sources }}</dd>
              </div>
              <div>
                <dt>Independent publishers</dt>
                <dd>{{ result.metrics.publishers }}</dd>
              </div>
              <div>
                <dt>Claims checked</dt>
                <dd>{{ result.metrics.claims }}</dd>
              </div>
              <div>
                <dt>Claims corroborated</dt>
                <dd>{{ result.metrics.corroborated }}</dd>
              </div>
              <div>
                <dt>Coverage</dt>
                <dd>{{ coverageLabel }}</dd>
              </div>
              <div>
                <dt>Agreement</dt>
                <dd>{{ agreementLabel }}</dd>
              </div>
            </dl>
          </section>

          <section class="rail-block">
            <details class="method">
              <summary>How this was checked</summary>
              <ol>
                <li>Your question is split into atomic claims.</li>
                <li>Wikipedia and news sources are searched and ranked.</li>
                <li>Each source is judged against each claim.</li>
                <li>Agreement counts independent publishers, not links.</li>
              </ol>
              <div class="method-queries">
                <p class="method-label">Searched for</p>
                <ul>
                  <li v-for="q in result.meta.queries" :key="q">{{ q }}</li>
                </ul>
              </div>
            </details>
          </section>

          <SourceSettings
            compact
            :sources="sourceCatalog"
            :loading="sourcesLoading"
            :error="sourcesError"
            :max-custom="sourceMax"
            @add="addSource"
            @toggle="toggleSource"
            @remove="removeSource"
          />

          <footer class="rail-meta">
            <p><span>Model</span> {{ result.meta.model }}</p>
            <p><span>Time</span> {{ elapsed }}s</p>
            <p v-if="result.meta.cached"><span>Result</span> Cached</p>
          </footer>
        </aside>
      </section>
    </main>

    <footer class="site-footer">
      <div class="shell site-footer-inner">
        <p>
          Local-first research. Sources are retrieved live; agreement counts
          independent publishers, not links. A public model is used unless you
          connect your own local model.
        </p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  createPairing,
  createSource,
  deleteSource,
  disconnectModel,
  getHealth,
  getSessionStatus,
  getSources,
  selectModel as setLocalModel,
  updateSource,
} from './api/client'
import AgreementBars from './components/AgreementBars.vue'
import LocalModelPanel from './components/LocalModelPanel.vue'
import SourceSettings from './components/SourceSettings.vue'
import SourcesPanel from './components/SourcesPanel.vue'
import VerdictCard from './components/VerdictCard.vue'
import { useTheme } from './composables/useTheme'

const examples = [
  'Did the WHO declare coffee a carcinogen?',
  'In which year did NVIDIA release its first GPU?',
  'What is the current status of the Artemis moon program?',
]

const stages = [
  { key: 'connecting', label: 'Connect to the model' },
  { key: 'planning', label: 'Read the question' },
  { key: 'retrieving', label: 'Find sources' },
  { key: 'judging', label: 'Compare claims' },
  { key: 'done', label: 'Write the verdict' },
]

const { isDark, toggleTheme } = useTheme()

const question = ref('')
const maxSources = ref(4)
const loading = ref(false)
const stage = ref('')
const stageMessage = ref('')
const result = ref(null)
const error = ref('')
const health = ref(null)
const healthChecked = ref(false)
const session = ref(null)
const pairing = ref(null)
const sessionBusy = ref(false)
const showLocalModel = ref(false)
const sourceCatalog = ref([])
const sourceMax = ref(10)
const sourcesLoading = ref(false)
const sourcesError = ref('')
let sessionTimer = null
let healthTimer = null
let pairingRequest = null

const currentStageIndex = computed(() => {
  const key = stage.value === 'cached' ? 'done' : stage.value
  const index = stages.findIndex((item) => item.key === key)
  return index === -1 ? 0 : index
})

const isConnectorError = computed(() =>
  /connector|pairing|connect your local model/i.test(error.value)
)

const isPublicError = computed(() =>
  /public model|public endpoint|pollinations|rate-limited|http 429|http 402/i.test(
    error.value
  )
)

const isLlmError = computed(() =>
  /lm studio|local server|port 1234|no model/i.test(error.value)
)

const isTimeout = computed(() =>
  /timeout|stopped sending|too long|did not respond/i.test(error.value)
)

const errorTitle = computed(() => {
  if (isConnectorError.value) return 'The local connector stopped'
  if (isPublicError.value) return 'The public model is unavailable'
  if (isTimeout.value) return 'The model is taking too long'
  if (isLlmError.value) return "The local model isn't responding"
  return 'The request failed'
})

const publicInfo = computed(
  () =>
    session.value?.public_llm || {
      enabled: false,
      label: '',
      model: '',
    }
)

const localAvailable = computed(
  () => Boolean(health.value?.lm_studio && health.value?.models?.length)
)

const publicActive = computed(() => {
  const current = session.value
  if (!current || current.connected || current.requires_connector) return false
  if (!publicInfo.value?.enabled) return false
  if (current.llm_provider === 'public') return true
  if (current.llm_provider === 'local') return false
  if (!healthChecked.value) return false
  return !localAvailable.value
})

const showModelPanel = computed(() => {
  const current = session.value
  if (!current) return false
  if (current.requires_connector || current.connected) return true
  return publicActive.value && showLocalModel.value
})

const modelReady = computed(() => {
  const current = session.value
  if (!current || !current.requires_connector) return true
  return Boolean(
    current.connected &&
    current.lm_studio &&
    current.models?.length &&
    current.model
  )
})

const healthLabel = computed(() => {
  const current = session.value
  if (current?.requires_connector) {
    if (!current.connected) return 'Connect local model'
    return current.model ? `Local · ${current.model}` : 'Local model connected'
  }
  if (current?.connected) {
    return current.model ? `Local · ${current.model}` : 'Local model ready'
  }
  if (publicActive.value) {
    return publicInfo.value.model
      ? `Public · ${publicInfo.value.model}`
      : 'Public model'
  }
  if (!healthChecked.value) return 'Checking local model'
  if (localAvailable.value) {
    return health.value.model
      ? `Local · ${health.value.model}`
      : 'Local model ready'
  }
  if (health.value?.lm_studio) return 'No model loaded'
  return 'Local model offline'
})

const healthTitle = computed(() => {
  const current = session.value
  if (current?.requires_connector) {
    if (!current.connected) {
      return 'Connect the local connector to use your own model'
    }
    return current.model
      ? `Local model: ${current.model}`
      : 'Local model connected'
  }
  if (current?.connected) {
    return current.model
      ? `Local model: ${current.model}`
      : 'Local model connected'
  }
  if (publicActive.value) {
    const label = publicInfo.value.label || 'a public provider'
    const model = publicInfo.value.model || 'public model'
    return (
      `Using ${label} (${model}). Question and source text are sent ` +
      'to a third party. Click to connect your own local model.'
    )
  }
  if (!healthChecked.value) return 'Checking LM Studio'
  if (localAvailable.value) {
    return health.value.model
      ? `LM Studio: ${health.value.model}`
      : 'LM Studio is ready'
  }
  if (health.value?.lm_studio) {
    return 'LM Studio is running, but no model is loaded'
  }
  return 'LM Studio is not reachable'
})

const healthClass = computed(() => {
  const current = session.value
  if (current?.requires_connector) {
    if (!current.connected) return 'idle'
    return current.lm_studio && current.models?.length ? 'ok' : 'bad'
  }
  if (current?.connected) {
    return current.lm_studio && current.models?.length ? 'ok' : 'bad'
  }
  if (publicActive.value) return 'ok'
  if (!healthChecked.value) return 'idle'
  return localAvailable.value ? 'ok' : 'bad'
})

const coverageLabel = computed(() => {
  const value = result.value?.metrics?.coverage
  return value === null || value === undefined
    ? 'n/a'
    : `${Math.round(value * 100)}%`
})

const agreementLabel = computed(() => {
  const value = result.value?.metrics?.agreement
  return value === null || value === undefined
    ? 'n/a'
    : `${Math.round(value * 100)}%`
})

const elapsed = computed(() =>
  result.value ? (result.value.meta.elapsed_ms / 1000).toFixed(1) : '0'
)

function stageState(index) {
  if (index < currentStageIndex.value) return 'done'
  if (index === currentStageIndex.value) return 'active'
  return 'pending'
}

async function loadHealth(silent = false) {
  if (!silent) healthChecked.value = false
  try {
    const { data } = await getHealth()
    health.value = data
  } catch {
    health.value = { lm_studio: false }
  } finally {
    healthChecked.value = true
  }
}

async function ensurePairing(force = false) {
  if (
    !force &&
    pairing.value &&
    new Date(pairing.value.expires_at).getTime() > Date.now()
  ) {
    return
  }
  if (pairingRequest) return pairingRequest
  pairingRequest = (async () => {
    try {
      const { data } = await createPairing()
      pairing.value = data
    } catch {
      pairing.value = null
    } finally {
      pairingRequest = null
    }
  })()
  return pairingRequest
}

async function refreshPairing() {
  sessionBusy.value = true
  try {
    await ensurePairing(true)
  } finally {
    sessionBusy.value = false
  }
}

async function refreshSession() {
  try {
    const { data } = await getSessionStatus()
    session.value = data
    if (data.requires_connector && !data.connected) {
      await ensurePairing()
    } else {
      pairing.value = null
    }
  } catch {
    session.value = null
  }
}

async function chooseModel(model) {
  if (!model || model === session.value?.model) return
  sessionBusy.value = true
  try {
    const { data } = await setLocalModel(model)
    session.value = data
  } catch {
    await refreshSession()
  } finally {
    sessionBusy.value = false
  }
}

async function disconnectLocalModel() {
  sessionBusy.value = true
  try {
    const { data } = await disconnectModel()
    session.value = data
    await ensurePairing(true)
  } catch {
    await refreshSession()
  } finally {
    sessionBusy.value = false
  }
}

async function loadSources() {
  sourcesError.value = ''
  try {
    const { data } = await getSources()
    sourceCatalog.value = data.sources || []
    sourceMax.value = data.max_custom ?? 10
  } catch {
    sourcesError.value = 'Could not load the source feeds.'
  }
}

function applySourceSnapshot(data) {
  sourceCatalog.value = data.sources || []
  sourceMax.value = data.max_custom ?? sourceMax.value
}

function sourceErrorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback
}

async function addSource({ url, label }) {
  sourcesLoading.value = true
  sourcesError.value = ''
  try {
    const { data } = await createSource(url, label)
    applySourceSnapshot(data)
  } catch (err) {
    sourcesError.value = sourceErrorMessage(
      err,
      'Could not add that feed. Check the URL and try again.'
    )
  } finally {
    sourcesLoading.value = false
  }
}

async function toggleSource({ id, enabled }) {
  sourcesLoading.value = true
  sourcesError.value = ''
  try {
    const { data } = await updateSource(id, enabled)
    applySourceSnapshot(data)
  } catch (err) {
    sourcesError.value = sourceErrorMessage(
      err,
      'Could not update that feed.'
    )
  } finally {
    sourcesLoading.value = false
  }
}

async function removeSource(id) {
  sourcesLoading.value = true
  sourcesError.value = ''
  try {
    const { data } = await deleteSource(id)
    applySourceSnapshot(data)
  } catch (err) {
    sourcesError.value = sourceErrorMessage(
      err,
      'Could not remove that feed.'
    )
  } finally {
    sourcesLoading.value = false
  }
}

async function openLocalModel() {
  showLocalModel.value = true
  await ensurePairing()
  requestAnimationFrame(() => {
    document
      .getElementById('local-model-title')
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

async function handleHealthClick() {
  await refreshSession()
  if (session.value?.requires_connector && !session.value.connected) {
    await openLocalModel()
    return
  }
  await loadHealth()
  if (publicActive.value) {
    await openLocalModel()
  }
}

function useExample(text) {
  question.value = text
  ask(false)
}

function handleEvent(event) {
  if (event.type === 'status') {
    if (event.stage) stage.value = event.stage
    if (event.message) stageMessage.value = event.message
  } else if (event.type === 'result') {
    result.value = event.data
    stage.value = 'done'
  } else if (event.type === 'error') {
    error.value = event.message || 'Unknown error'
  }
}

async function ask(refresh) {
  if (loading.value || !question.value.trim()) return
  if (!modelReady.value) {
    await openLocalModel()
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  stage.value = ''
  stageMessage.value = ''

  try {
    const response = await fetch('/api/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: question.value.trim(),
        max_sources: maxSources.value,
        refresh,
      }),
    })

    if (!response.ok) {
      let detail = `HTTP ${response.status}`
      try {
        const body = await response.json()
        detail = body.detail || detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let index
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index).trim()
        buffer = buffer.slice(index + 1)
        if (line) handleEvent(JSON.parse(line))
      }
    }
    if (buffer.trim()) handleEvent(JSON.parse(buffer))
  } catch (err) {
    error.value =
      err.message ||
      'Request failed. Check that the backend is running on port 8000.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadHealth(), refreshSession(), loadSources()])
  sessionTimer = window.setInterval(() => {
    if (!document.hidden) refreshSession()
  }, 4000)
  healthTimer = window.setInterval(() => {
    if (!document.hidden) loadHealth(true)
  }, 30000)
  const preset = new URLSearchParams(window.location.search).get('q')
  if (preset && preset.trim().length >= 3) {
    question.value = preset
    await ask(false)
  }
})

onBeforeUnmount(() => {
  if (sessionTimer) window.clearInterval(sessionTimer)
  if (healthTimer) window.clearInterval(healthTimer)
})
</script>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

main {
  flex: 1;
}

.site-footer {
  border-top: 1px solid var(--rule);
  margin-top: 32px;
}

.site-footer-inner {
  padding-top: 18px;
  padding-bottom: 28px;
}

.site-footer p {
  margin: 0;
  max-width: 70ch;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.topbar {
  border-bottom: 1px solid var(--rule);
}

.topbar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 16px;
  padding-bottom: 16px;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 18px;
}

.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid var(--rule);
  border-radius: 50%;
  background: transparent;
  color: var(--ink-2);
  transition: color 120ms ease, border-color 120ms ease,
    background-color 120ms ease;
}

.theme-toggle:hover {
  border-color: var(--rule-strong);
  background: var(--surface-2);
  color: var(--ink);
}

.theme-toggle svg {
  width: 16px;
  height: 16px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  text-decoration: none;
  font-family: var(--font-serif);
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.brand:hover {
  text-decoration: none;
}

.brand-mark {
  position: relative;
  width: 22px;
  height: 16px;
  display: inline-block;
}

.brand-mark i {
  position: absolute;
  top: 1px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid var(--ink);
  mix-blend-mode: multiply;
}

.brand-mark i:nth-child(1) {
  left: 0;
  background: rgba(0, 140, 149, 0.35);
}

.brand-mark i:nth-child(2) {
  left: 4px;
  background: rgba(176, 58, 107, 0.3);
}

.brand-mark i:nth-child(3) {
  left: 8px;
  background: rgba(201, 151, 0, 0.3);
}

.health {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 0;
  background: none;
  padding: 4px 0;
  color: var(--ink-2);
  font-size: 0.75rem;
}

.health .dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--unknown);
}

.health span:last-child {
  max-width: 30ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health.ok .dot {
  background: var(--agree);
}

.health.bad .dot {
  background: var(--disagree);
}

.health:hover {
  color: var(--ink);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: clamp(32px, 4vw, 72px);
  align-items: end;
  padding: clamp(48px, 5vw, 88px) 0 clamp(40px, 4.2vw, 80px);
}

.hero-copy h1 {
  font-size: clamp(2.375rem, 6vw, 4rem);
  line-height: 0.98;
  letter-spacing: -0.03em;
  max-width: 12ch;
}

.lede {
  margin-top: 18px;
  font-size: 1.0625rem;
  line-height: 1.6;
  color: var(--ink-2);
  max-width: 46ch;
}

.ask {
  margin-top: 1.875rem;
}

.field-label {
  display: block;
  font-size: 0.8125rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.ask-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.ask-row .field {
  flex: 1 1 auto;
}

.ask-row select.field {
  flex: 0 0 auto;
}

.hint {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.provider-note {
  margin-top: 1rem;
  max-width: 48ch;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--ink-2);
}

.provider-note .link-button {
  margin-left: 4px;
  font-size: 0.8125rem;
}

.examples {
  margin-top: 1.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  align-items: baseline;
}

.examples-label {
  font-size: 0.8125rem;
  color: var(--ink-2);
}

.example {
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  background: none;
  padding: 4px 0;
  color: var(--ink);
  font-size: 0.875rem;
  text-align: left;
}

.example:hover:not(:disabled) {
  border-bottom-color: var(--cobalt);
  color: var(--cobalt);
}

.example:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.specimen {
  border: 1px solid var(--rule-strong);
  background: var(--surface);
  padding: 22px;
  align-self: end;
}

.specimen-kicker {
  font-size: 0.75rem;
  color: var(--ink-2);
  margin-bottom: 14px;
}

.specimen-claim {
  font-family: var(--font-serif);
  font-size: 1.375rem;
  line-height: 1.3;
}

.specimen-strip {
  display: flex;
  gap: 2px;
  margin-top: 20px;
  height: 8px;
}

.specimen-strip span {
  flex: 1;
  background: var(--agree);
}

.specimen-strip span:nth-child(1) {
  opacity: 0.75;
}

.specimen-strip span:nth-child(2) {
  opacity: 0.85;
}

.specimen-strip span:nth-child(3) {
  opacity: 0.95;
}

.specimen-sources {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 10px;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.specimen-note {
  margin-top: 16px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--agree);
}

.landing-method {
  border-top: 1px solid var(--rule);
  padding-top: 24px;
  padding-bottom: 8px;
}

.landing-method-title {
  font-family: var(--font-serif);
  font-size: 1.375rem;
  font-weight: 500;
  margin-bottom: 18px;
}

.method-points {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 28px;
  margin: 0;
}

.method-points > div {
  border-top: 1px solid var(--rule);
  padding-top: 12px;
}

.method-points dt {
  font-size: 0.875rem;
  font-weight: 600;
}

.method-points dd {
  margin: 5px 0 0;
  max-width: 34ch;
  font-size: 0.8125rem;
  line-height: 1.55;
  color: var(--ink-2);
}

.ask-compact {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem 0 0;
  flex-wrap: wrap;
}

.ask-compact :deep(.local-model) {
  flex: 1 1 100%;
  margin-top: 0;
}

.ask-compact .ask {
  flex: 1 1 520px;
  margin: 0;
}

.ask-compact .ask-row {
  max-width: 52rem;
}

.notice {
  margin: 2rem 0;
  padding: 1.25rem 1.375rem;
  border-left: 3px solid var(--disagree);
  background: var(--surface);
  max-width: 45rem;
}

.notice-title {
  font-size: 1.5rem;
  margin-bottom: 8px;
}

.notice p {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--ink-2);
}

.notice-steps {
  margin-top: 14px;
}

.notice-steps ol {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 0.875rem;
  color: var(--ink-2);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress {
  padding: 3rem 0 4rem;
  max-width: 38.75rem;
}

.progress-title {
  font-size: 1.75rem;
  margin-bottom: 22px;
}

.stage-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--rule);
}

.stage-list li {
  display: grid;
  grid-template-columns: 20px 1fr;
  gap: 4px 12px;
  padding: 14px 0;
  border-bottom: 1px solid var(--rule);
  align-items: baseline;
}

.stage-mark {
  width: 9px;
  height: 9px;
  border: 1px solid var(--rule-strong);
  border-radius: 50%;
  display: inline-block;
  margin-top: 5px;
}

.stage-list li.active .stage-mark {
  border-color: var(--cobalt);
  background: var(--cobalt);
}

.stage-list li.done .stage-mark {
  border-color: var(--agree);
  background: var(--agree);
}

.stage-label {
  font-size: 0.9375rem;
  color: var(--ink-2);
}

.stage-list li.active .stage-label {
  color: var(--ink);
  font-weight: 600;
}

.stage-list li.done .stage-label {
  color: var(--ink);
}

.stage-detail {
  grid-column: 2;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.results {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(300px, 18vw, 380px);
  gap: clamp(32px, 3.5vw, 64px);
  padding: clamp(28px, 3vw, 56px) 0 clamp(56px, 5vw, 96px);
  align-items: start;
}

.reading {
  min-width: 0;
}

.rail {
  position: sticky;
  top: 24px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.rail-block {
  border-top: 1px solid var(--rule);
  padding-top: 16px;
}

.rail-title {
  font-family: var(--font-sans);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: 12px;
}

.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
  margin: 0;
}

.stats div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stats dt {
  font-size: 0.6875rem;
  color: var(--ink-2);
}

.stats dd {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.method summary {
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 600;
  list-style: none;
}

.method summary::-webkit-details-marker {
  display: none;
}

.method summary::after {
  content: '+';
  float: right;
  color: var(--ink-2);
}

.method[open] summary::after {
  content: '−';
}

.method ol {
  margin: 14px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.8125rem;
  color: var(--ink-2);
}

.method-queries {
  margin-top: 16px;
}

.method-label {
  font-size: 0.6875rem;
  color: var(--ink-2);
  margin-bottom: 4px;
}

.method-queries ul {
  margin: 0;
  padding-left: 16px;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.rail-meta {
  border-top: 1px solid var(--rule);
  padding-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--ink-2);
}

.rail-meta span {
  color: var(--ink);
  font-weight: 600;
  margin-right: 6px;
}

@media (max-width: 980px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 32px;
    padding: 44px 0 36px;
  }

  .hero-copy h1 {
    max-width: 16ch;
  }

  .specimen {
    max-width: 520px;
  }

  .results {
    grid-template-columns: 1fr;
    gap: 36px;
  }

  .rail {
    position: static;
  }
}

@media (max-width: 680px) {
  .ask-row {
    flex-wrap: wrap;
  }

  .ask-row .field {
    flex-basis: 100%;
  }

  .ask-row select.field {
    flex: 0 0 auto;
  }

  .ask-row .button {
    flex: 1 1 auto;
  }

  .topbar-inner {
    flex-wrap: wrap;
  }

  .examples {
    gap: 8px 14px;
  }

  .method-points {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .ask-compact .ask {
    flex-basis: 100%;
  }
}
</style>
