// Agentes (Codex e Ollama), execuções e colaboração A → B → consolidação.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { api, del, patch, post, quando } from '../api'

export default function Agentes() {
  const [ags, setAgs] = useState<any[]>([])
  const [modelos, setModelos] = useState<any[]>([])
  const [projs, setProjs] = useState<any[]>([])
  const [tarefas, setTarefas] = useState<any[]>([])
  const [runs, setRuns] = useState<Record<string, any[]>>({})
  const [aberta, setAberta] = useState<any>(null)
  const [f, setF] = useState({ pedido: '', projecto_id: '', primeiro: '', segundo: '' })
  const [pedidoAg, setPedidoAg] = useState<Record<string, string>>({})
  const [novo, setNovo] = useState({ nome: '', fornecedor: 'ollama', modelo: '', papel: '' })
  const [erro, setErro] = useState('')
  const ler = async () => {
    const a = await api('/api/agents'); setAgs(a)
    setTarefas(await api('/api/collab'))
    const rs: Record<string, any[]> = {}
    for (const x of a) rs[x.id] = await api(`/api/agents/${x.id}/runs`)
    setRuns(rs)
    setF((v) => ({ ...v, primeiro: v.primeiro || a.find((x: any) => x.fornecedor === 'codex')?.id || a[0]?.id || '', segundo: v.segundo || a.find((x: any) => x.fornecedor === 'ollama')?.id || '' }))
  }
  useEffect(() => { ler(); api('/api/models').then(setModelos); api('/api/projects').then(setProjs) }, [])
  const aCorrer = tarefas.some((t) => t.estado === 'a-correr' || t.estado === 'pendente') || Object.values(runs).flat().some((r) => r.estado === 'a-correr')
  useEffect(() => { if (!aCorrer) return; const t = setInterval(ler, 4000); return () => clearInterval(t) }, [aCorrer])
  const proj = (
    <select value={f.projecto_id} onChange={(e) => setF({ ...f, projecto_id: e.target.value })}>
      <option value="">Sem projecto</option>{projs.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
    </select>)
  return (
    <div className="grelha">
      <article className="largo">
        <h2>Novo agente</h2>
        <p className="pequeno suave">Cada agente é um fornecedor + modelo + papel. O coordenador da Equipa usa o papel para distribuir o trabalho. Todos começam só de leitura.</p>
        <form className="form-linha" onSubmit={async (e) => { e.preventDefault(); setErro(''); try { await post('/api/agents', novo); setNovo({ nome: '', fornecedor: 'ollama', modelo: '', papel: '' }); ler() } catch (x: any) { setErro(x.message) } }}>
          <input placeholder="Nome (ex.: Revisor PT-PT)" value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} required maxLength={80} />
          <select value={novo.fornecedor} onChange={(e) => setNovo({ ...novo, fornecedor: e.target.value, modelo: '' })}><option value="ollama">Ollama</option><option value="codex">Codex</option></select>
          <select value={novo.modelo} onChange={(e) => setNovo({ ...novo, modelo: e.target.value })}><option value="">automático</option>
            {modelos.filter((m) => m.fornecedor === novo.fornecedor && m.conversa).map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}</select>
          <input placeholder="Papel (o que faz bem)" value={novo.papel} onChange={(e) => setNovo({ ...novo, papel: e.target.value })} />
          <button className="primario">Criar</button>
        </form>
        {erro && <p className="aviso">{erro}</p>}
      </article>
      {ags.map((a) => (
        <article key={a.id}>
          <h2>{a.nome} <span className="etiqueta">{a.perfil === 'so-leitura' ? 'só leitura' : a.perfil}</span></h2>
          <p className="pequeno suave">{a.fornecedor}{a.capacidades.length ? ` · ${a.capacidades.join(', ')}` : ''}</p>
          <textarea rows={2} style={{ width: '100%' }} defaultValue={a.papel} placeholder="Papel na equipa (ex.: tarefas básicas)" onBlur={async (e) => { if (e.target.value !== a.papel) { await patch(`/api/agents/${a.id}`, { papel: e.target.value }); ler() } }} />
          <label className="pequeno">Modelo{' '}
            <select value={a.modelo ?? ''} onChange={async (e) => { await patch(`/api/agents/${a.id}`, { modelo: e.target.value }); ler() }}>
              <option value="">automático</option>
              {modelos.filter((m) => m.fornecedor === a.fornecedor && m.conversa).map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
            </select></label>{' '}
          <label className="pequeno"><input type="checkbox" checked={a.activo} onChange={async (e) => { await patch(`/api/agents/${a.id}`, { activo: e.target.checked }); ler() }} /> activo</label>
          <form className="form-linha" style={{ marginTop: 10 }} onSubmit={async (e) => { e.preventDefault(); await post(`/api/agents/${a.id}/run`, { pedido: pedidoAg[a.id], projecto_id: f.projecto_id || null }); setPedidoAg({ ...pedidoAg, [a.id]: '' }); ler() }}>
            <input placeholder="Pedido para este agente…" value={pedidoAg[a.id] ?? ''} onChange={(e) => setPedidoAg({ ...pedidoAg, [a.id]: e.target.value })} required />
            <button className="secundario" disabled={!a.activo}>Executar</button>
          </form>
          {!['Codex', 'Ollama'].includes(a.nome) && <button className="ligacao" onClick={async () => { if (confirm(`Apagar o agente «${a.nome}»?`)) { try { await del(`/api/agents/${a.id}`); ler() } catch (x: any) { setErro(x.message) } } }}>apagar agente</button>}
          {(runs[a.id] ?? []).slice(0, 5).map((r) => <details key={r.id}><summary className="pequeno"><span className={`etiqueta ${r.estado}`}>{r.estado}</span> {r.papel} · {quando(r.inicio)}</summary><pre className="saida">{r.saida || '…'}</pre></details>)}
        </article>
      ))}
      <article className="largo">
        <h2>Colaboração</h2>
        <p className="pequeno suave">O agente A analisa, o agente B revê, o servidor compara as duas respostas e o agente A consolida. Corre em segundo plano; pode sair desta página.</p>
        <form onSubmit={async (e) => { e.preventDefault(); await post('/api/collab', { ...f, projecto_id: f.projecto_id || null }); setF({ ...f, pedido: '' }); ler() }}>
          <textarea rows={3} style={{ width: '100%' }} placeholder="O que querem que analisem?" value={f.pedido} onChange={(e) => setF({ ...f, pedido: e.target.value })} required />
          <div className="form-linha">
            <label className="pequeno">A (análise) <select value={f.primeiro} onChange={(e) => setF({ ...f, primeiro: e.target.value })}>{ags.map((a) => <option key={a.id} value={a.id}>{a.nome}</option>)}</select></label>
            <label className="pequeno">B (revisão) <select value={f.segundo} onChange={(e) => setF({ ...f, segundo: e.target.value })}>{ags.map((a) => <option key={a.id} value={a.id}>{a.nome}</option>)}</select></label>
            {proj}
            <button className="primario">Iniciar</button>
          </div>
        </form>
        {tarefas.map((t) => <div key={t.id} className="linha">
          <button className="ligacao" style={{ textAlign: 'left', flex: 1 }} onClick={async () => setAberta(await api(`/api/collab/${t.id}`))}>{t.pedido.slice(0, 90)}<br /><small>{quando(t.criada)}</small></button>
          <span className={`etiqueta ${t.estado}`}>{t.estado}</span></div>)}
        {aberta && <div style={{ marginTop: 12 }}>
          <h3>{aberta.pedido.slice(0, 120)}</h3>
          {aberta.passos.map((p: any) => <details key={p.id}><summary className="pequeno"><span className={`etiqueta ${p.estado}`}>{p.estado}</span> {p.papel} · {ags.find((a) => a.id === p.agente_id)?.nome}</summary><pre className="saida">{p.saida}</pre></details>)}
          <pre className="saida">{aberta.resultado || 'A correr…'}</pre>
          <button className="ligacao" onClick={() => setAberta(null)}>Fechar</button>
        </div>}
      </article>
    </div>
  )
}
