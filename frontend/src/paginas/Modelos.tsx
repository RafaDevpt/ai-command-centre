// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { api, bytes } from '../api'

export default function Modelos() {
  const [m, setM] = useState<any[]>([])
  const [det, setDet] = useState<Record<string, any>>({})
  useEffect(() => { api('/api/models').then(setM) }, [])
  return (
    <div>
      <p className="suave">Só modelos já instalados. Nada é descarregado automaticamente.</p>
      <div className="tabela">
        {m.map((x) => (
          <div key={`${x.fornecedor}${x.id}`} className="linha">
            <span><b>{x.nome}</b> <small>{x.fornecedor}</small></span>
            <small>{bytes(x.tamanho)} · {x.parametros ?? ''} {x.quantizacao ?? ''} · {x.carregado ? '🟢 em memória' : 'em disco'}
              {x.conversa === false && ' · só embeddings'}
              {det[x.id] && ` · contexto ${det[x.id].contexto_usado}/${det[x.id].contexto_max ?? '?'}`}</small>
            {x.fornecedor === 'ollama' && !det[x.id] && (
              <button className="ligacao" onClick={() => api(`/api/models/ollama/${encodeURIComponent(x.id)}`).then((d) => setDet((o) => ({ ...o, [x.id]: d })))}>Detalhes</button>)}
          </div>
        ))}
      </div>
    </div>
  )
}
