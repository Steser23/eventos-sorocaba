"""Sesi Sorocaba: lista filtrada pela unidade + páginas de detalhe de cada evento.

A listagem do Sesi não traz datas, mas a página de cada evento traz unidade,
data e horário em texto. Por isso o agente:
  1. lê a lista já filtrada pela unidade (parâmetro codigoUnidade no endereço);
  2. abre só as páginas de eventos que ainda não conhece;
  3. extrai os dados de cada uma com o LLM (textos curtos, poucos tokens).
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..leitura import ler_com_navegador, ler_pagina_com_reserva
from ..llm import LimiteDeChamadas
from ..modelos import Evento, normalizar
from .comum import extrair_de_html, nova_metrica


def links_de_eventos(html: str, base: str) -> list[str]:
    """Endereços das páginas de detalhe (formato /evento/<código>/<nome>)."""
    sopa = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in sopa.find_all("a", href=True):
        url = urljoin(base, a["href"]).split("?")[0].split("#")[0]
        if "/evento/" in url and url not in links:
            links.append(url)
    return links


def coletar(config: dict, hoje: date, *, estado: dict, llm, limites: dict, depurar) -> tuple[list[Evento], dict, str]:
    metrica = nova_metrica(config["id"])
    estado_fonte = estado.setdefault(config["id"], {})
    url_lista = f"{config['url']}?codigoUnidade={config['codigo_unidade']}"

    html_lista, metodo = ler_pagina_com_reserva(url_lista)
    links = links_de_eventos(html_lista, url_lista)
    if not links:
        # A lista pode depender de JavaScript; tenta com o navegador, clicando em "Veja mais".
        html_lista = ler_com_navegador(url_lista, cliques_veja_mais=config.get("cliques_veja_mais", 0)).html
        links, metodo = links_de_eventos(html_lista, url_lista), "navegador"
    metrica["paginas_lidas"] += 1
    depurar("sesi_lista.txt", f"método: {metodo}\n" + "\n".join(links))

    novos = [l for l in links if l not in estado_fonte]
    limite = config.get("max_detalhes_por_execucao", 25)
    avisos = [f"lista lida por {metodo}: {len(links)} eventos, {len(novos)} novos"]
    if len(novos) > limite:
        avisos.append(f"{len(novos) - limite} ficam para a próxima execução")

    eventos: list[Evento] = []
    ultimo_texto = ""
    for url in novos[:limite]:
        try:
            html, _ = ler_pagina_com_reserva(url)
            encontrados, ultimo_texto = extrair_de_html(
                html,
                fonte=config["id"],
                link=url,
                contexto=f"Página de um evento do SESI-SP. Unidade esperada: {config.get('unidade', 'SESI Sorocaba')}.",
                referencia=hoje,
                estado_fonte=estado_fonte,
                chave=url,
                llm=llm,
                max_caracteres=limites["max_caracteres_por_trecho"],
                metrica=metrica,
            )
        except LimiteDeChamadas:
            avisos.append("limite de chamadas ao LLM atingido")
            break
        eventos.extend(e for e in encontrados if eh_de_sorocaba(e))

    metrica["erro"] = "; ".join(avisos)
    metrica["eventos_encontrados"] = len(eventos)
    return eventos, metrica, ultimo_texto


def eh_de_sorocaba(evento: Evento) -> bool:
    alvo = f"{evento.cidade or ''} {evento.local or ''} {evento.endereco or ''}"
    return "sorocaba" in normalizar(alvo)
