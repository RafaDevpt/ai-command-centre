"""
Equipa: vários agentes a trabalhar num objectivo sem intervenção do utilizador.

1. O coordenador divide o objectivo em subtarefas e atribui-as aos membros.
2. Os membros trabalham: agentes diferentes em paralelo, o mesmo agente em
   série. Cada um vê o quadro partilhado (o que os outros já produziram).
3. O coordenador revê o quadro e decide: concluir (resposta final) ou pedir
   mais trabalho, incluindo pôr um agente a rever/corrigir o de outro.
4. Repete até MAX de rondas. O utilizador pode deixar notas (entram na ronda
   seguinte) ou parar.

Os agentes continuam só de leitura; pedidos do Codex passam pelas Aprovações.

Created by Redfox using Claude
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from types import SimpleNamespace

from sqlalchemy import select, update

from . import agentes
from .db import sessao
from .models import Agent, TeamConversation, TeamMessage, TeamTask
from .seguranca import agora

_log = logging.getLogger("aicc.equipa")
MAX_SUBTAREFAS = 5
MAX_QUADRO = 5000           # caracteres do quadro mostrados a cada agente (CPU: contexto 4096 tokens)
_parar: set[str] = set()

FORMATO_PLANO = ('{"subtarefas": [{"agente": "<nome exacto>", "titulo": "<curto>", '
                 '"instrucoes": "<o que fazer, completo e autónomo>"}]}')
FORMATO_REVISAO = ('{"estado": "concluido", "resposta_final": "<resposta completa ao utilizador>"} ou '
                   '{"estado": "continuar", "subtarefas": [...mesmo formato...]}')


class ErroEquipa(RuntimeError):
    pass


def ler_json(texto: str) -> dict:
    """Extrai o primeiro objecto JSON da resposta (tolera ```json e texto à volta)."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S)
    inicio = texto.find("{")
    while inicio >= 0:
        profundidade = 0
        for i in range(inicio, len(texto)):
            if texto[i] == "{":
                profundidade += 1
            elif texto[i] == "}":
                profundidade -= 1
                if profundidade == 0:
                    try:
                        d = json.loads(texto[inicio:i + 1])
                        if isinstance(d, dict):
                            return d
                    except ValueError:
                        break
        inicio = texto.find("{", inicio + 1)
    raise ErroEquipa("O coordenador não respondeu em JSON.")


def _membros_txt(membros: list[Agent]) -> str:
    return "\n".join(f"- {a.name} ({a.provider}{', ' + a.model if a.model else ''}): {a.role or 'sem papel definido'}"
                     for a in membros)


async def _mensagem(task_id: str, ronda: int, autor: str, tipo: str, conteudo: str, titulo: str = "",
                    estado: str = "feito") -> int:
    async for s in sessao():
        m = TeamMessage(task_id=task_id, round=ronda, author=autor[:80], kind=tipo, title=titulo[:200],
                        content=conteudo, status=estado)
        s.add(m)
        await s.commit()
        return m.id
    raise RuntimeError("sem BD")


async def _actualizar(msg_id: int, conteudo: str, estado: str) -> None:
    async for s in sessao():
        m = await s.get(TeamMessage, msg_id)
        m.content, m.status = conteudo, estado
        await s.commit()


async def _quadro(task_id: str) -> tuple[str, str]:
    """Vista limitada da memória partilhada da conversa e notas para os agentes."""
    async for s in sessao():
        atual = await s.get(TeamTask, task_id)
        conversation_id = atual.conversation_id if atual else None
        tarefas = (await s.scalars(select(TeamTask).where(TeamTask.conversation_id == conversation_id)
                                   .order_by(TeamTask.turn_no, TeamTask.created_at, TeamTask.id))).all() \
            if conversation_id else ([atual] if atual else [])
        ids = [t.id for t in tarefas]
        mensagens = (await s.scalars(select(TeamMessage).where(TeamMessage.task_id.in_(ids))
                                     .order_by(TeamMessage.id))).all() if ids else []
        conversa = await s.get(TeamConversation, conversation_id) if conversation_id else None
        partes: list[str] = []
        memoria = conversa.memory if conversa else ""
        if memoria:
            memoria_visivel = memoria[-1600:]
            if len(memoria) > len(memoria_visivel):
                memoria_visivel = "…(parte antiga omitida)…\n" + memoria_visivel
            partes.append("Memória partilhada da conversa:\n" + memoria_visivel)
        for item in tarefas:
            if item.id != task_id:
                partes.append(f"[turno {item.turn_no}] Pedido do utilizador:\n{item.goal[:1200]}")
            for m in mensagens:
                if m.task_id != item.id:
                    continue
                if (m.kind == "subtarefa" and m.status == "feito") or (
                        m.kind in ("final", "claude") and m.status == "feito"):
                    limite = 1500 if m.kind == "subtarefa" else 2500
                    partes.append(f"[turno {item.turn_no}, ronda {m.round}] {m.author} — {m.title}:\n{m.content[:limite]}")
        notas = [m.content for m in mensagens if m.kind == "nota" and m.status == "feito"]
        quadro = "\n\n".join(partes) or "(ainda sem resultados anteriores)"
        if len(quadro) > MAX_QUADRO:
            marcador = "…(histórico antigo omitido; transcrição completa guardada)…\n\n"
            quadro = marcador + quadro[-(MAX_QUADRO - len(marcador)):]
        return quadro, "\n".join(f"- {n}" for n in notas[-20:]) or "(nenhuma)"
    return "", ""


async def _perguntar_coordenador(t: SimpleNamespace, pedido: str) -> dict:
    """Pergunta ao coordenador; se a resposta não for JSON, pede uma vez a correcção."""
    msg_id = await _mensagem(t.id, t.round, getattr(t, "coordinator_name", "Coordenador"), "coordenacao", "", "A preparar resposta", "a-correr")
    texto = ""
    ultimo_update = 0.0

    async def progresso(delta: str) -> None:
        nonlocal texto, ultimo_update
        texto += delta
        agora_mono = asyncio.get_running_loop().time()
        if agora_mono - ultimo_update >= 0.5:
            await _actualizar(msg_id, texto[-30000:], "a-correr")
            ultimo_update = agora_mono

    run = await agentes.correr(t.coordinator_id, pedido, t.project_id, "coordenacao", t.id, progresso)
    await _actualizar(msg_id, run.output, "feito" if run.status == "concluida" else "erro")
    if run.status != "concluida":
        raise ErroEquipa(f"O coordenador falhou: {run.output[-300:]}")
    try:
        return ler_json(run.output)
    except ErroEquipa:
        await _actualizar(msg_id, texto + "\n\nA corrigir o formato da resposta…", "a-correr")
        run = await agentes.correr(t.coordinator_id, pedido + "\n\nIMPORTANTE: a resposta anterior não era JSON "
                                   "válido. Responde APENAS com o objecto JSON, sem mais nada.",
                                   t.project_id, "coordenacao", t.id, progresso)
        await _actualizar(msg_id, run.output, "feito" if run.status == "concluida" else "erro")
        return ler_json(run.output)


def _subtarefas(decisao: dict) -> list:
    """Aceita os nomes de campo alternativos usados por alguns formatos do modelo."""
    if isinstance(decisao, list):
        return decisao
    valor = next((decisao[k] for k in ("subtarefas", "subtasks", "tarefas", "tasks")
                  if isinstance(decisao.get(k), list)), None)
    return valor if isinstance(valor, list) else []


def _validar(subtarefas, membros: dict[str, Agent]) -> list[dict]:
    saida = []
    for st in (subtarefas or [])[:MAX_SUBTAREFAS]:
        if not isinstance(st, dict):
            continue
        def campo(*aliases):
            valores = {str(st[k]).strip() for k in aliases if st.get(k) is not None and str(st[k]).strip()}
            if len(valores) > 1:
                raise ErroEquipa("O coordenador devolveu campos de tarefa contraditórios.")
            return next(iter(valores), "")

        nome = campo("agente", "membro", "agent", "member")
        agente = membros.get(nome.lower())
        if not agente:
            raise ErroEquipa(f"O coordenador atribuiu uma tarefa a um agente desconhecido: {nome or '(vazio)'}.")
        instrucoes = campo("instrucoes", "instructions", "descricao", "description")
        tarefa_generica = campo("tarefa", "task")
        instrucoes = instrucoes or tarefa_generica
        if not instrucoes:
            continue
        titulo = campo("titulo", "title") or tarefa_generica or instrucoes or "Subtarefa"
        saida.append({"agente": agente, "titulo": str(titulo)[:200], "instrucoes": str(instrucoes)[:6000]})
    if not saida:
        raise ErroEquipa("O coordenador não definiu subtarefas válidas.")
    return saida


async def _executar(t: SimpleNamespace, ronda: int, subtarefas: list[dict]) -> None:
    por_agente: dict[str, list[dict]] = {}
    for st in subtarefas:
        st["msg"] = await _mensagem(t.id, ronda, st["agente"].name, "subtarefa", "", st["titulo"], "a-correr")
        por_agente.setdefault(st["agente"].id, []).append(st)

    async def trabalhar(lista: list[dict]) -> None:
        for st in lista:
            if t.id in _parar:
                await _actualizar(st["msg"], "Parada pelo utilizador.", "erro")
                continue
            quadro, notas = await _quadro(t.id)
            pedido = (f"Trabalhas numa equipa de agentes. Objectivo geral:\n{t.goal}\n\n"
                      f"A tua subtarefa — {st['titulo']}:\n{st['instrucoes']}\n\n"
                      f"O que a equipa já produziu:\n{quadro}\n\nNotas do utilizador:\n{notas}\n\n"
                      "Responde só com o resultado da tua subtarefa, completo e em PT-PT.")
            ultimo_update = 0.0
            acumulado = ""

            async def progresso(delta: str) -> None:
                nonlocal ultimo_update, acumulado
                acumulado += delta
                agora_mono = asyncio.get_running_loop().time()
                if agora_mono - ultimo_update >= 0.5:
                    await _actualizar(st["msg"], acumulado[-30000:], "a-correr")
                    ultimo_update = agora_mono

            run = await agentes.correr(st["agente"].id, pedido, t.project_id, "subtarefa", t.id, progresso)
            estado = "feito" if run.status == "concluida" else "erro"
            conteudo = run.output
            if t.id in _parar and estado == "erro":
                conteudo = (conteudo + "\n\n" if conteudo else "") + "Interrompida pelo utilizador."
            await _actualizar(st["msg"], conteudo, estado)

    await asyncio.gather(*(trabalhar(lista) for lista in por_agente.values()))
    if t.id not in _parar:
        async for s in sessao():
            ids = [st["msg"] for st in subtarefas]
            msgs = (await s.scalars(select(TeamMessage).where(TeamMessage.id.in_(ids)))).all()
            falhas = [m.title for m in msgs if m.status != "feito"]
            if falhas:
                raise ErroEquipa("Uma ou mais subtarefas falharam; a equipa não pode concluir: " + ", ".join(falhas))
            break


async def _correr_equipa(task_id: str, retomar: bool = False) -> None:
    """retomar=True: a tarefa já tinha terminado e o utilizador trouxe o contributo do Claude;
    o coordenador revê logo (sem novo plano) e tem até 2 rondas extra."""
    async for s in sessao():
        t = await s.get(TeamTask, task_id)
        if not t:
            return
        t.status = "a-correr"
        await s.commit()
        coord = await s.get(Agent, t.coordinator_id)
        # Cópias simples: os objectos ORM expiram a cada commit (e não se podem recarregar aqui).
        coord = SimpleNamespace(name=coord.name)
        lista = [SimpleNamespace(id=a.id, name=a.name, provider=a.provider, model=a.model, role=a.role)
                 for a in (await s.scalars(select(Agent).where(Agent.id.in_(t.members)))).all() if a.enabled]
        membros = {a.name.lower(): a for a in lista}
        inicio = t.round + 1 if retomar else 1
        if retomar:
            t.max_rounds = t.round + 2
            await s.commit()
        t = SimpleNamespace(id=t.id, goal=t.goal, project_id=t.project_id, coordinator_id=t.coordinator_id, coordinator_name=coord.name,
                            conversation_id=t.conversation_id, turn_no=t.turn_no,
                            max_rounds=t.max_rounds, round=t.round if retomar else 0)
        try:
            if not membros:
                raise ErroEquipa("A equipa não tem membros activos.")
            subtarefas: list[dict] = []
            historico, notas_iniciais = await _quadro(t.id)
            plano = {} if retomar else await _perguntar_coordenador(t, (
                f"És o coordenador de uma equipa de agentes de IA. Objectivo do utilizador:\n{t.goal}\n\n"
                f"Memória partilhada e histórico desta conversa:\n{historico}\n\n"
                f"Notas anteriores do utilizador:\n{notas_iniciais}\n\n"
                f"Membros disponíveis (usa exactamente estes nomes):\n{_membros_txt(lista)}\n\n"
                f"Divide o objectivo em 1 a {MAX_SUBTAREFAS} subtarefas concretas e atribui cada uma ao membro "
                "mais adequado ao seu papel. Subtarefas de membros diferentes correm em paralelo. "
                f"Responde APENAS com JSON neste formato:\n{FORMATO_PLANO}"))
            if not retomar:
                subtarefas = _validar(_subtarefas(plano), membros)
            final = None
            for ronda in range(inicio, t.max_rounds + 1):
                if task_id in _parar:
                    break
                t.round = ronda
                await s.execute(update(TeamTask).where(TeamTask.id == task_id).values(round=ronda))
                await s.commit()
                if subtarefas:          # ao retomar, a 1.ª ronda é só a revisão do contributo do Claude
                    await _mensagem(t.id, ronda, coord.name, "plano", "\n".join(
                        f"- {st['agente'].name}: {st['titulo']}" for st in subtarefas), f"Plano da ronda {ronda}")
                    await _executar(t, ronda, subtarefas)
                if task_id in _parar:
                    break
                quadro, notas = await _quadro(t.id)
                ultima = ronda == t.max_rounds
                decisao = await _perguntar_coordenador(t, (
                    f"És o coordenador. Ronda {ronda} de {t.max_rounds}. Objectivo:\n{t.goal}\n\n"
                    f"Membros:\n{_membros_txt(lista)}\n\nQuadro da equipa:\n{quadro}\n\n"
                    f"Notas do utilizador:\n{notas}\n\n"
                    + ("Esta é a ÚLTIMA ronda: tens de concluir e escrever a resposta final, integrando o trabalho "
                       "da equipa.\n" if ultima else
                       "Se o objectivo está cumprido, conclui com a resposta final integrada. Se faltar algo ou "
                       "houver erros, pede mais subtarefas (podes pedir a um membro que reveja ou corrija o "
                       "trabalho de outro).\n")
                    + f"Responde APENAS com JSON: {FORMATO_REVISAO}"))
                if decisao.get("estado") == "concluido" or ultima:
                    final = str(decisao.get("resposta_final") or "").strip()
                    if not final:
                        final = "(O coordenador não escreveu a resposta final.)\n\n" + quadro
                    break
                await _mensagem(t.id, ronda, coord.name, "revisao", "Pediu mais trabalho.", "Revisão do coordenador")
                subtarefas = _validar(_subtarefas(decisao), membros)
            if task_id in _parar:
                estado, resultado = "parada", "Parada pelo utilizador."
            else:
                estado, resultado = "concluida", final or ""
                await _mensagem(task_id, t.round, coord.name, "final", resultado, "Resposta final")
        except Exception as exc:  # noqa: BLE001
            _log.warning("Equipa %s falhou (%s).", task_id, type(exc).__name__)
            estado, resultado = "erro", f"⚠️ {exc}"
            await _mensagem(task_id, getattr(t, "round", 0), "sistema", "erro", str(exc)[:1000], "Erro")
        await s.rollback()
        await s.execute(update(TeamTask).where(TeamTask.id == task_id)
                        .values(status=estado, result=resultado, finished_at=agora()))
        if t.conversation_id:
            conversa = await s.get(TeamConversation, t.conversation_id)
            if conversa:
                conversa.status = "activa"
                conversa.updated_at = agora()
        _parar.discard(task_id)
        await s.commit()


async def _recuperar_worker_interrompido(task_id: str) -> None:
    """Liberta a conversa se o worker falhar antes da sua finalização normal."""
    interrompida = task_id in _parar
    estado = "parada" if interrompida else "erro"
    resultado = ("Interrompida antes de concluir." if interrompida
                 else "O worker terminou inesperadamente antes de concluir.")
    async for s in sessao():
        await s.execute(update(TeamTask).where(
            TeamTask.id == task_id, TeamTask.status.in_(["pendente", "a-correr"])
        ).values(status=estado, result=f"⚠️ {resultado}", finished_at=agora()))
        t = await s.get(TeamTask, task_id)
        if t and t.conversation_id:
            await s.execute(update(TeamConversation).where(
                TeamConversation.id == t.conversation_id, TeamConversation.status == "a-correr"
            ).values(status="activa", updated_at=agora()))
        await s.commit()
        return


async def correr_equipa(task_id: str, retomar: bool = False) -> None:
    """Garante que uma excepção ou cancelamento não deixa a conversa bloqueada."""
    try:
        await _correr_equipa(task_id, retomar)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(_recuperar_worker_interrompido(task_id))
        except Exception as exc:  # noqa: BLE001
            _log.warning("Não foi possível finalizar equipa interrompida (%s).", type(exc).__name__)
        raise
    except Exception as exc:  # noqa: BLE001
        _log.warning("Worker da equipa falhou antes da finalização (%s).", type(exc).__name__)
        await _recuperar_worker_interrompido(task_id)


def briefing(goal: str, msgs: list[TeamMessage], resultado: str) -> str:
    """Texto para colar no Claude Code (ponte manual: o servidor não fala com o Claude)."""
    partes = ["# Pedido da equipa do AI Command Centre", "", "## Objectivo", goal.strip(), ""]
    planos = [m for m in msgs if m.kind == "plano"]
    if planos:
        partes += ["## Plano do coordenador", planos[-1].content, ""]
    feitos = [m for m in msgs if (m.kind == "subtarefa" and m.status == "feito") or m.kind == "claude"]
    if feitos:
        partes.append("## Trabalho já feito pela equipa")
        for m in feitos[-8:]:
            partes += [f"### {m.author} — {m.title} (ronda {m.round})", m.content[:3000], ""]
    notas = [m.content for m in msgs if m.kind == "nota"]
    if notas:
        partes += ["## Notas do utilizador", *[f"- {n}" for n in notas], ""]
    if resultado and not resultado.startswith("⚠️"):
        partes += ["## Resposta actual do coordenador", resultado[:4000], ""]
    partes += ["## O que preciso de ti",
               "És o membro da equipa responsável por produzir o código e testá-lo. Com base no que está acima:",
               "1. Escreve o código completo (ficheiros inteiros, com caminhos).",
               "2. Escreve os testes e corre-os; mostra o comando e o resultado.",
               "3. Diz o que ficou por fazer ou o que discordas do plano.",
               "Responde em PT-PT. A tua resposta vai ser colada de volta no quadro da equipa."]
    return "\n".join(partes)


def parar(task_id: str) -> None:
    _parar.add(task_id)
    from . import claude_code
    try:
        asyncio.get_running_loop().create_task(claude_code.interromper(task_id))
    except RuntimeError:
        pass
