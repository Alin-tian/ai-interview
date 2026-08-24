import { defineStore } from 'pinia'
export const useInterviewStore = defineStore('interview', () => {
  const session = ref<any>(null), logs = ref<string[]>([]), running = ref(false)
  function applyQuestion(turn:any) { if (!session.value) session.value={turns:[]}; const exists=session.value.turns.find((x:any)=>x.id===turn.id); if(!exists) session.value.turns.push(turn); else Object.assign(exists,turn) }
  function applyEvaluation(data:any) { const turn=session.value?.turns.find((x:any)=>x.id===data.turn_id); if(turn) turn.evaluation=data.evaluation }
  return {session, logs, running, applyQuestion, applyEvaluation}
})
