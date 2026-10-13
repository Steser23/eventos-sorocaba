# eventos-sorocaba

Agente que coleta, todos os dias, a programação cultural de Sorocaba (SP) para alimentar uma newsletter-concierge de eventos personalizada.

Projeto de portfólio de produto, em fase de piloto.

## Como funciona

| Fonte | Como é lida | Usa IA? |
| --- | --- | --- |
| Sesc Sorocaba | API pública do Sesc, com dados já estruturados | Não |
| Agenda cultural da Band | Leitura simples da página + extração com IA | Sim |
| Sesi Sorocaba | Navegador automatizado (Playwright), pois a página carrega por JavaScript + extração com IA | Sim |

Para gastar poucos tokens, o agente:

1. limpa o texto antes de enviá-lo à IA (remove menus, rodapés e avisos);
2. não chama a IA quando a página não mudou desde a última leitura;
3. nunca reprocessa uma matéria da Band já lida;
4. respeita um limite de chamadas por execução.

A IA usada por padrão é o **GitHub Models**, gratuito dentro do GitHub Actions. Para trocar de fornecedor, crie a variável `LLM_PROVEDOR` em *Settings → Secrets and variables → Actions → Variables* (`github` ou `anthropic`).

## Onde ver os resultados

- [`data/revisao.md`](data/revisao.md): eventos futuros aguardando revisão.
- [`data/eventos.json`](data/eventos.json): base completa de eventos.
- [`data/metricas.csv`](data/metricas.csv): números de cada execução (páginas lidas, tokens antes e depois da limpeza, chamadas à IA, eventos novos, erros).
- `data/depuracao/`: amostras da última leitura de cada fonte, para diagnóstico.

## Como rodar

O agente roda sozinho todos os dias às 06h17 (horário de Brasília). Para rodar na hora: aba **Actions → Coleta de eventos → Run workflow**.

Se todas as fontes falharem, a execução fica vermelha e o GitHub avisa.

## Estrutura

```
config/fontes.yaml       fontes ativas e limites
agente/__main__.py       rodada de coleta
agente/fontes/           um arquivo por fonte
agente/limpeza.py        limpeza de texto e detecção de mudança
agente/llm.py            chamada à IA, independente de fornecedor
agente/extracao.py       instruções e leitura da resposta da IA
tests/                   testes que rodam sem internet
```

## Regras de conteúdo

As descrições são reescritas, cada evento aponta para a fonte original, e imagens ou textos das fontes não são republicados.
