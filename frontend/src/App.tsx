// Casca da aplicação: login obrigatório, barra lateral, rotas e navegação móvel.
// Created by Redfox using Claude
import { useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api, definirCsrf, post } from './api'
import Login from './paginas/Login'
import Painel from './paginas/Painel'
import Conversa from './paginas/Conversa'
import Sessoes from './paginas/Sessoes'
import Modelos from './paginas/Modelos'
import Definicoes from './paginas/Definicoes'
import { PAGINAS_EXTRA } from './paginas/extra'

const SECCOES: [string, string][] = [
  ['/equipa', 'Colaboração'], ['/conversa', 'Conversa'], ['/painel', 'Painel'], ['/sessoes', 'Sessões'], ['/projectos', 'Projectos'],
  ['/modelos', 'Modelos'], ['/agentes', 'Agentes'], ['/aprovacoes', 'Aprovações'], ['/definicoes', 'Definições'],
]

function Casca({ nome, sair }: { nome: string; sair: () => void }) {
  const [menu, setMenu] = useState(false)
  const local = useLocation()
  useEffect(() => setMenu(false), [local.pathname])
  const titulo = SECCOES.find(([c]) => c !== '/' && local.pathname.startsWith(c))?.[1] ?? 'Painel'
  return (
    <div className={`casca ${menu ? 'menu-aberto' : ''}`}>
      <aside className="lateral">
        <div className="marca">◎ Command Centre</div>
        <nav>{SECCOES.map(([c, n]) => <NavLink key={c} to={c} end={c === '/'}>{n}</NavLink>)}</nav>
        <a className="claude" href="https://claude.ai" target="_blank" rel="noopener noreferrer">Abrir Claude ↗</a>
        <div className="utilizador"><span>{nome}</span><button className="ligacao" onClick={sair}>Sair</button></div>
      </aside>
      {menu && <div className="veu" onClick={() => setMenu(false)} />}
      <main>
        <header>
          <button className="hamburguer" aria-label="Menu" onClick={() => setMenu(!menu)}>☰</button>
          <h1>{titulo}</h1>
        </header>
        <Routes>
          <Route path="/" element={<Navigate to="/equipa" replace />} />
          <Route path="/painel" element={<Painel />} />
          <Route path="/conversa" element={<Conversa />} />
          <Route path="/conversa/:id" element={<Conversa />} />
          <Route path="/sessoes" element={<Sessoes />} />
          <Route path="/modelos" element={<Modelos />} />
          <Route path="/definicoes" element={<Definicoes />} />
          {PAGINAS_EXTRA.map(([c, E]) => <Route key={c} path={c} element={<E />} />)}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  const [nome, setNome] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    api('/api/auth/me').then((m) => { definirCsrf(m.csrf); setNome(m.username) }).catch(() => setNome(null))
    const expirou = () => setNome(null)
    window.addEventListener('aicc:sessao-expirada', expirou)
    return () => window.removeEventListener('aicc:sessao-expirada', expirou)
  }, [])
  if (nome === undefined) return null
  if (nome === null) return <Login entrou={setNome} />
  return (
    <BrowserRouter>
      <Casca nome={nome} sair={async () => { await post('/api/auth/logout').catch(() => {}); setNome(null) }} />
    </BrowserRouter>
  )
}
