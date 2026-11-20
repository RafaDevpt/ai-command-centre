// Definições: conta, segurança, fornecedores (incl. login do Codex), Claude, cópias e sistema.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { api, bytes, post, quando } from '../api'
import { Ponto } from './Painel'
import Codex from './Codex'
import Claude from './Claude'

export default function Definicoes() {
  const [sessoes, setSessoes] = useState<any[]>([])
  const [estado, setEstado] = useState<any>(null)
  const [atual, setAtual] = useState(''); const [nova, setNova] = useState(''); const [msg, setMsg] = useState('')
  const ler = () => { api('/api/auth/sessions').then(setSessoes); api('/api/dashboard').then(setEstado) }
  useEffect(() => { ler() }, [])
  async function mudar(e: React.FormEvent) {
    e.preventDefault(); setMsg('')
    try { await post('/api/auth/password', { atual, nova }); setMsg('Palavra-passe alterada; as outras sessões foram terminadas.'); ler() }
    catch (x: any) { setMsg(x.message) } finally { setAtual(''); setNova('') }
  }
  return (
    <div className="definicoes">
      <article>
        <h2>Conta e segurança</h2>
        <form onSubmit={mudar} className="form-linha">
          <input type="password" autoComplete="current-password" placeholder="Palavra-passe actual" value={atual} onChange={(e) => setAtual(e.target.value)} required />
          <input type="password" autoComplete="new-password" placeholder="Nova (mín. 12)" minLength={12} value={nova} onChange={(e) => setNova(e.target.value)} required />
          <button className="secundario">Mudar</button>
        </form>
        {msg && <p className="suave">{msg}</p>}
        <h3>Dispositivos com sessão aberta</h3>
        {sessoes.map((s) => <p key={s.id} className="pequeno">{s.actual ? '● esta' : '○'} · {s.dispositivo.slice(0, 60) || 'desconhecido'} · última {quando(s.ultima)}</p>)}
        <button className="secundario" onClick={async () => { await post('/api/auth/sessions/terminar-outras'); ler() }}>Terminar as outras sessões</button>
      </article>
      <article>
        <h2>Fornecedores</h2>
        {estado && <>
          <p><Ponto ok={estado.fornecedores.ollama.ok} /> Ollama {estado.fornecedores.ollama.versao ?? ''} · 127.0.0.1:11434 (instalação existente, não gerida aqui)</p>
        </>}
        <Codex />
      </article>
      <Claude />
      <article>
        <h2>Sistema e cópias de segurança</h2>
        {estado && <p className="pequeno">RAM livre {bytes(estado.recursos.ram.disponivel)} · disco livre {bytes(estado.recursos.disco.livre)} · CPU {estado.recursos.cpu_percent.toFixed(0)} %</p>}
        <p className="pequeno">Cópias da base de dados: <code>scripts/backup.sh</code> no servidor (ver docs/BACKUP-RESTORE.md).
          As credenciais dos fornecedores ficam fora da base de dados, em <code>agents/</code>.</p>
      </article>
    </div>
  )
}
