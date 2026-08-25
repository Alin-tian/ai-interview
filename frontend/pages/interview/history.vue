<template>
  <main class="mx-auto max-w-5xl px-4 py-10">
    <div class="flex flex-wrap items-center justify-between gap-4"><div><h1 class="text-3xl font-bold">面试历史</h1><p class="mt-2 text-slate-500">继续未完成的模拟面试，或查看已完成报告。</p></div><div class="flex items-center gap-2"><select v-model="pendingJob" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"><option value="">全部岗位</option><option v-for="job in jobOptions" :key="job" :value="job">{{ job }}</option></select><button type="button" class="btn-primary" @click="applyFilter">筛选</button></div></div>
    <div v-if="error" class="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }} <button class="ml-3 rounded border px-3 py-1" @click="loadHistory">重试</button></div>
    <div v-if="loading && !items.length" class="card mt-6 p-10 text-center text-slate-500">正在加载面试记录…</div>
    <div class="mt-6 space-y-3"><div v-for="x in filteredItems" :key="x.id" class="card flex items-center justify-between gap-4 p-5"><NuxtLink :to="destination(x)" class="min-w-0 flex-1"><h2 class="font-semibold text-slate-900">{{ x.job_title }}</h2><p class="mt-1 text-sm text-slate-500">{{ x.company || '未填写公司' }}</p><p class="mt-2 text-xs text-slate-400">创建：{{ formatTime(x.created_at) }} · 更新：{{ formatTime(x.updated_at) }}</p></NuxtLink><div class="flex shrink-0 items-center gap-4"><span class="status-badge" :class="`status-${x.status}`">{{ statusLabel(x.status) }}</span><button class="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600" :disabled="deleting === x.id" @click="openDeleteDialog(x)">删除</button></div></div><div v-if="!loading && !filteredItems.length" class="card p-10 text-center text-slate-500">暂无面试记录</div></div>
    <Teleport to="body">
      <div v-if="pendingDelete" class="delete-dialog-overlay" @click.self="cancelDelete">
        <section class="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title">
          <h2 id="delete-dialog-title" class="delete-dialog-title">确认删除</h2>
          <p class="delete-dialog-message">确定删除“{{ pendingDelete.job_title }}”这条面试记录吗？关联的简历文件和面试资料将被同时删除，且不可恢复。</p>
          <div class="delete-dialog-actions">
            <button type="button" class="delete-dialog-button delete-dialog-cancel" :disabled="deleting !== null" @click="cancelDelete">取消</button>
            <button type="button" class="delete-dialog-button delete-dialog-confirm" :disabled="deleting !== null" @click="remove">{{ deleting !== null ? '删除中…' : '确认删除' }}</button>
          </div>
        </section>
      </div>
    </Teleport>
  </main>
</template>
<script setup lang="ts">
import { deleteInterview, getHistory } from '~/utils/api'
const items = ref<any[]>([]), deleting = ref<number | null>(null), loading = ref(false), error = ref(''), pendingJob = ref(''), selectedJob = ref(''), pendingDelete = ref<any | null>(null)
const jobOptions = computed(() => Array.from(new Set(items.value.map(item => String(item.job_title || '').trim()).filter(Boolean))).sort())
const filteredItems = computed(() => selectedJob.value ? items.value.filter(item => item.job_title === selectedJob.value) : items.value)
const statusLabel = (x: string) => ({ created: '待开始', in_progress: '进行中', completed: '已完成', failed: '失败' }[x] || x)
const formatTime = (value: string) => new Date(value).toLocaleString('zh-CN', { hour12: false })
const destination = (x: any) => x.status === 'completed' ? `/interview/result/${x.id}` : `/interview/session/${x.id}`
function applyFilter() { selectedJob.value = pendingJob.value }
function openDeleteDialog(x: any) { pendingDelete.value = x }
function cancelDelete() { if (deleting.value === null) pendingDelete.value = null }
async function remove() { const x = pendingDelete.value; if (!x) return; deleting.value = x.id; error.value = ''; try { await deleteInterview(x.id); items.value = items.value.filter(item => item.id !== x.id); pendingDelete.value = null } catch (e: any) { error.value = e.message || '删除失败，请稍后重试' } finally { deleting.value = null } }
async function loadHistory() { loading.value = true; error.value = ''; try { const result = await getHistory(); items.value = Array.isArray(result?.data) ? result.data : [] } catch (e: any) { error.value = e.message || '加载历史失败' } finally { loading.value = false } }
onMounted(loadHistory)
onActivated(loadHistory)
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 64px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
}

.status-created {
  border-color: #e2e8f0;
  background: #f1f5f9;
  color: #475569;
}

.status-in_progress {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.status-completed {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

.status-failed {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.delete-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 20px;
  background: rgb(15 23 42 / 45%);
}

.delete-dialog {
  box-sizing: border-box;
  width: min(400px, 100%);
  padding: 24px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 20px 45px rgb(15 23 42 / 20%);
}

.delete-dialog-title {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  font-weight: 600;
  line-height: 28px;
}

.delete-dialog-message {
  margin: 12px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 22px;
}

.delete-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.delete-dialog-button {
  min-width: 80px;
  height: 40px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  line-height: 38px;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s;
}

.delete-dialog-cancel {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
}

.delete-dialog-cancel:hover { background: #f8fafc; }
.delete-dialog-confirm { border: 1px solid #dc2626; background: #dc2626; color: #fff; }
.delete-dialog-confirm:hover { border-color: #b91c1c; background: #b91c1c; }
.delete-dialog-button:disabled { cursor: not-allowed; opacity: 0.55; }
</style>
