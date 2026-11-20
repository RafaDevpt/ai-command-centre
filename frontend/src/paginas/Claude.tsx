// Claude: aplicação oficial externa. Atalho, estado das importações e importação da exportação oficial.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { api, post, quando } from '../api'

export default function Claude() {
  const [e, setE] = useState<any>(null)
  const [msg, setMsg] = useState('')
  const [reg, setReg] = useState({ titulo: '', ligacao: '', notas: '' })
  const ler = () => api('/api/claude/status').then(setE)
  useEffect(() => { ler() }, [])
  const importar = async (f: FileList | null) => {
    if (!f?.[0]) return
    setMsg('A importar…')
    const fd = new FormData(); fd.append('ficheiro', f[0])
    try { const r = await post('/api/claude/import', fd); setMsg(`Importadas ${r.novas} conversas (${r.mensagens} mensagens); ${r.repetidas} já existiam.`); ler() } catch (x: any) { setMsg(x.message) }
  }
  return (
    <article>
      <h2>Claude (aplicação externa)</h2>
      <p><a className="primario" href="https://claude.ai" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-block', textDecoration: 'none' }}>Abrir o Claude ↗</a></p>
      <p className="pequeno suave">O Claude usa-se na aplicação ou no site oficiais, com a sua conta. Este servidor não liga ao Claude: não guarda credenciais, não lê cookies e não automatiza o browser. Por isso não mostra o estado da conta nem os limites.</p>
      {e && <p className="pequeno">{e.sessoes_importadas} sessões externas guardadas{e.ultima_importacao ? ` · última ${quando(e.ultima_importacao)}` : ''}.</p>}
      <h3>Importar a exportação oficial</h3>
      <p className="pequeno suave">No claude.ai: Definições → Privacidade → Exportar dados. Recebe um ZIP por email; carregue-o aqui (ou só o <code>conversations.json</code>). As conversas ficam só de leitura, em Sessões → Externas.</p>
      <label className="secundario anexar">Escolher ZIP ou JSON<input type="file" accept=".zip,.json,application/zip,application/json" hidden onChange={(x) => importar(x.target.files)} /></label>
      {msg && <p className="pequeno">{msg}</p>}
      <h3>Registar uma sessão à mão</h3>
      <form onSubmit={async (x) => { x.preventDefault(); try { await post('/api/claude/sessions', { titulo: reg.titulo, ligacao: reg.ligacao || null, notas: reg.notas }); setReg({ titulo: '', ligacao: '', notas: '' }); setMsg('Sessão registada.'); ler() } catch (y: any) { setMsg(y.message) } }}>
        <div className="form-linha">
          <input placeholder="Título" value={reg.titulo} onChange={(x) => setReg({ ...reg, titulo: x.target.value })} required maxLength={200} />
          <input placeholder="https://claude.ai/chat/… (opcional)" value={reg.ligacao} onChange={(x) => setReg({ ...reg, ligacao: x.target.value })} pattern="https://claude\.ai/.*" />
        </div>
        <textarea rows={3} style={{ width: '100%' }} placeholder="Notas ou resumo (opcional)" value={reg.notas} onChange={(x) => setReg({ ...reg, notas: x.target.value })} />
        <button className="secundario">Registar</button>
      </form>
    </article>
  )
}
