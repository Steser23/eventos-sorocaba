"""Arquivos de dados do agente, guardados na pasta data/ do repositório."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from .modelos import Evento

PASTA = Path("data")
EVENTOS = PASTA / "eventos.json"
ESTADO = PASTA / "estado.json"
METRICAS = PASTA / "metricas.csv"
REVISAO = PASTA / "revisao.md"
DEPURACAO = PASTA / "depuracao"

COLUNAS_METRICAS = [
    "data_execucao", "fonte", "paginas_lidas", "paginas_sem_mudanca",
    "caracteres_brutos", "caracteres_limpos", "tokens_estimados_brutos", "tokens_estimados_limpos",
    "chamadas_llm", "tokens_entrada_api", "tokens_saida_api",
    "eventos_encontrados", "eventos_novos", "erro",
]


def carregar_eventos() -> dict[str, dict]:
    if not EVENTOS.exists():
        return {}
    return {e["id"]: e for e in json.loads(EVENTOS.read_text(encoding="utf-8"))}


def salvar_eventos(eventos: dict[str, dict]) -> None:
    PASTA.mkdir(exist_ok=True)
    ordenados = sorted(eventos.values(), key=lambda e: (e.get("data_inicio") or "9999", e["titulo"]))
    EVENTOS.write_text(json.dumps(ordenados, ensure_ascii=False, indent=2), encoding="utf-8")


def mesclar(existentes: dict[str, dict], novos: list[Evento]) -> list[dict]:
    """Acrescenta só os eventos inéditos; o que já foi revisado nunca é sobrescrito."""
    inseridos = []
    for evento in novos:
        if evento.id in existentes:
            continue
        existentes[evento.id] = evento.para_dict()
        inseridos.append(existentes[evento.id])
    return inseridos


def carregar_estado() -> dict:
    if not ESTADO.exists():
        return {}
    return json.loads(ESTADO.read_text(encoding="utf-8"))


def salvar_estado(estado: dict) -> None:
    PASTA.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar_metricas(linhas: list[dict]) -> None:
    PASTA.mkdir(exist_ok=True)
    novo = not METRICAS.exists()
    with METRICAS.open("a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_METRICAS)
        if novo:
            escritor.writeheader()
        for linha in linhas:
            escritor.writerow({c: linha.get(c, "") for c in COLUNAS_METRICAS})


def escrever_revisao(eventos: dict[str, dict], hoje: date) -> None:
    """Página legível no GitHub com os eventos que ainda precisam de revisão."""
    pendentes = [
        e for e in eventos.values()
        if e["status"] == "pendente_revisao" and (e.get("data_fim") or e.get("data_inicio") or "9999") >= hoje.isoformat()
    ]
    pendentes.sort(key=lambda e: (e.get("data_inicio") or "9999", e["titulo"]))
    linhas = [
        "# Eventos para revisar",
        "",
        f"Atualizado em {hoje.isoformat()}. {len(pendentes)} eventos futuros aguardando revisão.",
        "Confiança **baixa** = data ou local incertos: confira na fonte antes de aprovar.",
        "",
        "| Data | Horário | Evento | Local | Cidade | Preço | Confiança | Fonte |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in pendentes:
        preco = "Grátis" if e.get("gratuito") else (e.get("preco") or "")
        linhas.append(
            "| {data} | {hora} | {titulo} | {local} | {cidade} | {preco} | {conf} | [{fonte}]({link}) |".format(
                data=e.get("data_inicio") or "?",
                hora=e.get("horario") or "",
                titulo=_celula(e["titulo"]),
                local=_celula(e.get("local") or ""),
                cidade=_celula(e.get("cidade") or ""),
                preco=_celula(preco),
                conf=e.get("confianca", ""),
                fonte=e["fonte"],
                link=e["link_fonte"],
            )
        )
    PASTA.mkdir(exist_ok=True)
    REVISAO.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def salvar_depuracao(nome: str, conteudo: str) -> None:
    """Guarda amostras da última leitura, para entender e melhorar o agente."""
    DEPURACAO.mkdir(parents=True, exist_ok=True)
    (DEPURACAO / nome).write_text(conteudo[:200000], encoding="utf-8")


def _celula(texto: str) -> str:
    return texto.replace("|", "/").replace("\n", " ")
