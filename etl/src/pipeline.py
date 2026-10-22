from __future__ import annotations

import logging

from sqlalchemy.engine import Engine

from config import ESTADO_PADRAO, MUNICIPIOS_GRANDE_SP
from extract import extrair, obter_url_planilha_da_semana
from load import carregar
from transform import transformar

logger = logging.getLogger(__name__)


def executar_pipeline(
    origem: str,
    engine: Engine,
    municipios: list[str] | None = MUNICIPIOS_GRANDE_SP,
    estado: str | None = ESTADO_PADRAO,
    produtos: list[str] | None = None,
) -> dict:
    """
    Roda o ETL completo a partir de uma URL ou caminho de arquivo.
    Devolve um resumo com a contagem de linhas de cada etapa.

    Levanta RuntimeError se nada sobrar após a transformação: numa execução
    agendada isso é quase sempre sinal de problema (layout da ANP mudou,
    nome de produto diferente...) e deve falhar de forma visível.
    """
    bruto = extrair(origem)
    limpo = transformar(bruto, produtos=produtos, municipios=municipios, estado=estado)

    if limpo.empty:
        raise RuntimeError(
            f"Nenhuma linha restou após a transformação ({len(bruto)} extraídas). "
            "Verifique filtros de produto/município e o layout da planilha."
        )

    gravados = carregar(limpo, engine)
    resumo = {
        "linhas_extraidas": len(bruto),
        "linhas_transformadas": len(limpo),
        "linhas_carregadas": gravados,
    }
    logger.info("Pipeline concluído: %s", resumo)
    return resumo


def executar_semanal(pagina_url: str, engine: Engine, **kwargs) -> dict:
    """Descobre a planilha mais recente na página da ANP e roda o pipeline."""
    url_planilha = obter_url_planilha_da_semana(pagina_url)
    return executar_pipeline(url_planilha, engine, **kwargs)