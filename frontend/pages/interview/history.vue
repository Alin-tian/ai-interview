<template>
  <main class="mx-auto max-w-5xl px-4 py-10">
    <div class="flex items-center justify-between"><div><h1 class="text-3xl font-bold">面试历史</h1><p class="mt-2 text-slate-500">继续未完成的模拟面试，或查看已完成报告。</p></div><NuxtLink to="/interview/setup" class="btn-primary">新建面试</NuxtLink></div>
    <p v-if="error" class="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{error}}</p>
    <div class="mt-6 space-y-3"><div v-for="x in items" :key="x.id" class="card flex items-center justify-between gap-4 p-5 transition hover:border-blue-300"><NuxtLink :to="destination(x)" class="min-w-0 flex-1"><h2 class="font-semibold text-slate-900">{{x.job_title}}</h2><p class="mt-1 text-sm text-slate-500">{{x.company||'未填写公司'}}</p><p class="mt-2 text-xs text-slate-400">创建：{{formatTime(x.created_at)}} · 更新：{{formatTime(x.updated_at)}}</p></NuxtLink><div class="flex shrink-0 items-center gap-4"><div class="text-right"><span :class="x.status==='completed'?'bg-emerald-50 text-emerald-700':x.status==='in_progress'?'bg-blue-50 text-blue-700':'bg-slate-100 text-slate-600'" class="tag">{{statusLabel(x.status)}}</span><p v-if="x.overall_score!==null" class="mt-2 text-sm font-semibold text-blue-600">{{x.overall_score}} 分</p><p v-else class="mt-2 text-xs text-slate-400">第 {{x.current_round}} 轮</p></div><button class="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50" :disabled="deleting===x.id" @click="remove(x)">{{deleting===x.id?'删除中…':'删除'}}</button></div></div><div v-if="!items.length" class="card p-10 text-center text-slate-500">暂无面试记录</div></div>
  </main>
</template>
<script setup lang="ts">
import {deleteInterview, getHistory} from '~/utils/api'
const items=ref<any[]>([]), deleting=ref<number|null>(null), error=ref('')
const statusLabel=(x:string)=>({created:'待开始',in_progress:'进行中',completed:'已完成',failed:'失败'}[x]||x)
const formatTime=(value:string)=>new Date(value).toLocaleString('zh-CN',{hour12:false})
const destination=(x:any)=>x.status==='completed'?`/interview/result/${x.id}`:`/interview/session/${x.id}`
async function remove(x:any){if(!window.confirm(`确定删除“${x.job_title}”这条面试记录吗？此操作会同时删除其简历文件，且不可恢复。`))return;deleting.value=x.id;error.value='';try{await deleteInterview(x.id);items.value=items.value.filter(item=>item.id!==x.id)}catch(e:any){error.value=e.message||'删除失败，请稍后重试'}finally{deleting.value=null}}
onMounted(async()=>{try{items.value=(await getHistory()).data}catch(e:any){error.value=e.message||'加载历史失败'}})
</script>
