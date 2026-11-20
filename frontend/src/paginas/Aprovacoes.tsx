// Aprovações (obrigatórias para comandos, ficheiros, instalações e configuração) e registo de auditoria.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, post, quando } from '../api'

export default function Aprovacoes() {
  const [d, setD] = useState<any>({ pendentes: 0, itens: [] })
  const [estado, setEstado] = useState('pendente')
  const [audit, setAudit] = useState<any[] | null>(null)
  const [erro, setErro] = useState('')
  const ler = () => api(`/api/approvals${estado ? `?estado=${estado}` : ''}`).then(setD)
  useEffect(() => { ler(); const t = setInterval(ler, 5000); return () => clearInterval(t) }, [estado])
  const decidir = async (id: string, decisao: string) => {
    setErro('')
    try { await post(`/api/approvals/${id}`, { decisao }) } catch (e: any) { setErro(e.message) }
    ler()
  }
  return (
    <div>
      <div className="filtros">
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="pendente">Pendentes ({d.pendentes})</option><option value="">Todas</option>
          <option value="aprovada">Aprovadas</option><option value="executada">Executadas</option>
          <option value="rejeitada">Rejeitadas</option><option value="expirada">Expiradas</option><option value="falhou">Falharam</option>
        </select>
        <button className="secundario" onClick={async () => setAudit(audit ? null : await api('/api/audit'))}>{audit ? 'Esconder auditoria' : 'Registo de auditoria'}</button>
      </div>
      {erro && <p className="aviso">{erro}</p>}
      {d.itens.length === 0 && <p className="suave">Nada {estado === 'pendente' ? 'à espera de aprovação' : 'aqui'}.</p>}
      {d.itens.map((a: any) => (
        <article key={a.id} style={{ marginBottom: 10 }}>
          <p><span className={`etiqueta ${a.estado}`}>{a.estado}</span> <span className="etiqueta">{a.tipo}</span> <strong>{a.resumo}</strong></p>
          <p className="pequeno suave">{a.origem} · {quando(a.criada)}{a.sessao_id && <> · <Link to={`/conversa/${a.sessao_id}`}>ver conversa</Link></>}{a.decidida && ` · decidida por ${a.decidida_por} em ${quando(a.decidida)}`}</p>
          <details><summary className="pequeno">Detalhes</summary><pre className="saida">{JSON.stringify(a.detalhe, null, 2)}</pre></details>
          {a.resultado && <pre className="saida">{a.resultado}</pre>}
          {a.estado === 'pendente' && <div className="form-linha">
            <button className="primario" onClick={() => decidir(a.id, 'aprovar')}>Aprovar</button>
            <button className="secundario" onClick={() => decidir(a.id, 'rejeitar')}>Rejeitar</button>
            <span className="pequeno suave">Sem decisão em 15 min, é recusada automaticamente.</span>
          </div>}
        </article>
      ))}
      {audit && <article><h3>Auditoria (últimos 200)</h3>
        {audit.map((x) => <p key={x.id} className="pequeno">{quando(x.quando)} · <strong>{x.quem}</strong> · {x.accao} <span className="suave">{JSON.stringify(x.detalhe)}</span></p>)}
      </article>}
    </div>
  )
}
