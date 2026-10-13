"""Agenda cultural da Band: encontra as agendas mais recentes e extrai os eventos com o LLM."""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..leitura import ler_pagina, ler_pagina_com_reserva
from ..limpeza import texto_limpo
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


def agendas_no_sitemap(xml: str, maximo: int) -> list[str]:
    """Matérias de agenda de Sorocaba no sitemap de notícias (o canal oficial para robôs)."""
    sopa = BeautifulSoup(xml, "html.parser")
    links: list[str] = []
    for url in sopa.find_all("url"):
        loc = url.find("loc")
        titulo = url.find("news:title")
        texto = f"{titulo.get_text(' ') if titulo else ''} {loc.get_text() if loc else ''}".lower()
        if loc and "sorocaba" in texto and any(p in texto for p in ("agenda", "fim de semana")):
            link = loc.get_text().strip()
            if link not in links:
                links.append(link)
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

    maximo = config.get("max_artigos", 2)
    agendas: list[str] = []
    avisos: list[str] = []

    # 1º caminho: sitemap de notícias, indicado no robots.txt da Band para robôs.
    try:
        agendas = agendas_no_sitemap(ler_pagina(config["url_sitemap"]), maximo)
    except Exception as erro:  # noqa: BLE001
        avisos.append(f"sitemap: {type(erro).__name__}")

    # 2º caminho: página da seção, com o navegador como reserva se o site recusar.
    if not agendas:
        try:
            html_lista, metodo = ler_pagina_com_reserva(url_lista)
            depurar("band_lista.txt", f"método: {metodo}\n\n" + texto_limpo(html_lista)[:20000])
            agendas = encontrar_agendas(html_lista, url_lista, maximo)
            print(f"lista lida por {metodo}")
        except Exception as erro:  # noqa: BLE001
            avisos.append(f"lista: {type(erro).__name__}")

    metrica["erro"] = "; ".join(avisos)
    if not agendas:
        metrica["erro"] = (metrica["erro"] + "; nenhuma agenda encontrada").strip("; ")
        return [], metrica, ""

    eventos: list[Evento] = []
    ultimo_texto = ""
    for url in agendas:
        if url in estado_fonte:  # matéria já processada numa execução anterior
            metrica["paginas_sem_mudanca"] += 1
            continue
        html, _ = ler_pagina_com_reserva(url)
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
