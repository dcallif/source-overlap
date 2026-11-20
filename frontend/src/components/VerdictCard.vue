<template>
  <section class="verdict" :class="`tone-${verdict.tone}`">
    <p class="verdict-label">{{ verdict.label }}</p>
    <h1 class="verdict-question">{{ result.question }}</h1>
    <p v-if="directAnswer" class="verdict-answer">
      {{ directAnswer.answer }}
    </p>
    <p v-else class="verdict-headline">{{ result.verdict.headline }}</p>
    <p class="verdict-claim">{{ result.verdict.central_claim }}</p>
    <p class="verdict-explanation">{{ result.verdict.explanation }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ result: { type: Object, required: true } })

const directAnswer = computed(
  () => props.result.verdict.direct_answer || null
)

const isYesNo = computed(() =>
  /^(is|are|was|were|do|does|did|has|have|had|can|could|will|would|should)\b/i.test(
    props.result.question.trim()
  )
)

const VERDICTS = {
  supported: { yes: 'Yes', label: 'Supported', tone: 'agree' },
  contested: { yes: 'Mixed', label: 'Mixed', tone: 'mixed' },
  contradicted: { yes: 'No', label: 'Contradicted', tone: 'disagree' },
  insufficient_evidence: {
    yes: 'Not enough evidence',
    label: 'Not enough evidence',
    tone: 'mixed',
  },
  no_coverage: { yes: 'No coverage', label: 'No coverage', tone: 'unknown' },
}

const verdict = computed(() => {
  if (directAnswer.value) {
    const agreement = directAnswer.value.agreement
    const tone =
      agreement === 'agree'
        ? 'agree'
        : agreement === 'disagree'
          ? 'mixed'
          : 'unknown'
    return { tone, label: 'Answer' }
  }
  const item = VERDICTS[props.result.verdict.answer] || VERDICTS.no_coverage
  return {
    tone: item.tone,
    label: isYesNo.value ? item.yes : item.label,
  }
})
</script>

<style scoped>
.verdict {
  border-left: 3px solid var(--rule-strong);
  padding: 4px 0 4px 22px;
}

.tone-agree {
  border-left-color: var(--agree);
}

.tone-disagree {
  border-left-color: var(--disagree);
}

.tone-mixed {
  border-left-color: var(--mixed);
}

.tone-unknown {
  border-left-color: var(--unknown);
}

.verdict-label {
  font-family: var(--font-sans);
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: 10px;
}

.tone-agree .verdict-label {
  color: var(--agree);
}

.tone-disagree .verdict-label {
  color: var(--disagree);
}

.tone-mixed .verdict-label {
  color: var(--mixed);
}

.verdict-question {
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  font-weight: 500;
  max-width: 22ch;
}

.verdict-headline {
  margin-top: 18px;
  font-family: var(--font-serif);
  font-size: 1.5rem;
  line-height: 1.25;
}

.verdict-answer {
  margin-top: 18px;
  font-family: var(--font-serif);
  font-size: clamp(2rem, 3vw, 3rem);
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.verdict-claim {
  margin-top: 10px;
  font-family: var(--font-serif);
  font-size: 1.1875rem;
  line-height: 1.45;
  max-width: 52ch;
}

.verdict-explanation {
  margin-top: 14px;
  font-size: 0.9375rem;
  line-height: 1.6;
  color: var(--ink-2);
  max-width: 62ch;
}
</style>
