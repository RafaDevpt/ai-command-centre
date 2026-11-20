// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, bytes, quando } from '../api'

export function Ponto({ ok }: { ok?: boolean | null }) {
  return <i className={`ponto ${ok == null ? '' : ok ? 'bom' : 'mau'}`} aria-hidden />
}

export default function Painel() {
  const [d, setD] = useState<any>(null)
  const [modelos, setModelos] = useState<any[]>([])
  useEffect(() => {
    const ler = () => { api('/api/dashboard').then(setD).catch(() => {}); api('/api/models').then(setModelos).catch(() => {}) }
    ler(); const t = setInterval(ler, 15000); return () => clearInterval(t)
  }, [])
  if (!d) return <p className="suave">A carregar…</p>
  const f = d.fornecedores, r = d.recursos
  return (
    <section className="grelha">
      <article>
        <h2>Fornecedores</h2>
        <p><Ponto ok={f.ollama.ok} /> Ollama {f.ollama.versao ?? ''}</p>
        <p><Ponto ok={f.codex.ok} /> Codex {f.codex.conta ? `· ${f.codex.conta}` : f.codex.nota ? `· ${f.codex.nota}` : ''}</p>
        <p><Ponto ok={null} /> Claude · aplicação oficial separada</p>
      </article>
      <article>
        <h2>Actividade</h2>
        <p><Link to="/aprovacoes">Aprovações pendentes: <b>{d.aprovacoes_pendentes}</b></Link></p>
        <p><Link to="/agentes">Tarefas a correr: <b>{d.tarefas_a_correr}</b></Link></p>
        <p>Modelos disponíveis: <b>{modelos.filter((m) => m.conversa !== false).length}</b>
          {' '}· carregado: {modelos.find((m) => m.carregado)?.nome ?? 'nenhum'}</p>
      </article>
      <article>
        <h2>Servidor</h2>
        <Barra rotulo="CPU" pct={r.cpu_percent} />
        <Barra rotulo={`RAM · livre ${bytes(r.ram.disponivel)}`} pct={r.ram.percent} />
        <Barra rotulo={`Disco /data · livre ${bytes(r.disco.livre)}`} pct={r.disco.percent} />
      </article>
      <article className="largo">
        <h2>Sessões recentes</h2>
        {d.sessoes_recentes.length === 0 && <p className="suave">Ainda não há conversas. <Link to="/conversa">Começar</Link></p>}
        {d.sessoes_recentes.map((s: any) => (
          <Link key={s.id} className="linha" to={`/conversa/${s.id}`}>
            <span>{s.titulo}</span><small>{s.fornecedor} · {s.modelo} · {quando(s.ultima)}</small>
          </Link>
        ))}
      </article>
    </section>
  )
}

function Barra({ rotulo, pct }: { rotulo: string; pct: number }) {
  return (
    <div className="barra"><span>{rotulo}</span><b>{pct.toFixed(0)} %</b>
      <div><i style={{ width: `${Math.min(100, pct)}%` }} /></div></div>
  )
}
