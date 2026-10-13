"""Formato padrão de um evento, igual para todas as fontes."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Optional


def normalizar(texto: Optional[str]) -> str:
    """Minúsculas, sem acentos e sem pontuação, para comparar textos."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9 ]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


@dataclass
class Evento:
    titulo: str
    fonte: str
    link_fonte: str
    data_inicio: Optional[str] = None   # AAAA-MM-DD
    data_fim: Optional[str] = None      # AAAA-MM-DD
    horario: Optional[str] = None       # HH:MM
    local: Optional[str] = None
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    preco: Optional[str] = None
    gratuito: Optional[bool] = None
    categoria: Optional[str] = None
    descricao: Optional[str] = None     # resumo curto, escrito com palavras próprias
    cancelado: bool = False
    confianca: str = "alta"             # alta | media | baixa
    status: str = "pendente_revisao"    # pendente_revisao | aprovado | rejeitado
    coletado_em: Optional[str] = None
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.chave()

    def chave(self) -> str:
        """Identificador estável: mesmo título + data + local = mesmo evento."""
        base = "|".join(
            [
                normalizar(self.titulo)[:80],
                (self.data_inicio or "")[:10],
                normalizar(self.local)[:30],
            ]
        )
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]

    def para_dict(self) -> dict:
        return asdict(self)
