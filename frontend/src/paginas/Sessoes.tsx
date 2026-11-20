// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, patch, quando } from '../api'

export default function Sessoes() {
  const [lista, setLista] = useState<any[]>([])
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState('activa')
  const ler = () => api(`/api/sessions?${new URLSearchParams({ ...(q ? { q } : {}), ...(estado ? { estado } : {}) })}`).then(setLista)
  useEffect(() => { ler() }, [estado])
  return (
    <div>
      <form className="filtros" onSubmit={(e) => { e.preventDefault(); ler() }}>
        <input placeholder="Pesquisar no histórico…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="activa">Activas</option><option value="arquivada">Arquivadas</option>
          <option value="externa">Externas (Claude)</option><option value="">Todas</option>
        </select>
        <button className="secundario">Procurar</button>
      </form>
      {lista.length === 0 && <p className="suave">Nada encontrado.</p>}
      {lista.map((s) => (
        <div key={s.id} className="linha">
          <Link to={`/conversa/${s.id}`}><span>{s.titulo}</span>
            <small>{s.fornecedor} · {s.modelo} · criada {quando(s.criada)} · última {quando(s.ultima)} · {s.estado}</small></Link>
          {s.estado !== 'externa' && (
            <button className="ligacao" onClick={async () => { await patch(`/api/sessions/${s.id}`, { estado: s.estado === 'activa' ? 'arquivada' : 'activa' }); ler() }}>
              {s.estado === 'activa' ? 'Arquivar' : 'Reactivar'}</button>)}
        </div>
      ))}
    </div>
  )
}
