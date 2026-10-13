"""Agenda cultural da Band: encontra as agendas mais recentes e extrai os eventos com o LLM."""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..leitura import ler_pagina
from ..modelos import Evento
from .comum import extrair_de_html, nova_metrica

PALAVRAS = ("agenda", "fim de semana", "programação")


def encontrar_agendas(html_lista: str, url_lista: str, maximo: int) -> list[str]:
    """Links de matérias de agenda na página da seção, do mais recente para o mais antigo."""
    sopa = BeautifulSoup(html_lista, "html.parser")
    links: list[str] = []
    for a in sopa.find_all("a", href=True):
        url = urljoin(url_lista, a["href"]).split("?")[0].split("#")[0]
        if "band.com.br" not in url:
            continue
        texto = f"{a.get_text(' ')} {url}".lower()
        if "agenda-cultural" in url or (any(p in texto for p in PALAVRAS) and "sorocaba" in texto):
            if url not in links and url.rstrip("/") != url_lista.rstrip("/"):
                links.append(url)
    return links[:maximo]


def data_publicacao(html: str, padrao: date) -> date:
    sopa = BeautifulSoup(html, "html.parser")
    meta = sopa.find("meta", attrs={"property": "article:published_time"}) or sopa.find(
        "meta", attrs={"name": "date"}
    )
    try:
        return date.fromisoformat(meta["content"][:10])
    except (TypeError, KeyError, ValueError):
        return padrao


def coletar(config: dict, hoje: date, *, estado: dict, llm, limites: dict, depurar) -> tuple[list[Evento], dict, str]:
    metrica = nova_metrica(config["id"])
    estado_fonte = estado.setdefault(config["id"], {})
    url_lista = config["url_lista"]

    agendas = encontrar_agendas(ler_pagina(url_lista), url_lista, config.get("max_artigos", 2))
    if not agendas:
        metrica["erro"] = "nenhuma agenda encontrada na página da seção"
        return [], metrica, ""

    eventos: list[Evento] = []
    ultimo_texto = ""
    for url in agendas:
        if url in estado_fonte:  # matéria já processada numa execução anterior
            metrica["paginas_sem_mudanca"] += 1
            continue
        html = ler_pagina(url)
        encontrados, ultimo_texto = extrair_de_html(
            html,
            fonte=config["id"],
            link=url,
            contexto=f"Matéria de agenda cultural da Band: {url}",
            referencia=data_publicacao(html, hoje),
            estado_fonte=estado_fonte,
            chave=url,
            llm=llm,
            max_caracteres=limites["max_caracteres_por_trecho"],
            metrica=metrica,
        )
        eventos.extend(encontrados)

    metrica["eventos_encontrados"] = len(eventos)
    return eventos, metrica, ultimo_texto
