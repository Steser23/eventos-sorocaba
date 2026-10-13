"""Extração de eventos de um texto livre com o LLM."""

from __future__ import annotations

import json
import re
from datetime import date

from .modelos import Evento

INSTRUCOES = """Você extrai eventos de textos de agendas culturais de Sorocaba (SP) e região.

Responda SOMENTE com JSON no formato:
{"eventos": [{"titulo": "...", "data_inicio": "AAAA-MM-DD", "data_fim": "AAAA-MM-DD ou null",
"horario": "HH:MM ou null", "local": "...", "endereco": "... ou null", "cidade": "...",
"preco": "... ou null", "gratuito": true/false/null, "categoria": "...",
"descricao": "...", "confianca": "alta|media|baixa"}]}

Regras:
- Um item por evento. Ignore propagandas, menus, notícias e textos que não sejam eventos.
- Use a data de referência para completar o ano de datas como "sábado (19/09)".
- Nunca invente: se uma informação não estiver no texto, use null.
- "cidade" é a cidade onde o evento acontece (Sorocaba, Votorantim, Itu...).
- "categoria": uma entre música, teatro, dança, cinema, exposição, feira, gastronomia,
  infantil, esporte, curso, festa, literatura, outro.
- "descricao": uma frase curta escrita com suas próprias palavras, nunca copiada do texto.
- "confianca": "baixa" se a data ou o local forem incertos.
- Se não houver eventos, responda {"eventos": []}.
"""

DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HORA = re.compile(r"^\d{2}:\d{2}$")


def montar_conteudo(trecho: str, referencia: date, contexto: str) -> str:
    return f"Data de referência: {referencia.isoformat()}\nFonte: {contexto}\n\nTexto:\n{trecho}"


def interpretar_resposta(texto: str, fonte: str, link: str, coletado_em: str) -> list[Evento]:
    """Converte a resposta do LLM em eventos, descartando o que vier malformado."""
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio == -1 or fim == -1:
            return []
        try:
            dados = json.loads(texto[inicio : fim + 1])
        except json.JSONDecodeError:
            return []

    eventos = []
    for item in dados.get("eventos", []) if isinstance(dados, dict) else []:
        if not isinstance(item, dict) or not item.get("titulo"):
            continue
        data_inicio = _valido(item.get("data_inicio"), DATA_ISO)
        confianca = item.get("confianca") if item.get("confianca") in {"alta", "media", "baixa"} else "media"
        if not data_inicio:
            confianca = "baixa"
        eventos.append(
            Evento(
                titulo=str(item["titulo"]).strip(),
                fonte=fonte,
                link_fonte=link,
                data_inicio=data_inicio,
                data_fim=_valido(item.get("data_fim"), DATA_ISO),
                horario=_valido(item.get("horario"), HORA),
                local=_texto(item.get("local")),
                endereco=_texto(item.get("endereco")),
                cidade=_texto(item.get("cidade")),
                preco=_texto(item.get("preco")),
                gratuito=item.get("gratuito") if isinstance(item.get("gratuito"), bool) else None,
                categoria=_texto(item.get("categoria")),
                descricao=_texto(item.get("descricao")),
                confianca=confianca,
                coletado_em=coletado_em,
            )
        )
    return eventos


def _valido(valor, padrao: re.Pattern) -> str | None:
    if isinstance(valor, str) and padrao.match(valor.strip()):
        return valor.strip()
    return None


def _texto(valor) -> str | None:
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None
