from . import band, sesc, sesi

COLETORES = {
    "api_sesc": sesc.coletar,
    "band_agenda": band.coletar,
    "navegador": sesi.coletar,
}
