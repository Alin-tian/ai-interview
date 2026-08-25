// Do not call useRuntimeConfig at module scope. Utility modules are imported
// while Nuxt is resolving routes, before a Nuxt/Vue setup context exists.
// The public runtime config is available on the client payload instead.
function apiBase() {
  const runtime = (globalThis as any).__NUXT__?.config?.public?.apiBase
  return runtime || 'http://localhost:8010/api/v1'
}

async function responseError(response: Response): Promise<Error> {
  const text = await response.text()
  try {
    const payload = JSON.parse(text)
    return new Error(payload.detail || payload.error || text || `请求失败（${response.status}）`)
  } catch {
    return new Error(text || `请求失败（${response.status}）`)
  }
}

export async function createInterview(form: FormData) { const r = await fetch(`${apiBase()}/interviews`, { method: 'POST', body: form }); if (!r.ok) throw await responseError(r); return r.json() }
export async function getInterview(id: string) { const r = await fetch(`${apiBase()}/interviews/${id}`); if (!r.ok) throw await responseError(r); return r.json() }
export async function getHistory() { const r = await fetch(`${apiBase()}/interviews/history/list`); if (!r.ok) throw await responseError(r); return r.json() }
export async function deleteInterview(id: string | number) { const r = await fetch(`${apiBase()}/interviews/${id}`, {method:'DELETE'}); if (!r.ok) throw await responseError(r); return r.json() }
export async function ask(id: string, question: string) { const r = await fetch(`${apiBase()}/interviews/${id}/ask`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question}) }); if (!r.ok) throw await responseError(r); return r.json() }

export async function stream(url: string, body?: any, onEvent?: (name:string, data:any)=>void) {
  const r = await fetch(`${apiBase()}${url}`, {method:'POST', headers: body ? {'Content-Type':'application/json'} : undefined, body: body ? JSON.stringify(body) : undefined})
  if (!r.ok) throw await responseError(r)
  if (!r.body) throw new Error('服务器未返回工作流数据')

  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (block: string) => {
    let name = ''
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) name = line.slice(6).trimStart()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!name) return
    const raw = dataLines.join('\n')
    try {
      onEvent?.(name, raw ? JSON.parse(raw) : {})
    } catch {
      throw new Error(`无法解析 Agent 工作流事件：${name}`)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) dispatch(part)
    if (done) break
  }
  if (buffer.trim()) dispatch(buffer)
}
