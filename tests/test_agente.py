"""Testes que rodam sem internet: conferem a lógica, não os sites."""

from datetime import date

from agente import armazenamento as arq
from agente.extracao import interpretar_resposta
from agente.fontes import band, sesc, sesi
from agente.fontes.comum import extrair_de_html, nova_metrica
from agente.limpeza import dividir_em_trechos, texto_bruto, texto_limpo
from agente.llm import Resposta
from agente.modelos import Evento

HOJE = date(2026, 10, 13)
CONFIG_SESC = {"id": "sesc", "nome": "Sesc Sorocaba", "unidade": "Sorocaba", "endereco": "Rua X, 1"}

ITEM_SESC = {
    "link": "/programacao/clube-de-escrita-sorocaba-12",
    "titulo": "Clube de escrita Sorocaba",
    "complemento": "Com Gustavo Araújo, escritor",
    "cancelado": "",
    "dataProxSessao": "2026-10-27T19:00",
    "dataPrimeiraSessao": "2026-10-27T19:00",
    "dataUltimaSessao": "2026-10-27T21:00",
    "tipos_linguagens": [{"titulo": "Cursos e Oficinas"}],
    "unidade": [{"name": "Sorocaba", "link": "/unidades/sorocaba"}],
    "gratuito": "Atividade gratuita",
}


def test_sesc_converte_item():
    e = sesc.converter(ITEM_SESC, CONFIG_SESC, HOJE, "agora")
    assert e.titulo == "Clube de escrita Sorocaba — Com Gustavo Araújo, escritor"
    assert e.data_inicio == "2026-10-27" and e.horario == "19:00" and e.data_fim is None
    assert e.gratuito is True and e.cidade == "Sorocaba"
    assert e.link_fonte == "https://www.sescsp.org.br/programacao/clube-de-escrita-sorocaba-12"


def test_sesc_descarta_outra_unidade_cancelado_e_passado():
    outra = {**ITEM_SESC, "unidade": [{"name": "Campinas"}]}
    cancelado = {**ITEM_SESC, "cancelado": "1"}
    passado = {**ITEM_SESC, "dataPrimeiraSessao": "2026-09-01T10:00", "dataUltimaSessao": "2026-09-01T12:00"}
    for item in (outra, cancelado, passado):
        assert sesc.converter(item, CONFIG_SESC, HOJE, "agora") is None


def test_interpreta_resposta_e_descarta_lixo():
    texto = """```json
    {"eventos": [
      {"titulo": "Show de jazz", "data_inicio": "2026-10-17", "horario": "20:00",
       "local": "Sesc Sorocaba", "cidade": "Sorocaba", "gratuito": true, "confianca": "alta"},
      {"titulo": "Sem data", "data_inicio": "sábado", "local": "Praça"},
      {"data_inicio": "2026-10-18"}
    ]}
    ```"""
    eventos = interpretar_resposta(texto, "band", "https://x", "agora")
    assert [e.titulo for e in eventos] == ["Show de jazz", "Sem data"]
    assert eventos[1].data_inicio is None and eventos[1].confianca == "baixa"
    assert interpretar_resposta("não é json", "band", "https://x", "agora") == []


def test_mesmo_evento_tem_mesmo_id_e_nao_duplica():
    a = Evento(titulo="Show de Jazz!", fonte="band", link_fonte="1", data_inicio="2026-10-17", local="Sesc Sorocaba")
    b = Evento(titulo="show de jazz", fonte="sesi", link_fonte="2", data_inicio="2026-10-17", local="SESC SOROCABA")
    assert a.id == b.id
    base = {}
    assert len(arq.mesclar(base, [a, b])) == 1


def test_limpeza_reduz_texto_e_trechos_respeitam_limite():
    html = (
        "<html><body><nav>Menu Início Contato</nav><header>Cabeçalho</header>"
        "<main><p>" + "Show no sábado às 20h no Sesc. " * 60 + "</p></main>"
        "<footer>Rodapé política de cookies</footer></body></html>"
    )
    assert "Menu" in texto_bruto(html)
    limpo = texto_limpo(html)
    assert "Menu" not in limpo and "Rodapé" not in limpo and "Show no sábado" in limpo
    trechos = dividir_em_trechos("linha\n" * 5000, 1000)
    assert all(len(t) <= 1000 for t in trechos) and len(trechos) > 1


def test_band_encontra_links_de_agenda():
    html = """
    <a href="/band-multi/sorocaba-e-regiao/noticias/agenda-cultural-sorocaba-68-202608050859">Agenda cultural</a>
    <a href="/entretenimento/carol-biazin-burning-fest-sorocaba">Carol Biazin movimentam agenda cultural de Sorocaba</a>
    <a href="/esporte/futebol">Futebol</a>
    <a href="https://outro-site.com/agenda-cultural">Fora</a>
    """
    links = band.encontrar_agendas(html, "https://www.band.com.br/band-multi/sorocaba-e-regiao", 5)
    assert links == [
        "https://www.band.com.br/band-multi/sorocaba-e-regiao/noticias/agenda-cultural-sorocaba-68-202608050859",
        "https://www.band.com.br/entretenimento/carol-biazin-burning-fest-sorocaba",
    ]


def test_band_sitemap_filtra_agendas_de_sorocaba():
    xml = """<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
    <url><loc>https://www.band.com.br/a/agenda-cultural-sorocaba-1</loc>
      <news:news><news:title>Agenda cultural: Sorocaba tem samba</news:title></news:news></url>
    <url><loc>https://www.band.com.br/b/outra</loc>
      <news:news><news:title>Agenda cultural de Curitiba</news:title></news:news></url>
    <url><loc>https://www.band.com.br/c/futebol</loc>
      <news:news><news:title>Sorocaba vence jogo</news:title></news:news></url>
    </urlset>"""
    assert band.agendas_no_sitemap(xml, 5) == ["https://www.band.com.br/a/agenda-cultural-sorocaba-1"]


def test_sesi_encontra_paginas_de_evento():
    html = """
    <a href="https://www.sesisp.org.br/evento/e918c839/astrologia">Saiba mais</a>
    <a href="/evento/c9d96ba4/movendo-territorios?x=1">Saiba mais</a>
    <a href="/eventos">Todos</a>
    """
    assert sesi.links_de_eventos(html, "https://www.sesisp.org.br/eventos") == [
        "https://www.sesisp.org.br/evento/e918c839/astrologia",
        "https://www.sesisp.org.br/evento/c9d96ba4/movendo-territorios",
    ]


class LLMFalso:
    def __init__(self):
        self.chamadas = 0

    def perguntar(self, instrucoes, conteudo):
        self.chamadas += 1
        return Resposta('{"eventos": [{"titulo": "Feira", "data_inicio": "2026-10-18", "local": "Praça"}]}', 100, 20)


def test_pagina_sem_mudanca_nao_chama_llm():
    html = "<html><body><main><p>" + "Feira no domingo na praça central. " * 40 + "</p></main></body></html>"
    llm, estado = LLMFalso(), {}
    args = dict(fonte="band", link="u", contexto="c", referencia=HOJE, estado_fonte=estado, chave="u", llm=llm, max_caracteres=16000)

    primeira, _ = extrair_de_html(html, metrica=nova_metrica("band"), **args)
    metrica = nova_metrica("band")
    segunda, _ = extrair_de_html(html, metrica=metrica, **args)

    assert len(primeira) == 1 and segunda == []
    assert llm.chamadas == 1 and metrica["paginas_sem_mudanca"] == 1


def test_llm_usa_modelo_reserva_quando_principal_esta_sobrecarregado(monkeypatch):
    from agente import llm as modulo

    monkeypatch.setenv("LLM_PROVEDOR", "gemini")
    monkeypatch.delenv("LLM_MODELO", raising=False)
    monkeypatch.delenv("LLM_MODELO_RESERVA", raising=False)
    cliente = modulo.ClienteLLM()
    usados = []

    def falso(self, instrucoes, conteudo):
        usados.append(self.modelo)
        if len(usados) == 1:
            raise modulo.ErroLLM(503, "sobrecarregado")
        return Resposta('{"eventos": []}', 10, 2)

    monkeypatch.setattr(modulo.ClienteLLM, "_gemini", falso)
    assert cliente.perguntar("i", "c").texto == '{"eventos": []}'
    assert usados == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
