// Projectos: instruções, documentos, memória (com propostas dos agentes) e sessões.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, bytes, del, patch, post, quando } from '../api'

export function ListaProjectos() {
  const [lista, setLista] = useState<any[]>([])
  const [nome, setNome] = useState('')
  const ir = useNavigate()
  const ler = () => api('/api/projects').then(setLista)
  useEffect(() => { ler() }, [])
  return (
    <div>
      <form className="form-linha" onSubmit={async (e) => { e.preventDefault(); const p = await post('/api/projects', { nome }); setNome(''); ir(`/projectos/${p.id}`) }}>
        <input placeholder="Nome do novo projecto" value={nome} onChange={(e) => setNome(e.target.value)} required maxLength={120} />
        <button className="primario">Criar</button>
      </form>
      {lista.length === 0 && <p className="suave">Ainda não há projectos.</p>}
      {lista.map((p) => (
        <div key={p.id} className="linha">
          <Link to={`/projectos/${p.id}`}><span>{p.nome}</span>
            <small>{p.sessoes} sessões · {p.documentos} documentos{p.memoria_pendente ? ` · ${p.memoria_pendente} memórias por aprovar` : ''}</small></Link>
          {p.memoria_pendente > 0 && <span className="etiqueta pendente">memória pendente</span>}
        </div>
      ))}
    </div>
  )
}

export function Projecto() {
  const { id } = useParams()
  const ir = useNavigate()
  const [p, setP] = useState<any>(null)
  const [instr, setInstr] = useState('')
  const [docs, setDocs] = useState<any[]>([])
  const [mem, setMem] = useState<any[]>([])
  const [nota, setNota] = useState('')
  const [q, setQ] = useState('')
  const [res, setRes] = useState<any>(null)
  const [msg, setMsg] = useState('')
  const base = `/api/projects/${id}`
  const ler = async () => {
    const d = await api(base); setP(d); setInstr(d.instrucoes)
    setDocs(await api(`${base}/documents`)); setMem(await api(`${base}/memory`))
  }
  useEffect(() => { ler().catch(() => ir('/projectos')) }, [id])
  if (!p) return <p className="suave">A carregar…</p>
  const pendentes = mem.filter((m) => !m.aprovada)
  const carregar = async (f: FileList | null) => {
    for (const fich of Array.from(f ?? [])) { const fd = new FormData(); fd.append('ficheiro', fich); await post(`${base}/documents`, fd) }
    ler()
  }
  const apagarProjecto = async () => {
    const n = prompt(`Para apagar, escreva o nome do projecto («${p.nome}»). As sessões ficam, sem projecto; os ficheiros no servidor não são apagados.`)
    if (n) { try { await api(base, { method: 'DELETE', body: JSON.stringify({ confirmar: n }) }); ir('/projectos') } catch (e: any) { setMsg(e.message) } }
  }
  return (
    <div className="grelha">
      <article className="largo">
        <h2>{p.nome}</h2>
        <p className="pequeno suave">Instruções dadas a todos os modelos e agentes nas conversas deste projecto.</p>
        <textarea rows={5} style={{ width: '100%' }} value={instr} onChange={(e) => setInstr(e.target.value)} />
        <div className="form-linha">
          <button className="primario" onClick={async () => { await patch(base, { instrucoes: instr }); setMsg('Guardado.') }}>Guardar instruções</button>
          <Link className="secundario" to={`/conversa?projecto=${p.id}`}>Nova conversa neste projecto</Link>
          <button className="ligacao" onClick={apagarProjecto}>Apagar projecto</button>
        </div>
        {msg && <p className="suave">{msg}</p>}
      </article>
      {pendentes.length > 0 && <article className="largo">
        <h3>Memória proposta pelos agentes ({pendentes.length})</h3>
        <p className="pequeno suave">Só entra no contexto depois de aprovada.</p>
        {pendentes.map((m) => <div key={m.id} className="linha"><span>{m.texto}<br /><small>{m.origem} · {quando(m.criada)}</small></span>
          <span><button className="primario" onClick={async () => { await post(`${base}/memory/${m.id}/approve`); ler() }}>Aprovar</button>{' '}
            <button className="secundario" onClick={async () => { await del(`${base}/memory/${m.id}`); ler() }}>Rejeitar</button></span></div>)}
      </article>}
      <article>
        <h3>Memória aprovada</h3>
        <form className="form-linha" onSubmit={async (e) => { e.preventDefault(); await post(`${base}/memory`, { texto: nota }); setNota(''); ler() }}>
          <input placeholder="Nova nota (facto, decisão, resumo)…" value={nota} onChange={(e) => setNota(e.target.value)} required />
          <button className="secundario">Juntar</button>
        </form>
        {mem.filter((m) => m.aprovada).map((m) => <div key={m.id} className="linha"><span className="pequeno">{m.texto}</span>
          <button className="ligacao" onClick={async () => { if (confirm('Remover esta memória?')) { await del(`${base}/memory/${m.id}`); ler() } }}>remover</button></div>)}
        <button className="ligacao" onClick={async () => { try { const r = await post(`${base}/memory/index`); setMsg(`${r.indexadas} memórias indexadas.`) } catch (e: any) { setMsg(e.message) } }}>Indexar para pesquisa semântica</button>
      </article>
      <article>
        <h3>Documentos</h3>
        <label className="secundario anexar">Carregar documentos<input type="file" multiple hidden onChange={(e) => carregar(e.target.files)} /></label>
        {docs.map((d) => <div key={d.id} className="linha"><span className="pequeno">{d.nome}<br /><small>{bytes(d.tamanho)} · {d.tem_texto ? 'texto extraído' : 'sem texto'} · {quando(d.criado)}</small></span>
          <button className="ligacao" onClick={async () => { if (confirm(`Remover «${d.nome}»?`)) { await del(`${base}/documents/${d.id}`); ler() } }}>remover</button></div>)}
      </article>
      <article>
        <h3>Pesquisar neste projecto</h3>
        <form className="form-linha" onSubmit={async (e) => { e.preventDefault(); setRes(await api(`${base}/search?q=${encodeURIComponent(q)}`)) }}>
          <input placeholder="Documentos e memória…" value={q} onChange={(e) => setQ(e.target.value)} required />
          <button className="secundario">Procurar</button>
        </form>
        {res && <>{res.documentos.map((d: any) => <p key={d.id} className="pequeno"><strong>{d.nome}</strong>: {d.excerto}</p>)}
          {res.memoria.map((m: any) => <p key={m.id} className="pequeno">🧠 {m.texto}</p>)}
          {!res.documentos.length && !res.memoria.length && <p className="suave">Nada encontrado.</p>}</>}
      </article>
      <article>
        <h3>Sessões</h3>
        {p.sessoes.length === 0 && <p className="suave pequeno">Nenhuma ainda.</p>}
        {p.sessoes.map((s: any) => <div key={s.id} className="linha"><Link to={`/conversa/${s.id}`}><span>{s.titulo}</span><small>{s.fornecedor} · {s.modelo} · {quando(s.ultima)}</small></Link></div>)}
      </article>
    </div>
  )
}
