// Created by Redfox using Claude
import { useState } from 'react'
import { post, definirCsrf } from '../api'

export default function Login({ entrou }: { entrou: (nome: string) => void }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [erro, setErro] = useState('')
  const [aEnviar, setAEnviar] = useState(false)
  async function enviar(e: React.FormEvent) {
    e.preventDefault(); setErro(''); setAEnviar(true)
    try {
      const r = await post<{ username: string; csrf: string }>('/api/auth/login', { username: u, password: p })
      definirCsrf(r.csrf); entrou(r.username)
    } catch (x: any) { setErro(x.message) } finally { setAEnviar(false); setP('') }
  }
  return (
    <div className="login">
      <form onSubmit={enviar}>
        <div className="marca grande">◎ Command Centre</div>
        <label>Utilizador<input autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></label>
        <label>Palavra-passe<input type="password" autoComplete="current-password" value={p}
          onChange={(e) => setP(e.target.value)} required /></label>
        {erro && <p className="aviso">{erro}</p>}
        <button className="primario" disabled={aEnviar}>{aEnviar ? 'A entrar…' : 'Entrar'}</button>
      </form>
    </div>
  )
}
