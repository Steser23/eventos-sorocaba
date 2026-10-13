"""Etapas comuns às fontes que precisam do LLM: limpar, detectar mudança, extrair."""

from __future__ import annotations

from datetime import date, datetime, timezone

from ..extracao import INSTRUCOES, interpretar_resposta, montar_conteudo
from ..limpeza import (
    data_aparece_no_texto,
    dividir_em_trechos,
    estimar_tokens,
    impressao_digital,
    texto_bruto,
    texto_limpo,
)
from ..llm import ClienteLLM
from ..modelos import Evento


def nova_metrica(fonte: str) -> dict:
    return {
        "fonte": fonte, "paginas_lidas": 0, "paginas_sem_mudanca": 0,
        "caracteres_brutos": 0, "caracteres_limpos": 0,
        "tokens_estimados_brutos": 0, "tokens_estimados_limpos": 0,
        "chamadas_llm": 0, "tokens_entrada_api": 0, "tokens_saida_api": 0,
        "eventos_encontrados": 0, "eventos_novos": 0, "erro": "",
    }


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extrair_de_html(
    html: str,
    *,
    fonte: str,
    link: str,
    contexto: str,
    referencia: date,
    estado_fonte: dict,
    chave: str,
    llm: ClienteLLM,
    max_caracteres: int,
    metrica: dict,
    modo_limpeza: str = "auto",
) -> tuple[list[Evento], str]:
    """Extrai eventos de uma página. Se o texto for igual ao da última leitura, não chama o LLM.

    Devolve os eventos e o texto limpo (para depuração).
    """
    bruto = texto_bruto(html)
    limpo = texto_limpo(html, modo=modo_limpeza)
    metrica["paginas_lidas"] += 1
    metrica["caracteres_brutos"] += len(bruto)
    metrica["caracteres_limpos"] += len(limpo)
    metrica["tokens_estimados_brutos"] += estimar_tokens(bruto)
    metrica["tokens_estimados_limpos"] += estimar_tokens(limpo)

    digital = impressao_digital(limpo)
    if estado_fonte.get(chave) == digital:
        metrica["paginas_sem_mudanca"] += 1
        return [], limpo

    eventos: list[Evento] = []
    coletado = agora_iso()
    for trecho in dividir_em_trechos(limpo, max_caracteres):
        resposta = llm.perguntar(INSTRUCOES, montar_conteudo(trecho, referencia, contexto))
        metrica["chamadas_llm"] += 1
        metrica["tokens_entrada_api"] += resposta.tokens_entrada
        metrica["tokens_saida_api"] += resposta.tokens_saida
        for evento in interpretar_resposta(resposta.texto, fonte, link, coletado):
            # Data que não aparece no texto lido é suspeita: vai para revisão com confiança baixa.
            if evento.data_inicio and not data_aparece_no_texto(evento.data_inicio, trecho):
                evento.confianca = "baixa"
            eventos.append(evento)

    # Só marca como lida depois de extrair tudo: se algo falhar, tenta de novo amanhã.
    estado_fonte[chave] = digital
    return eventos, limpo
