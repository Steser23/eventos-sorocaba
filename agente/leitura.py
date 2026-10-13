"""Leitura das páginas: simples (sem navegador) ou com navegador (Playwright)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

USER_AGENT = (
    "Mozilla/5.0 (compatible; eventos-sorocaba/0.1; "
    "+https://github.com/Steser23/eventos-sorocaba)"
)
TIMEOUT = 30.0
CABECALHOS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def ler_pagina(url: str) -> str:
    """Baixa o HTML de uma página que não depende de JavaScript."""
    with httpx.Client(headers=CABECALHOS, timeout=TIMEOUT, follow_redirects=True) as cliente:
        resposta = cliente.get(url)
        resposta.raise_for_status()
        return resposta.text


def ler_pagina_com_reserva(url: str) -> tuple[str, str]:
    """Tenta a leitura simples; se o site recusar (403, 429...), abre com o navegador.

    Devolve o HTML e o método usado ("simples" ou "navegador").
    """
    try:
        return ler_pagina(url), "simples"
    except httpx.HTTPStatusError as erro:
        if erro.response.status_code not in (401, 403, 406, 429, 503):
            raise
    return ler_com_navegador(url).html, "navegador"


def ler_json(url: str, params: dict | None = None) -> dict:
    """Consulta uma API que responde em JSON."""
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True) as cliente:
        resposta = cliente.get(url, params=params)
        resposta.raise_for_status()
        return resposta.json()


@dataclass
class PaginaRenderizada:
    html: str
    respostas_json: list[dict] = field(default_factory=list)  # dados que a página buscou sozinha
    unidade_filtrada: bool = False


def ler_com_navegador(url: str, unidade: str | None = None, cliques_veja_mais: int = 0) -> PaginaRenderizada:
    """Abre a página num navegador sem tela, espera o conteúdo carregar e devolve o HTML.

    Também guarda as respostas JSON que a página carregou: em muitos sites elas
    revelam uma API escondida, mais barata e confiável do que ler o texto.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    capturadas: list[dict] = []

    def guardar_json(resposta) -> None:
        try:
            tipo = resposta.headers.get("content-type", "")
            if "json" in tipo and len(capturadas) < 30:
                corpo = resposta.text()
                capturadas.append({"url": resposta.url, "amostra": corpo[:20000]})
        except Exception:
            pass

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(user_agent=USER_AGENT)
        pagina.on("response", guardar_json)
        pagina.goto(url, wait_until="networkidle", timeout=60000)

        filtrou = False
        if unidade:
            filtrou = _tentar_filtrar_unidade(pagina, unidade)
            if filtrou:
                try:
                    pagina.wait_for_load_state("networkidle", timeout=20000)
                except PlaywrightTimeout:
                    pass

        for _ in range(cliques_veja_mais):
            botao = pagina.get_by_text("Veja mais", exact=False)
            if botao.count() == 0:
                break
            try:
                botao.first.click(timeout=5000)
                pagina.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeout:
                break

        html = pagina.content()
        navegador.close()

    return PaginaRenderizada(html=html, respostas_json=capturadas, unidade_filtrada=filtrou)


def _tentar_filtrar_unidade(pagina, unidade: str) -> bool:
    """Procura um campo de seleção com a unidade (ex.: "SESI Sorocaba") e a escolhe."""
    for seletor in pagina.locator("select").all():
        try:
            opcoes = seletor.locator("option").all_inner_texts()
            alvo = next((o for o in opcoes if unidade.lower() in o.lower()), None)
            if alvo:
                seletor.select_option(label=alvo.strip())
                return True
        except Exception:
            continue
    return False


def resumo_json(capturas: list[dict]) -> str:
    """Texto curto para registrar quais APIs a página usou (ajuda a melhorar o agente)."""
    return json.dumps([c["url"] for c in capturas], ensure_ascii=False, indent=2)
