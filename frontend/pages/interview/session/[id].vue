<template>
  <main class="interview-session mx-auto max-w-7xl px-4 py-6">
    <header class="session-heading">
      <div>
        <span class="tag bg-blue-50 text-blue-700">{{ session?.phase_label || '初始化中' }}</span>
        <h1 class="mt-2 text-2xl font-bold">{{ session?.job_title || '模拟面试' }}</h1>
        <p class="text-sm text-slate-500">
          {{ session?.company || '目标岗位' }} · 第 {{ session?.current_round || 0 }}/{{ session?.max_rounds || 10 }} 轮
        </p>
      </div>
      <div class="text-right">
        <span
          class="tag"
          :class="session?.degraded_mode ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'"
        >{{ session?.degraded_mode ? '规则降级' : 'Agent 运行中' }}</span>
        <div class="mt-2 h-2 w-40 rounded-full bg-slate-200">
          <div
            class="h-2 rounded-full bg-blue-600"
            :style="{ width: `${Math.min((session?.current_round || 0) / (session?.max_rounds || 10) * 100, 100)}%` }"
          />
        </div>
      </div>
    </header>

    <div class="session-columns">
      <section class="session-questions space-y-4">
        <div
          v-for="turn in session?.turns"
          :key="turn.id"
          :ref="el => setTurnRef(turn.id, el)"
          class="card p-5"
        >
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-blue-600">
              {{ turn.phase_label || turn.question.category }} {{ turn.is_followup ? '· 追问' : '' }}
            </span>
            <span v-if="turn.evaluation" class="tag bg-emerald-50 text-emerald-700">
              {{ turn.evaluation.overall_score }} 分
            </span>
          </div>
          <h2 class="mt-3 text-lg font-semibold text-slate-900">{{ turn.question.question }}</h2>
          <template v-if="isCurrent(turn) && (!turn.answer || pendingTurnId === turn.id)">
            <textarea v-model="answer" class="input mt-4 h-36" :disabled="running" placeholder="用真实经历、个人行动和结果回答" />
            <button class="btn-primary mt-3" :disabled="running || !answer.trim()" @click="submit(turn.id)">
              {{ pendingTurnId === turn.id ? processingLabel : '提交回答' }}
            </button>
          </template>
          <div v-if="turn.answer" class="mt-4 whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm">{{ turn.answer }}</div>
          <div v-if="turn.evaluation" class="mt-4 space-y-2 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm">
            <p><b>优势：</b>{{ displayList(turn.evaluation.strengths) || '暂无' }}</p>
            <p><b>证据缺口：</b>{{ displayList(turn.evaluation.evidence_gaps) || '暂无' }}</p>
            <p><b>改进建议：</b>{{ turn.evaluation.improvement_suggestion }}</p>
            <p v-if="displayList(turn.evaluation.factual_errors)"><b class="text-red-700">事实错误：</b>{{ displayList(turn.evaluation.factual_errors) }}</p>
            <p v-if="turn.evaluation.standard_answer_short"><b>参考回答：</b>{{ turn.evaluation.standard_answer_short }}</p>
            <details v-if="turn.evaluation.standard_answer_full">
              <summary class="cursor-pointer font-medium">查看完整参考回答</summary>
              <p class="mt-2 whitespace-pre-wrap">{{ turn.evaluation.standard_answer_full }}</p>
            </details>
          </div>
        </div>
        <div v-if="error" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          <span>{{ error }}</span>
          <button v-if="recoverableTurn" class="ml-3 rounded border border-red-200 bg-white px-3 py-1" :disabled="running" @click="continueNext">
            {{ running ? '生成中…' : '继续生成下一题' }}
          </button>
        </div>
      </section>

      <aside class="session-sidebar space-y-4">
        <div class="card p-5">
          <h2 class="font-semibold">Agent 工作流</h2>
          <div class="mt-3 space-y-2 text-sm">
            <p v-for="(log, index) in logs" :key="`${index}-${log}`" class="text-slate-600">✓ {{ log }}</p>
            <p v-if="running" class="text-blue-600">● {{ processingLabel }}</p>
          </div>
        </div>
        <div class="card p-5">
          <h2 class="font-semibold">公开资料来源</h2>
          <div v-for="source in session?.sources" :key="source.id" class="mt-3">
            <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer" class="block text-sm text-blue-600 underline">{{ source.title }}</a>
            <span v-else class="block text-sm text-slate-600">{{ source.title }}</span>
            <p v-if="source.status === 'summary_only'" class="mt-1 text-xs text-amber-700">已保存搜索摘要；原网页正文未能抓取</p>
          </div>
          <p v-if="!session?.sources?.length" class="mt-2 text-sm text-slate-400">未采集到公开资料</p>
        </div>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.interview-session {
  width: 100%;
  max-width: 80rem;
  margin-right: auto;
  margin-left: auto;
}

.session-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.session-columns {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  align-items: start;
  gap: 1.5rem;
}

.session-questions,
.session-sidebar {
  min-width: 0;
}

@media (max-width: 767px) {
  .session-heading {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .session-columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import { getInterview, stream } from '~/utils/api'

const route = useRoute()
const id = String(route.params.id)
const session = ref<any>()
const answer = ref('')
const running = ref(false)
const processingLabel = ref('评估中…')
const error = ref('')
const streamError = ref('')
const pendingTurnId = ref<number | null>(null)
const pendingAnswer = ref('')
const logs = ref<string[]>([])
const turnRefs = new Map<number, Element>()
const recoverableTurn = computed(() => {
  if (!session.value || session.value.status === 'completed' || session.value.turns.some((turn: any) => !turn.answer)) return null
  const last = session.value.turns.at(-1)
  return last?.answer && last?.evaluation ? last : null
})

function setTurnRef(id: number, el: Element | ComponentPublicInstance | null) { if (el instanceof Element) turnRefs.set(id, el) }
function displayList(value: unknown) {
  if (Array.isArray(value)) return value.filter(Boolean).join('、')
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}
function isCurrent(turn: any) { return !turn.answer && session.value?.turns.filter((item: any) => !item.answer).at(-1)?.id === turn.id }
async function load() { session.value = (await getInterview(id)).data }

function handle(name: string, data: any) {
  if (name === 'workflow_node_enter') {
    logs.value.push(`进入 ${data.node_name}`)
    processingLabel.value = data.node_id === 'next_step' ? '生成下一题中…' : '评估中…'
  }
  if (name === 'workflow_node_leave') logs.value.push(`完成 ${data.node_name}`)
  if (name === 'evaluation') {
    const turn = session.value.turns.find((item: any) => item.id === data.turn_id)
    if (turn) { turn.answer = data.answer || turn.answer || pendingAnswer.value; turn.evaluation = data.evaluation }
    processingLabel.value = '生成下一题中…'
  }
  if (name === 'question') {
    const existing = session.value.turns.find((turn: any) => turn.id === data.id)
    if (existing) Object.assign(existing, data); else session.value.turns.push(data)
    nextTick(() => turnRefs.get(data.id)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }
  if (name === 'interview_completed') session.value.final_review = data
  if (name === 'workflow_error') { streamError.value = data.error || 'Agent 工作流执行失败'; error.value = streamError.value }
}

async function begin() {
  running.value = true
  streamError.value = ''
  try { await stream(`/interviews/${id}/start`, undefined, handle); await load() }
  catch (e: any) { error.value = e.message || '面试初始化失败' }
  finally { running.value = false }
}

async function submit(turnId: number) {
  const submittedAnswer = answer.value.trim()
  if (!submittedAnswer) return
  const turn = session.value.turns.find((item: any) => item.id === turnId)
  pendingTurnId.value = turnId
  pendingAnswer.value = submittedAnswer
  running.value = true
  processingLabel.value = '评估中…'
  streamError.value = ''
  error.value = ''
  logs.value.push('已提交回答，等待评估')
  try {
    await stream(`/interviews/${id}/answer`, { turn_id: turnId, answer: submittedAnswer }, handle)
    await load()
    const persistedTurn = session.value?.turns?.find((item: any) => item.id === turnId)
    if (streamError.value) {
      // A workflow_error is a completed SSE response, not a fetch rejection.
      // Let the user retry evaluation or use the recovery action as appropriate.
      pendingTurnId.value = null
      pendingAnswer.value = ''
      answer.value = persistedTurn?.answer ? '' : submittedAnswer
    } else if (persistedTurn?.answer) {
      answer.value = ''
      pendingTurnId.value = null
      pendingAnswer.value = ''
    } else {
      answer.value = submittedAnswer
    }
    if (!streamError.value && session.value.status === 'completed') await navigateTo(`/interview/result/${id}`)
  } catch (e: any) {
    error.value = e.message || '回答处理失败，请重试'
    await load().catch(() => undefined)
    const persistedTurn = session.value?.turns?.find((item: any) => item.id === turnId)
    if (!persistedTurn?.answer) {
      answer.value = submittedAnswer
      pendingTurnId.value = null
      pendingAnswer.value = ''
    } else {
      answer.value = ''
      pendingTurnId.value = null
      pendingAnswer.value = ''
    }
  } finally {
    running.value = false
  }
}

async function continueNext() {
  const turn = recoverableTurn.value
  if (!turn) return
  running.value = true
  processingLabel.value = '生成下一题中…'
  streamError.value = ''
  error.value = ''
  try {
    await stream(`/interviews/${id}/answer`, { turn_id: turn.id, answer: '' }, handle)
    await load()
    pendingTurnId.value = null
    pendingAnswer.value = ''
    if (!streamError.value && session.value.status === 'completed') await navigateTo(`/interview/result/${id}`)
  } catch (e: any) {
    error.value = e.message || '下一题生成失败，请重试'
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  await load()
  const notice = sessionStorage.getItem(`interview-source-notice-${id}`)
  if (notice) { logs.value.push(notice); sessionStorage.removeItem(`interview-source-notice-${id}`) }
  if (!session.value.turns.length) await begin()
})
</script>
