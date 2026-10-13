"""Executa uma rodada de coleta: python -m agente

Lê cada fonte ativa, acrescenta os eventos novos em data/eventos.json,
atualiza a página de revisão e registra as métricas da execução.
Uma fonte com erro não interrompe as outras.
"""

from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path

import yaml

from . import armazenamento as arq
from .fontes import COLETORES
from .llm import ClienteLLM, LimiteDeChamadas


def main(caminho_config: str = "config/fontes.yaml") -> int:
    config = yaml.safe_load(Path(caminho_config).read_text(encoding="utf-8"))
    limites = config["limites"]
    hoje = date.today()

    eventos = arq.carregar_eventos()
    estado = arq.carregar_estado()
    llm = ClienteLLM(max_chamadas=limites["max_chamadas_llm_por_execucao"])
    metricas, falhas, ativas = [], 0, 0

    for fonte in config["fontes"]:
        if not fonte.get("ativa", True):
            continue
        ativas += 1
        print(f"\n== {fonte['nome']} ==")
        try:
            encontrados, metrica, amostra = COLETORES[fonte["tipo"]](
                fonte, hoje, estado=estado, llm=llm, limites=limites, depurar=arq.salvar_depuracao
            )
            if amostra:
                arq.salvar_depuracao(f"{fonte['id']}_ultima_leitura.txt", amostra)
            novos = arq.mesclar(eventos, encontrados)
            metrica["eventos_novos"] = len(novos)
            print(f"eventos encontrados: {len(encontrados)} | novos: {len(novos)} | chamadas ao LLM: {metrica['chamadas_llm']}")
        except LimiteDeChamadas as erro:
            metrica = {"fonte": fonte["id"], "erro": f"limite: {erro}"}
            print(f"parado: {erro}")
        except Exception as erro:  # noqa: BLE001 - registrar e seguir para a próxima fonte
            falhas += 1
            mensagem = " ".join(f"{type(erro).__name__}: {erro}".split())
            metrica = {"fonte": fonte["id"], "erro": mensagem[:300]}
            traceback.print_exc()
        metrica["data_execucao"] = hoje.isoformat()
        metricas.append(metrica)

    arq.salvar_eventos(eventos)
    arq.salvar_estado(estado)
    arq.registrar_metricas(metricas)
    arq.escrever_revisao(eventos, hoje)

    print(f"\nTotal de eventos na base: {len(eventos)}")
    # Se todas as fontes falharem, a execução termina com erro e o GitHub avisa por e-mail.
    return 1 if ativas and falhas == ativas else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
