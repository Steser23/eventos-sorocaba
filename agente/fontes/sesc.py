"""Sesc Sorocaba: a programação vem da API pública do Sesc, já estruturada (sem LLM)."""

from __future__ import annotations

from datetime import date

from ..leitura import ler_json
from ..modelos import Evento
from .comum import agora_iso, nova_metrica

BASE = "https://www.sescsp.org.br"
BUSCA = f"{BASE}/wp-json/wp/v1/atividades/search"


def coletar(config: dict, hoje: date, **_) -> tuple[list[Evento], dict, str]:
    metrica = nova_metrica(config["id"])
    eventos: list[Evento] = []
    coletado = agora_iso()
    amostras = []

    for pagina in range(1, config.get("max_paginas", 10) + 1):
        dados = ler_json(BUSCA, params={"s": config.get("busca", "sorocaba"), "ppp": 50, "page": pagina})
        metrica["paginas_lidas"] += 1
        itens = dados.get("atividade") or []
        if not itens:
            break
        amostras.extend(itens[:2] if pagina == 1 else [])
        for item in itens:
            evento = converter(item, config, hoje, coletado)
            if evento:
                eventos.append(evento)

    metrica["eventos_encontrados"] = len(eventos)
    return eventos, metrica, str(amostras)[:20000]


def converter(item: dict, config: dict, hoje: date, coletado: str) -> Evento | None:
    """Transforma um item da API do Sesc no formato padrão. Devolve None para descartar."""
    unidades = [u.get("name", "") for u in item.get("unidade") or []]
    if config.get("unidade", "Sorocaba") not in unidades:
        return None  # a busca também traz eventos de outras unidades que citam Sorocaba
    if item.get("cancelado"):
        return None

    inicio = item.get("dataPrimeiraSessao") or ""
    fim = item.get("dataUltimaSessao") or inicio
    proxima = item.get("dataProxSessao") or inicio
    data_fim = fim[:10] or None
    if data_fim and data_fim < hoje.isoformat():
        return None  # evento que já terminou

    titulo = (item.get("titulo") or "").strip()
    if item.get("complemento"):
        titulo = f"{titulo} — {item['complemento'].strip()}"

    categorias = item.get("tipos_linguagens") or []
    categoria = categorias[0].get("titulo") if categorias else None

    return Evento(
        titulo=titulo,
        fonte="sesc",
        link_fonte=BASE + (item.get("link") or ""),
        data_inicio=inicio[:10] or None,
        data_fim=data_fim if data_fim != inicio[:10] else None,
        horario=proxima[11:16] or None,
        local=config.get("nome", "Sesc Sorocaba"),
        endereco=config.get("endereco"),
        cidade="Sorocaba",
        gratuito=True if item.get("gratuito") else None,
        categoria=categoria,
        confianca="alta",
        coletado_em=coletado,
    )
