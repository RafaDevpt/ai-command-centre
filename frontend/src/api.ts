// Cliente da API: cookies de sessão + cabeçalho anti-CSRF. Created by Redfox using Claude
let csrf = ''
export const definirCsrf = (t: string) => { csrf = t }
export const obterCsrf = () => csrf

export class ErroApi extends Error {
  estado: number
  constructor(estado: number, mensagem: string) { super(mensagem); this.estado = estado }
}

export async function api<T = any>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const cabecalhos: Record<string, string> = { ...(opcoes.headers as Record<string, string> || {}) }
  if (opcoes.method && opcoes.method !== 'GET') cabecalhos['X-CSRF-Token'] = csrf
  if (opcoes.body && !(opcoes.body instanceof FormData)) cabecalhos['Content-Type'] = 'application/json'
  const r = await fetch(caminho, { ...opcoes, headers: cabecalhos, credentials: 'same-origin' })
  if (r.status === 401 && !caminho.startsWith('/api/auth/login')) {
    window.dispatchEvent(new Event('aicc:sessao-expirada'))
  }
  const dados = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text()
  if (!r.ok) {
    const detalhe = typeof dados === 'object' && dados?.detail
    throw new ErroApi(r.status, typeof detalhe === 'string' ? detalhe : `Erro ${r.status}`)
  }
  return dados as T
}

export const post = <T = any>(caminho: string, corpo?: unknown) =>
  api<T>(caminho, { method: 'POST', body: corpo instanceof FormData ? corpo : JSON.stringify(corpo ?? {}) })
export const patch = <T = any>(caminho: string, corpo: unknown) =>
  api<T>(caminho, { method: 'PATCH', body: JSON.stringify(corpo) })
export const del = <T = any>(caminho: string) => api<T>(caminho, { method: 'DELETE' })

export const bytes = (n?: number | null) =>
  n == null ? '—' : n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(0)} MB` : `${Math.round(n / 1e3)} kB`
export const quando = (iso?: string) => iso ? new Date(iso).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' }) : ''
