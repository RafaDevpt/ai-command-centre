// Conversa unificada: escolher fornecedor/modelo/projecto, streaming por WebSocket,
// anexos e retoma de sessões. Created by Redfox using Claude
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, obterCsrf, patch, post } from '../api'

type Msg = { id?: number; papel: string; texto: string; fornecedor?: string | null; modelo?: string | null;
  anexos?: { id: string; nome: string }[] }
type Modelo = { id: string; fornecedor: string; nome: string; conversa?: boolean }
type Anexo = { id: string; nome: string; texto: boolean }

export default function Conversa() {
  const { id } = useParams()
  const navegar = useNavigate()
  const [sessao, setSessao] = useState<any>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [modelos, setModelos] = useState<Modelo[]>([])
  const [projectos, setProjectos] = useState<any[]>([])
  const [escolha, setEscolha] = useState('')
  const [procura] = useSearchParams()
  const [projecto, setProjecto] = useState(procura.get('projecto') ?? '')
  const [texto, setTexto] = useState('')
  const [anexos, setAnexos] = useState<Anexo[]>([])
  const [aResponder, setAResponder] = useState(false)
  const [erro, setErro] = useState('')
  const ws = useRef<WebSocket | null>(null)
  const fim = useRef<HTMLDivElement>(null)
  const pendente = useRef<{ sid: string; texto: string; anexos: Anexo[] } | null>(null)

  useEffect(() => {
    api<Modelo[]>('/api/models').then((m) => {
      const c = m.filter((x) => x.conversa !== false); setModelos(c)
      setEscolha((e) => e || (c[0] ? `${c[0].fornecedor}|${c[0].id}` : ''))
    }).catch(() => {})
    api('/api/projects').then(setProjectos).catch(() => {})
  }, [])

  useEffect(() => {
    setErro('')
    if (!id) { setSessao(null); if (!pendente.current) setMsgs([]); return }
    api(`/api/sessions/${id}`).then((s) => {
      // Sessão acabada de criar por enviar(): a resposta já está a chegar; não apagar.
      if (pendente.current?.sid === s.id) { pendente.current = null; setSessao(s); return }
      setSessao(s); setMsgs(s.mensagens); setEscolha(`${s.fornecedor}|${s.modelo}`); setProjecto(s.projecto_id ?? '')
    }).catch((e) => setErro(e.message))
  }, [id])

  useEffect(() => { fim.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  function ligar(): Promise<WebSocket> {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) return Promise.resolve(ws.current)
    return new Promise((ok, falha) => {
      const sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws/chat`)
      sock.onopen = () => { ws.current = sock; ok(sock) }
      sock.onerror = () => falha(new Error('Sem ligação ao servidor.'))
      sock.onclose = () => { ws.current = null; setAResponder(false) }
      sock.onmessage = (ev) => {
        const e = JSON.parse(ev.data)
        if (e.tipo === 'delta') setMsgs((m) => { const u = m[m.length - 1]; return [...m.slice(0, -1), { ...u, texto: u.texto + e.texto }] })
        else if (e.tipo === 'aprovacao') setMsgs((m) => [...m.slice(0, -1), { papel: 'aviso', texto: `🔐 Pedido de aprovação: ${e.resumo} — veja em Aprovações.` }, m[m.length - 1]])
        else if (e.tipo === 'aviso') setMsgs((m) => [...m.slice(0, -1), { papel: 'aviso', texto: e.texto }, m[m.length - 1]])
        else if (e.tipo === 'fim') { setAResponder(false); if (e.erro) setErro(e.erro)
          setMsgs((m) => { const u = m[m.length - 1]; return [...m.slice(0, -1), { ...u, id: e.mensagem_id, texto: u.texto || `⚠️ ${e.erro}` }] }) }
        else if (e.tipo === 'erro' || e.tipo === 'parado') { setAResponder(false); if (e.texto) setErro(e.texto) }
      }
    })
  }

  async function enviar(e?: React.FormEvent) {
    e?.preventDefault()
    if (!texto.trim() || aResponder || !escolha) return
    setErro('')
    let sid = id
    const [fornecedor, modelo] = escolha.split('|')
    try {
      if (!sid) {
        const s = await post('/api/sessions', { fornecedor, modelo, projecto_id: projecto || null })
        sid = s.id
        pendente.current = { sid: s.id, texto, anexos }
        navegar(`/conversa/${s.id}`)
      }
      const sock = await ligar()
      setMsgs((m) => [...m, { papel: 'user', texto, anexos }, { papel: 'assistant', texto: '', fornecedor, modelo }])
      setAResponder(true)
      sock.send(JSON.stringify({ tipo: 'enviar', csrf: obterCsrf(), sessao_id: sid, texto, anexos }))
      setTexto(''); setAnexos([])
    } catch (x: any) { setErro(x.message); setAResponder(false) }
  }

  async function anexar(f: FileList | null) {
    if (!f?.length) return
    const fd = new FormData(); fd.append('ficheiro', f[0])
    try { const a = await post<Anexo>('/api/attachments', fd); setAnexos((x) => [...x, a]) } catch (x: any) { setErro(x.message) }
  }

  const [fornecedorActual, modeloActual] = escolha.split('|')
  const bloqueado = !!sessao && sessao.estado === 'externa'

  return (
    <div className="conversa">
      <div className="barra-conversa">
        <select value={escolha} disabled={!!sessao} onChange={(e) => setEscolha(e.target.value)} aria-label="Modelo">
          {modelos.length === 0 && <option value="">Sem modelos</option>}
          {modelos.map((m) => <option key={`${m.fornecedor}|${m.id}`} value={`${m.fornecedor}|${m.id}`}>{m.fornecedor} · {m.nome}</option>)}
        </select>
        <select value={projecto} aria-label="Projecto" onChange={async (e) => {
          setProjecto(e.target.value)
          if (sessao) await patch(`/api/sessions/${sessao.id}`, { projecto_id: e.target.value })
        }}>
          <option value="">Sem projecto</option>
          {projectos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
        </select>
        {sessao && <button className="secundario" onClick={() => navegar('/conversa')}>Nova</button>}
      </div>
      <div className="mensagens">
        {msgs.length === 0 && <p className="suave centro">Escreva uma mensagem para começar. Responde: <b>{fornecedorActual} · {modeloActual}</b></p>}
        {msgs.map((m, i) => (
          <div key={m.id ?? `t${i}`} className={`msg ${m.papel}`}>
            {m.papel === 'assistant' && <div className="origem">{m.fornecedor} · {m.modelo}</div>}
            <div className="texto">{m.texto || (aResponder && i === msgs.length - 1 ? '…' : '')}</div>
            {!!m.anexos?.length && <div className="anexos">{m.anexos.map((a) => <span key={a.id}>📎 {a.nome}</span>)}</div>}
          </div>
        ))}
        <div ref={fim} />
      </div>
      {erro && <p className="aviso">{erro}</p>}
      {bloqueado ? <p className="suave">Sessão externa importada: só leitura.</p> : (
        <form className="compor" onSubmit={enviar}>
          {!!anexos.length && <div className="anexos">{anexos.map((a) => <span key={a.id}>📎 {a.nome}</span>)}</div>}
          <textarea value={texto} rows={2} placeholder="Mensagem…" onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !('ontouchstart' in window)) { e.preventDefault(); enviar() } }} />
          <div className="accoes">
            <label className="secundario anexar">📎<input type="file" hidden onChange={(e) => anexar(e.target.files)} /></label>
            {aResponder
              ? <button type="button" className="secundario" onClick={() => ws.current?.send(JSON.stringify({ tipo: 'parar', csrf: obterCsrf() }))}>Parar</button>
              : <button className="primario" disabled={!texto.trim()}>Enviar</button>}
          </div>
        </form>
      )}
    </div>
  )
}
