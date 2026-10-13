"""Chamada ao modelo de IA, sem ficar preso a um fornecedor.

Trocar de fornecedor = mudar a variável LLM_PROVEDOR:
  - "gemini"    (padrão): API do Gemini, plano gratuito (precisa de GEMINI_API_KEY)
  - "anthropic": API do Claude, paga por uso (precisa de ANTHROPIC_API_KEY)
O modelo pode ser trocado com a variável LLM_MODELO.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

PADROES = {
    "gemini": "gemini-3.8-flash",
    "anthropic": "claude-haiku-5-5",
}


# Modelos reserva, usados quando o principal está sobrecarregado ou indisponível.
RESERVAS = {
    "gemini": ["gemini-2.5-flash-lite"],
    "anthropic": [],
}
TEMPORARIOS = {429, 500, 502, 503, 504}


class ErroLLM(RuntimeError):
    def __init__(self, status: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status = status


class LimiteDeChamadas(Exception):
    """O orçamento de chamadas desta execução acabou."""


@dataclass
class Resposta:
    texto: str
    tokens_entrada: int
    tokens_saida: int


class ClienteLLM:
    def __init__(self, max_chamadas: int = 40) -> None:
        self.provedor = (os.environ.get("LLM_PROVEDOR") or "gemini").lower()
        if self.provedor not in PADROES:
            raise ValueError(f"LLM_PROVEDOR desconhecido: {self.provedor}")
        principal = os.environ.get("LLM_MODELO") or PADROES[self.provedor]
        reserva = os.environ.get("LLM_MODELO_RESERVA")
        self.modelos = [principal] + ([reserva] if reserva else RESERVAS[self.provedor])
        self.modelo = principal
        self.max_chamadas = max_chamadas
        self.chamadas = 0

    def perguntar(self, instrucoes: str, conteudo: str) -> Resposta:
        if self.chamadas >= self.max_chamadas:
            raise LimiteDeChamadas(f"limite de {self.max_chamadas} chamadas atingido")
        self.chamadas += 1
        ultimo_erro: ErroLLM | None = None
        for modelo in self.modelos:
            self.modelo = modelo
            try:
                if self.provedor == "gemini":
                    return self._gemini(instrucoes, conteudo)
                return self._anthropic(instrucoes, conteudo)
            except ErroLLM as erro:
                # Sobrecarga (503), limite (429) ou modelo inexistente (404): tenta o próximo.
                if erro.status not in TEMPORARIOS | {404}:
                    raise
                print(f"modelo {modelo} indisponível ({erro.status}); tentando o próximo")
                ultimo_erro = erro
        raise ultimo_erro

    def _gemini(self, instrucoes: str, conteudo: str) -> Resposta:
        """Gemini pelo endereço compatível com o formato da OpenAI."""
        token = os.environ.get("GEMINI_API_KEY")
        if not token:
            raise RuntimeError("GEMINI_API_KEY ausente: cadastre a chave nos Secrets do repositório.")
        corpo = {
            "model": self.modelo,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instrucoes},
                {"role": "user", "content": conteudo},
            ],
        }
        dados = _postar(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            corpo,
        )
        uso = dados.get("usage") or {}
        return Resposta(
            texto=dados["choices"][0]["message"]["content"] or "",
            tokens_entrada=uso.get("prompt_tokens", 0),
            tokens_saida=uso.get("completion_tokens", 0),
        )

    def _anthropic(self, instrucoes: str, conteudo: str) -> Resposta:
        chave = os.environ.get("ANTHROPIC_API_KEY")
        if not chave:
            raise RuntimeError("ANTHROPIC_API_KEY ausente.")
        corpo = {
            "model": self.modelo,
            "max_tokens": 4000,
            "temperature": 0,
            # Instruções fixas em cache: chamadas seguintes pagam menos por elas.
            "system": [{"type": "text", "text": instrucoes, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": conteudo}],
        }
        dados = _postar(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": chave, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            corpo,
        )
        texto = "".join(b.get("text", "") for b in dados.get("content", []) if b.get("type") == "text")
        uso = dados.get("usage") or {}
        return Resposta(texto=texto, tokens_entrada=uso.get("input_tokens", 0), tokens_saida=uso.get("output_tokens", 0))


def _postar(url: str, cabecalhos: dict, corpo: dict, tentativas: int = 3) -> dict:
    """Envia a requisição; em erros temporários (sobrecarga, limite), espera e tenta de novo."""
    esperas = [10, 30]
    for tentativa in range(tentativas):
        resposta = httpx.post(url, headers=cabecalhos, json=corpo, timeout=120)
        if resposta.status_code in TEMPORARIOS and tentativa < tentativas - 1:
            sugerida = resposta.headers.get("retry-after")
            espera = float(sugerida) if sugerida and sugerida.replace(".", "").isdigit() else esperas[tentativa]
            time.sleep(min(espera, 90))
            continue
        if resposta.status_code == 400 and "response_format" in corpo:
            # Alguns modelos não aceitam o modo JSON; tenta sem ele.
            corpo = {k: v for k, v in corpo.items() if k != "response_format"}
            continue
        return _ler_json(resposta)
    return _ler_json(resposta)


def _ler_json(resposta: httpx.Response) -> dict:
    """Converte a resposta em JSON; se não der, mostra o que o servidor devolveu."""
    if resposta.status_code >= 400:
        raise ErroLLM(resposta.status_code, f"LLM respondeu {resposta.status_code}: {resposta.text[:300]}")
    try:
        return resposta.json()
    except ValueError as erro:
        raise RuntimeError(
            f"LLM respondeu {resposta.status_code} sem JSON "
            f"(tipo: {resposta.headers.get('content-type', '?')}): {resposta.text[:300]!r}"
        ) from erro
