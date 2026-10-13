"""Sesi Sorocaba: página carregada por JavaScript, lida com navegador (Playwright) + LLM.

É a fonte mais difícil. Além dos eventos, a primeira execução guarda em
data/depuracao/ as APIs que a página usa: se houver uma API estruturada,
como no Sesc, dá para trocar o navegador por ela e economizar tokens.
"""

from __future__ import annotations

import json
from datetime import date

from ..leitura import ler_com_navegador
from ..modelos import Evento, normalizar
from .comum import extrair_de_html, nova_metrica


def coletar(config: dict, hoje: date, *, estado: dict, llm, limites: dict, depurar) -> tuple[list[Evento], dict, str]:
    metrica = nova_metrica(config["id"])
    estado_fonte = estado.setdefault(config["id"], {})
    unidade = config.get("unidade", "SESI Sorocaba")

    pagina = ler_com_navegador(config["url"], unidade=unidade, cliques_veja_mais=config.get("cliques_veja_mais", 0))
    depurar("sesi_apis.json", json.dumps(pagina.respostas_json, ensure_ascii=False, indent=2))
    if not pagina.unidade_filtrada:
        metrica["erro"] = "filtro de unidade não encontrado; resultado pode misturar unidades"

    contexto = (
        f"Programação do SESI-SP. Extraia apenas eventos da unidade {unidade} "
        "(cidade Sorocaba). Ignore eventos de outras cidades."
    )
    eventos, texto = extrair_de_html(
        pagina.html,
        fonte=config["id"],
        link=config["url"],
        contexto=contexto,
        referencia=hoje,
        estado_fonte=estado_fonte,
        chave="listagem",
        llm=llm,
        max_caracteres=limites["max_caracteres_por_trecho"],
        metrica=metrica,
    )
    eventos = [e for e in eventos if eh_de_sorocaba(e)]
    metrica["eventos_encontrados"] = len(eventos)
    return eventos, metrica, texto


def eh_de_sorocaba(evento: Evento) -> bool:
    alvo = f"{evento.cidade or ''} {evento.local or ''} {evento.endereco or ''}"
    return "sorocaba" in normalizar(alvo)
