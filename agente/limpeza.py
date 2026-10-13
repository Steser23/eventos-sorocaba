"""Transforma HTML em texto limpo, para gastar menos tokens no LLM."""

from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

ETIQUETAS_DE_RUIDO = ["script", "style", "noscript", "nav", "footer", "form", "svg", "iframe", "aside"]


def texto_bruto(html: str) -> str:
    """Todo o texto visível da página, sem nenhuma limpeza (só para medir)."""
    sopa = BeautifulSoup(html, "html.parser")
    for tag in sopa(["script", "style", "noscript"]):
        tag.decompose()
    return _compactar(sopa.get_text("\n"))


def texto_limpo(html: str, modo: str = "auto") -> str:
    """Texto principal da página, sem menus, rodapés e avisos.

    modo "auto": tenta o trafilatura (bom em artigos); se ele devolver pouco
    texto, usa a limpeza estrutural.
    modo "estrutural": só remove partes que nunca têm conteúdo (menus, rodapés,
    scripts). Mais seguro para páginas com dados em blocos, como as sessões
    de um evento, que o trafilatura às vezes descarta.
    """
    if modo == "estrutural":
        return _limpeza_estrutural(html)
    principal = ""
    try:
        import trafilatura

        principal = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True) or ""
    except Exception:
        principal = ""

    if len(principal) >= 800:
        return _compactar(principal)
    return _limpeza_estrutural(html)


def _limpeza_estrutural(html: str) -> str:
    sopa = BeautifulSoup(html, "html.parser")
    for tag in sopa(ETIQUETAS_DE_RUIDO):
        tag.decompose()
    for tag in sopa.select("[class*=cookie], [id*=cookie], [class*=menu], [class*=newsletter]"):
        tag.decompose()
    return _compactar(sopa.get_text("\n"))


def _compactar(texto: str) -> str:
    linhas = [re.sub(r"[ \t]+", " ", l).strip() for l in texto.splitlines()]
    linhas = [l for l in linhas if l]
    return "\n".join(linhas)


def estimar_tokens(texto: str) -> int:
    """Estimativa simples: cerca de 1 token a cada 4 caracteres."""
    return (len(texto) + 3) // 4


def impressao_digital(texto: str) -> str:
    """Resumo do conteúdo: se não mudar, a página não mudou desde a última leitura."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def dividir_em_trechos(texto: str, max_caracteres: int) -> list[str]:
    """Quebra textos longos em trechos, respeitando o limite de cada chamada ao LLM."""
    if len(texto) <= max_caracteres:
        return [texto] if texto else []
    trechos, atual = [], ""
    for linha in texto.splitlines():
        while len(linha) > max_caracteres:
            if atual:
                trechos.append(atual)
                atual = ""
            trechos.append(linha[:max_caracteres])
            linha = linha[max_caracteres:]
        if len(atual) + len(linha) + 1 > max_caracteres:
            trechos.append(atual)
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        trechos.append(atual)
    return trechos


MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_aparece_no_texto(data_iso: str, texto: str) -> bool:
    """Confere se o dia e o mês de uma data aparecem no texto (31/10, 31 de outubro, 31 out...).

    É uma checagem simples contra datas inventadas pela IA.
    """
    from .modelos import normalizar

    ano, mes, dia = data_iso.split("-")
    d, m = int(dia), int(mes)
    t = " " + normalizar(texto.replace("/", " barra ")) + " "
    nome = MESES[m - 1]
    padroes = [
        f" {d} barra {m} ", f" {d:02d} barra {m:02d} ", f" {d} barra {m:02d} ", f" {d:02d} barra {m} ",
        f" {d} de {nome}", f" {d:02d} de {nome}", f" {d} {nome[:3]}", f" {d:02d} {nome[:3]}",
        f" {ano} {mes} {dia} ",
    ]
    return any(p in t for p in padroes)
