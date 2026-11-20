// Dashboard de colaboração: Codex no centro, agentes ligados e tarefas ao vivo.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, patch, post, quando } from '../api'

const ACTIVA = ['pendente', 'a-correr']
const ESTADO: Record<string, string> = { pendente: 'Na fila', 'a-correr': 'A trabalhar', concluida: 'Concluída', erro: 'Falhou', parada: 'Interrompida', feito: 'Concluída', 'à espera': 'À espera' }
const ICONES: Record<string, string> = { plano: '⌘', coordenacao: '◉', subtarefa: '↗', revisao: '↻', final: '✓', claude: '✳', nota: '✎', erro: '!' }

export default function Equipa() {
  const [agentes, setAgentes] = useState<any[]>([])
  const [lista, setLista] = useState<any[]>([])
  const [conversa, setConversa] = useState<any>(null)
  const [memoria, setMemoria] = useState('')
  const [memoriaSuja, setMemoriaSuja] = useState(false)
  const [tarefa, setTarefa] = useState<any>(null)
  const [seleccionado, setSeleccionado] = useState('')
  const [membros, setMembros] = useState<string[]>([])
  const [objectivo, setObjectivo] = useState('')
  const [nota, setNota] = useState('')
  const [projecto, setProjecto] = useState('')
  const [projectos, setProjectos] = useState<any[]>([])
  const [erro, setErro] = useState('')
  const [reconectar, setReconectar] = useState(false)
  const [aEnviar, setAEnviar] = useState(false)

  const coordenador = agentes.find((a) => a.fornecedor === 'codex' && a.activo)
  const participantes = agentes.filter((a) => a.activo && a.fornecedor !== 'codex')
  const activa = !!tarefa && ACTIVA.includes(tarefa.estado)

  const lerLista = useCallback(async () => {
    const dados = await api('/api/team/conversations')
    setLista(dados)
    return dados
  }, [])
  const abrir = useCallback(async (id: string) => {
    try {
      const [detalhe] = await Promise.all([api(`/api/team/conversations/${id}`), lerLista()])
      setConversa(detalhe)
      const actual = detalhe.tarefas?.[detalhe.tarefas.length - 1] ?? null
      setTarefa(actual); setReconectar(false); setErro('')
      if (!memoriaSuja) setMemoria(detalhe.memoria || '')
      setSeleccionado((actualId) => actualId || actual?.membros?.[0] || actual?.coordenador || '')
    } catch { setReconectar(true) }
  }, [lerLista, memoriaSuja])

  useEffect(() => {
    api('/api/agents').then((dados: any[]) => {
      const activos = dados.filter((a) => a.activo)
      setAgentes(activos)
      setMembros(activos.filter((a) => a.fornecedor !== 'codex').map((a) => a.id))
      const cc = activos.find((a) => a.fornecedor === 'codex')
      setSeleccionado(cc?.id ?? '')
    }).catch(() => setErro('Não foi possível carregar os agentes.'))
    api('/api/projects').then(setProjectos).catch(() => {})
    lerLista().then((dados) => { if (dados[0]) void abrir(dados[0].id) }).catch(() => setReconectar(true))
  }, [abrir, lerLista])

  useEffect(() => {
    if (!activa || !conversa?.id) return
    const actualizar = () => { void abrir(conversa.id) }
    const offline = () => setReconectar(true)
    const intervalo = window.setInterval(actualizar, 1600)
    window.addEventListener('online', actualizar); window.addEventListener('offline', offline)
    return () => { window.clearInterval(intervalo); window.removeEventListener('online', actualizar); window.removeEventListener('offline', offline) }
  }, [activa, conversa?.id, abrir])

  const porId = (id: string) => agentes.find((a) => a.id === id)
  const nome = (id: string) => porId(id)?.nome ?? 'Agente indisponível'
  const tarefasDoAgente = (id: string) => (tarefa?.quadro ?? []).filter((m: any) => id === tarefa.coordenador
    ? ['plano', 'coordenacao', 'revisao', 'final', 'erro'].includes(m.tipo) && ['Codex', nome(id), 'sistema'].includes(m.autor)
    : m.autor === nome(id) && ['subtarefa', 'erro'].includes(m.tipo))

  const linhas = useMemo(() => {
    const total = Math.max(participantes.length, 1)
    return participantes.map((a, i) => {
      const angulo = (i / total) * Math.PI * 2 - Math.PI / 2
      const x = 50 + Math.cos(angulo) * 34
      const y = 50 + Math.sin(angulo) * 36
      const ms = (tarefa?.quadro ?? []).filter((m: any) => m.autor === a.nome && m.tipo === 'subtarefa')
      const actual = [...ms].reverse().find((m: any) => m.estado === 'a-correr')
      const falha = [...ms].reverse().find((m: any) => m.estado === 'erro')
      const ultimo = [...ms].reverse().find((m: any) => m.estado === 'feito')
      const estado = actual ? 'a-correr' : falha ? 'erro' : ultimo ? 'feito' : activa ? 'pendente' : 'à espera'
      return { agente: a, x, y, estado, actual, falha, ultimo }
    })
  }, [participantes, tarefa, activa])

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault(); setErro('')
    if (!coordenador) { setErro('O agente Codex não está activo.'); return }
    if (!membros.length) { setErro('Selecciona pelo menos um agente para a equipa.'); return }
    setAEnviar(true)
    try {
      const nova = await post('/api/team', { objectivo, coordenador: coordenador.id, membros, projecto_id: projecto || null, rondas: 4, conversation_id: conversa?.id || null })
      setObjectivo(''); setTarefa(nova); setSeleccionado(coordenador.id); setReconectar(false)
      await abrir(nova.conversation_id)
    } catch (x: any) { setErro(x.message) } finally { setAEnviar(false) }
  }
  const enviarNota = async (e: React.FormEvent) => {
    e.preventDefault()
    try { await post(`/api/team/${tarefa.id}/note`, { texto: nota }); setNota(''); if (conversa) await abrir(conversa.id) }
    catch (x: any) { setErro(x.message) }
  }
  const parar = async () => {
    try { await post(`/api/team/${tarefa.id}/stop`); if (conversa) await abrir(conversa.id) }
    catch (x: any) { setErro(x.message) }
  }
  const repetir = async () => {
    try { await post(`/api/team/${tarefa.id}/retry`); if (conversa) await abrir(conversa.id) }
    catch (x: any) { setErro(x.message) }
  }
  const guardarMemoria = async () => {
    if (!conversa?.id) return
    try {
      await patch(`/api/team/conversations/${conversa.id}/memory`, { texto: memoria })
      setMemoriaSuja(false); await abrir(conversa.id)
    } catch (x: any) { setErro(x.message) }
  }
  const transcricao = conversa?.tarefas ?? []

  const eventos = tarefasDoAgente(seleccionado)
  const centro = coordenador?.id === seleccionado
  const ultimaFinal = [...(tarefa?.quadro ?? [])].reverse().find((m: any) => m.tipo === 'final')

  return <div className="cerebro">
    <section className="cerebro-topo">
        <div><span className="microtitulo">AICC / COLLABORATION FABRIC</span><h2>Uma conversa. Uma equipa. Memória partilhada.</h2><p>O Codex mantém o contexto entre turnos e coordena as outras IAs.</p></div>
      <div className="cerebro-estado"><span className={`pulso ${activa ? 'activo' : ''}`} />{activa ? 'FLUXO ACTIVO' : 'SISTEMA PRONTO'}<small>{participantes.length + (coordenador ? 1 : 0)} agentes online</small></div>
    </section>

    {reconectar && <div className="cerebro-aviso" role="status"><span>Ligação interrompida.</span> A reconectar; o estado persistido continua disponível.</div>}
    {erro && <div className="cerebro-aviso erro" role="alert">{erro}</div>}

    <section className="cerebro-layout">
      <aside className="cerebro-chat">
        <div className="painel-titulo"><span>01 / CONVERSA</span><span className="online-dot" /> MEMÓRIA PERSISTENTE</div>
        <div className="conversa-acoes"><button type="button" onClick={() => { setConversa(null); setTarefa(null); setMemoria(''); setMemoriaSuja(false); setObjectivo('') }}>＋ Nova conversa</button><span>{conversa ? `${conversa.turnos} turnos guardados` : 'Conversa nova'}</span></div>
        <div className="cerebro-boasvindas"><div className="avatar-codex">C</div><div><b>Codex</b><small>coordenador · pronto</small></div></div>
        <p className="chat-hint">Continua a conversa em qualquer momento. O histórico e a memória ficam guardados e são partilhados com os agentes desta sessão.</p>
        <div className="chat-transcricao">{transcricao.map((t: any) => <article className="turno-chat" key={t.id}><small>TURNO {t.turno} · {quando(t.criada)}</small><p className="turno-pedido">{t.objectivo}</p>{t.estado === 'concluida' ? <p className="turno-resposta">{t.resultado}</p> : <p className={`turno-estado ${t.estado}`}>{ESTADO[t.estado] ?? t.estado}{t.estado === 'erro' ? ` · ${t.resultado}` : ''}</p>}</article>)}</div>
        <div className="membros-label">EQUIPA DISPONÍVEL <span>{membros.length} seleccionados</span></div>
        <div className="membros-toggles">{participantes.map((a) => <label key={a.id} className={`membro-toggle ${membros.includes(a.id) ? 'ligado' : ''}`}><input type="checkbox" checked={membros.includes(a.id)} onChange={(e) => setMembros(e.target.checked ? [...membros, a.id] : membros.filter((x) => x !== a.id))} /><span className={`mini-ai ${a.fornecedor === 'claude-code' ? 'claude-ai' : 'local-ai'}`}>{a.fornecedor === 'claude-code' ? '✳' : '◌'}</span><span>{a.nome}<small>{a.fornecedor === 'claude-code' ? 'CLI oficial' : 'modelo local'}</small></span><i>{membros.includes(a.id) ? 'ON' : 'OFF'}</i></label>)}</div>
        <label className="projecto-select">PROJECTO CONTEXTO<select value={projecto} onChange={(e) => setProjecto(e.target.value)}><option value="">Geral</option>{projectos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</select></label>
        {conversa && <label className="memoria-partilhada">MEMÓRIA PARTILHADA<textarea rows={3} value={memoria} placeholder="Decisões, preferências e contexto duradouro para todos os agentes…" onChange={(e) => { setMemoria(e.target.value); setMemoriaSuja(true) }} /><button type="button" disabled={!memoriaSuja} onClick={() => void guardarMemoria()}>Guardar memória</button></label>}
        <form className="composer" onSubmit={enviar}>
          <textarea rows={5} placeholder="Ex.: Analisa estes logs, identifica a causa e propõe uma correcção…" value={objectivo} onChange={(e) => setObjectivo(e.target.value)} required />
          <div><span>{conversa ? `CONTINUAR TURNO ${conversa.turnos + 1}` : 'INICIAR CONVERSA'} · SHIFT+ENTER NOVA LINHA</span><button className="send-button" disabled={aEnviar || activa || !coordenador || !membros.length} aria-label="Enviar pedido">{aEnviar ? '…' : '↑'}</button></div>
        </form>
        <div className="chat-historico"><div className="painel-titulo">CONVERSAS RECENTES</div>{lista.slice(0, 6).map((c) => <button key={c.id} className={`historico-item ${conversa?.id === c.id ? 'actual' : ''}`} onClick={() => { setConversa(c); void abrir(c.id) }}><span className={`estado-ponto ${c.actual?.estado ?? c.estado}`} /><span>{c.titulo}</span><small>{c.turnos} turnos</small></button>)}</div>
      </aside>

      <section className="cerebro-main">
        <div className="painel-titulo"><span>02 / ROUTING GRAPH</span><span className="graph-hint">SELECCIONA UMA LIGAÇÃO PARA INSPECCIONAR</span></div>
        <div className="brain-graph">
          <svg className="brain-lines" viewBox="0 0 1000 600" preserveAspectRatio="none" aria-hidden="true">
            <defs><marker id="seta-fluxo" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#72a8ff" /></marker></defs>
            {linhas.map((l) => <line key={l.agente.id} x1="500" y1="300" x2={l.x * 10} y2={l.y * 6} markerStart="url(#seta-fluxo)" markerEnd="url(#seta-fluxo)" className={`brain-line ${l.estado === 'a-correr' ? 'em-curso' : l.estado === 'erro' ? 'com-erro' : ''} ${seleccionado === l.agente.id ? 'seleccionada' : ''}`} />)}
          </svg>
          {linhas.map((l) => <button key={l.agente.id} aria-label={`Inspeccionar ligação Codex para ${l.agente.nome}`} title={`Codex → ${l.agente.nome}`} className="brain-hit" style={{ left: `${(50 + l.x) / 2}%`, top: `${(50 + l.y) / 2}%` }} onClick={() => setSeleccionado(l.agente.id)} />)}
          {linhas.map((l) => <button key={`n-${l.agente.id}`} className={`brain-node ai-node ${seleccionado === l.agente.id ? 'seleccionado' : ''} ${l.estado === 'erro' ? 'falhado' : ''}`} style={{ left: `${l.x}%`, top: `${l.y}%` }} onClick={() => setSeleccionado(l.agente.id)}><span className={`node-icon ${l.agente.fornecedor === 'claude-code' ? 'claude-ai' : 'local-ai'}`}>{l.agente.fornecedor === 'claude-code' ? '✳' : '◌'}</span><b>{l.agente.nome}</b><small>{l.agente.fornecedor === 'claude-code' ? 'CLAUDE CODE · CLI' : 'OLLAMA · LOCAL'}</small><em className={`node-state ${l.estado}`}>{ESTADO[l.estado] ?? l.estado}</em></button>)}
          <button className={`brain-node core-node ${seleccionado === coordenador?.id ? 'seleccionado' : ''}`} style={{ left: '50%', top: '50%' }} onClick={() => coordenador && setSeleccionado(coordenador.id)}><span className="core-orbit orbit-one" /><span className="core-orbit orbit-two" /><span className="core-mark">C</span><b>Codex</b><small>COORDINADOR</small><em>{activa ? 'A ORQUESTRAR' : 'PRONTO'}</em></button>
          {!participantes.length && <div className="graph-empty">Cria ou activa agentes na página Agentes para os ligar ao fluxo.</div>}
          <div className="graph-foot"><span><i className="legend-dot live" /> AO VIVO</span><span><i className="legend-dot idle" /> DISPONÍVEL</span><span><i className="legend-dot bad" /> ERRO</span></div>
        </div>

        {tarefa ? <div className="task-strip"><div><small>FLUXO ACTUAL · RONDA {tarefa.ronda}/{tarefa.rondas}</small><strong>{tarefa.objectivo}</strong></div><span className={`task-pill ${tarefa.estado}`}>{ESTADO[tarefa.estado] ?? tarefa.estado}</span>{activa && <button className="stop-button" onClick={parar}>■ PARAR</button>}{['erro', 'parada'].includes(tarefa.estado) && <button className="retry-button" onClick={repetir}>↻ REPETIR</button>}</div> : <div className="task-empty">Envia um pedido para iniciar a colaboração. Cada linha vai mostrar o percurso e o estado do trabalho.</div>}

        {activa && <form className="nota-fluxo" onSubmit={enviarNota}><input placeholder="Nota para o Codex (entra na próxima ronda)…" value={nota} onChange={(e) => setNota(e.target.value)} required /><button>Adicionar nota ↗</button></form>}
        {ultimaFinal && <section className="final-answer"><div className="painel-titulo">03 / RESPOSTA CONSOLIDADA <span>Codex</span></div><p>{ultimaFinal.texto}</p></section>}
      </section>

      <aside className="cerebro-inspector">
        <div className="painel-titulo"><span>03 / LIVE INSPECTOR</span><span className="inspect-menu">•••</span></div>
        {seleccionado ? <>
          <div className="inspect-agent"><span className={`inspect-icon ${centro ? 'core-mark' : porId(seleccionado)?.fornecedor === 'claude-code' ? 'claude-ai' : 'local-ai'}`}>{centro ? 'C' : porId(seleccionado)?.fornecedor === 'claude-code' ? '✳' : '◌'}</span><div><b>{nome(seleccionado)}</b><small>{centro ? 'Agente coordenador' : porId(seleccionado)?.papel || porId(seleccionado)?.fornecedor}</small></div></div>
          {centro && tarefa && <div className="route-label"><span>Codex</span><b>↔</b><span>Equipa</span></div>}
          {!centro && <div className="route-label"><span>Codex</span><b>→</b><span>{nome(seleccionado)}</span></div>}
          <div className="event-list-title">ACTIVIDADE {activa && <span className="live-label"><i /> LIVE</span>}</div>
          <div className="event-list">{eventos.length ? eventos.map((m: any) => <article className={`event-card ${m.estado === 'erro' ? 'evento-erro' : ''}`} key={m.id}><div className="event-head"><span className="event-icon">{ICONES[m.tipo] ?? '·'}</span><b>{m.titulo || m.tipo}</b><span className={`event-status ${m.estado}`}>{ESTADO[m.estado] ?? m.estado}</span></div><small>RONDA {m.ronda} · {quando(m.quando)}</small><pre>{m.texto || (m.estado === 'a-correr' ? 'A aguardar saída do agente…' : '(sem conteúdo)')}</pre></article>) : <div className="event-vazio">{tarefa ? 'Esta ligação ainda não recebeu trabalho nesta tarefa.' : 'A actividade da ligação aparece aqui.'}</div>}</div>
        </> : <div className="event-vazio">Selecciona um agente ou uma ligação para inspeccionar o fluxo em tempo real.</div>}
      </aside>
    </section>
  </div>
}
