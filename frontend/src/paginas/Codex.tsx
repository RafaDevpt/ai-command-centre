// Codex: «Sign in with ChatGPT» oficial por código de dispositivo. Sem tokens no browser.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { api, post } from '../api'
import { Ponto } from './Painel'

type Estado = { ok: boolean; instalado: boolean; plano?: string; conta?: string; nota?: string; login_pendente?: boolean }
type Login = { login_id: string; url: string; codigo: string }

export default function Codex() {
  const [e, setE] = useState<Estado | null>(null)
  const [login, setLogin] = useState<Login | null>(null)
  const [erro, setErro] = useState('')
  const ler = () => api<Estado>('/api/codex/status').then(setE).catch((x) => setErro(String(x.message)))
  useEffect(() => { ler() }, [])
  useEffect(() => {
    if (!login) return
    const t = setInterval(async () => {
      const n = await api<Estado>('/api/codex/status')
      setE(n)
      if (n.ok || !n.login_pendente) { setLogin(null) }
    }, 4000)
    return () => clearInterval(t)
  }, [login])

  const entrar = async () => {
    setErro('')
    try { setLogin(await post<Login>('/api/codex/login')) } catch (x: any) { setErro(x.message) }
  }
  const cancelar = async () => { if (login) await post('/api/codex/login/cancel', { login_id: login.login_id }); setLogin(null); ler() }
  const sair = async () => { if (confirm('Terminar a sessão do Codex neste servidor?')) { await post('/api/codex/logout'); ler() } }

  if (!e) return <p className="pequeno suave">Codex: a verificar…</p>
  return (
    <div>
      <p><Ponto ok={e.ok} /> Codex {e.ok ? `· ${e.conta ?? 'conta ChatGPT'} · plano ${e.plano ?? '?'}` : `· ${e.nota ?? ''}`}</p>
      {e.instalado && !e.ok && !login && <button className="primario" onClick={entrar}>Iniciar sessão com ChatGPT</button>}
      {login && <div className="aviso">
        <p>1. Abra <a href={login.url} target="_blank" rel="noreferrer noopener">{login.url}</a> (em qualquer dispositivo)</p>
        <p>2. Introduza o código <strong style={{ fontSize: '1.3em', letterSpacing: '.1em' }}>{login.codigo}</strong></p>
        <p className="pequeno">A página actualiza sozinha quando terminar. O código expira em poucos minutos.</p>
        <button className="secundario" onClick={cancelar}>Cancelar</button>
      </div>}
      {e.ok && <button className="secundario" onClick={sair}>Terminar sessão do Codex</button>}
      {e.ok && e.plano === 'go' && <p className="pequeno suave">ChatGPT Go: o Codex está incluído, mas com limites de utilização mais baixos do que Plus/Pro. Quando o limite acaba, o Codex devolve erro até o período renovar.</p>}
      <p className="pequeno suave">Login oficial da OpenAI; as credenciais ficam só em <code>agents/codex</code> no servidor (pasta 700) e nunca na base de dados nem no browser. O Codex corre em modo só-leitura e qualquer comando ou alteração de ficheiros pede aprovação.</p>
      {erro && <p className="aviso">{erro}</p>}
    </div>
  )
}
