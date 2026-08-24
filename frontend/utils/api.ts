// Do not call useRuntimeConfig at module scope. Utility modules are imported
// while Nuxt is resolving routes, before a Nuxt/Vue setup context exists.
// The public runtime config is available on the client payload instead.
function apiBase() {
  const runtime = (globalThis as any).__NUXT__?.config?.public?.apiBase
  return runtime || 'http://localhost:8010/api/v1'
}
export async function createInterview(form: FormData) { const r = await fetch(`${apiBase()}/interviews`, { method: 'POST', body: form }); if (!r.ok) throw new Error(await r.text()); return r.json() }
export async function getInterview(id: string) { const r = await fetch(`${apiBase()}/interviews/${id}`); if (!r.ok) throw new Error(await r.text()); return r.json() }
export async function getHistory() { const r = await fetch(`${apiBase()}/interviews/history/list`); if (!r.ok) throw new Error(await r.text()); return r.json() }
export async function deleteInterview(id: string | number) { const r = await fetch(`${apiBase()}/interviews/${id}`, {method:'DELETE'}); if (!r.ok) throw new Error(await r.text()); return r.json() }
export async function ask(id: string, question: string) { const r = await fetch(`${apiBase()}/interviews/${id}/ask`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question}) }); if (!r.ok) throw new Error(await r.text()); return r.json() }
export async function stream(url: string, body?: any, onEvent?: (name:string, data:any)=>void) {
  const r = await fetch(`${apiBase()}${url}`, {method:'POST', headers: body ? {'Content-Type':'application/json'} : undefined, body: body ? JSON.stringify(body) : undefined})
  if (!r.ok || !r.body) throw new Error(await r.text())
  const reader = r.body.getReader(), decoder = new TextDecoder(); let buffer=''
  while(true) { const {done,value}=await reader.read(); if(done) break; buffer += decoder.decode(value,{stream:true}); const parts=buffer.split('\n\n'); buffer=parts.pop()||''; for(const part of parts){ let name='', raw=''; for(const line of part.split('\n')){if(line.startsWith('event: '))name=line.slice(7); if(line.startsWith('data: '))raw=line.slice(6)} if(name) onEvent?.(name, JSON.parse(raw||'{}')) } }
}
