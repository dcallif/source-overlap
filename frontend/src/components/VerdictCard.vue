<template>
  <section class="verdict" :class="`tone-${verdict.tone}`">
    <p class="verdict-label">{{ verdict.label }}</p>
    <h1 class="verdict-question">{{ result.question }}</h1>
    <p class="verdict-headline">{{ result.verdict.headline }}</p>
    <p class="verdict-claim">{{ result.verdict.central_claim }}</p>
    <p class="verdict-explanation">{{ result.verdict.explanation }}</p>
    <p class="verdict-disclaimer">{{ result.verdict.disclaimer }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ result: { type: Object, required: true } })

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
  font-size: 14px;
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
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 500;
  max-width: 22ch;
}

.verdict-headline {
  margin-top: 18px;
  font-family: var(--font-serif);
  font-size: 24px;
  line-height: 1.25;
}

.verdict-claim {
  margin-top: 10px;
  font-family: var(--font-serif);
  font-size: 19px;
  line-height: 1.45;
  max-width: 52ch;
}

.verdict-explanation {
  margin-top: 14px;
  font-size: 15px;
  line-height: 1.6;
  color: var(--ink-2);
  max-width: 62ch;
}

.verdict-disclaimer {
  margin-top: 18px;
  padding-top: 12px;
  border-top: 1px solid var(--rule);
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-2);
  max-width: 62ch;
}
</style>
