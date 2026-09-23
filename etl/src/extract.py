from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

COLUNAS_ESPERADAS = [
    "Regiao - Sigla",
    "Estado - Sigla",
    "Municipio",
    "Revenda",
    "CNPJ da Revenda",
    "Bairro",
    "Cep",
    "Produto",
    "Data da Coleta",
    "Valor de Venda",
    "Unidade de Medida",
    "Bandeira",
]

TENTATIVAS_LEITURA = [ 
    {"sep": ";", "encoding": "latin1"},
    {"sep": ";", "encoding": "utf-8"},
    {"sep": ",", "encoding": "utf-8"},
]

def baixar_arquivo(url: str, pasta_destino: str | Path = "data/raw") -> Path:
    pasta_destino = Path(pasta_destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)


    extensao = ".xlsx" if url.lower().endswith(".xlsx") else ".csv"
    nome_arquivo = f"anp_precos_{datetime.now():%Y%m%d_%H%M%S}{extensao}"
    caminho_destino = pasta_destino / nome_arquivo

    logger.info("Baixando arquivo da ANP: %s", url)
    resposta = requests.get(url, timeout=30)
    resposta.raise_for_status()
 
    caminho_destino.write_bytes(resposta.content)
    logger.info("Arquivo salvo em: %s", caminho_destino)
    return caminho_destino
 
 
def ler_planilha_anp(caminho: str | Path) -> pd.DataFrame:
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
 
    if caminho.suffix.lower() == ".xlsx":
        logger.info("Lendo XLSX: %s", caminho)
        df = pd.read_excel(caminho)
        return df
 
    ultimo_erro: Exception | None = None
    for tentativa in TENTATIVAS_LEITURA:
        try:
            logger.info("Tentando ler CSV com %s", tentativa)
            df = pd.read_csv(caminho, **tentativa)
            if df.shape[1] > 1:  # separador errado geralmente gera 1 coluna só
                return df
        except (UnicodeDecodeError, pd.errors.ParserError) as erro:
            ultimo_erro = erro
            continue
 
    raise ValueError(
        f"Não foi possível ler o CSV com nenhuma combinação testada. "
        f"Último erro: {ultimo_erro}"
    )

def validar_colunas(df: pd.DataFrame, colunas_esperadas: list[str] = COLUNAS_ESPERADAS) -> None:
    colunas_faltando = [c for c in colunas_esperadas if c not in df.columns]
    if colunas_faltando:
        raise ValueError(
            f"Colunas ausentes na planilha da ANP: {colunas_faltando}. "
            f"Colunas encontradas: {df.columns.tolist()}"
        )
    logger.info("Validação de colunas OK.")
 
 
def extrair(origem: str, colunas_esperadas: list[str] = COLUNAS_ESPERADAS) -> pd.DataFrame:

    if origem.startswith("http://") or origem.startswith("https://"):
        caminho = baixar_arquivo(origem)
    else:
        caminho = Path(origem)
 
    df = ler_planilha_anp(caminho)
    validar_colunas(df, colunas_esperadas)
    logger.info("Extração concluída: %d linhas, %d colunas.", *df.shape)
    return df
 
 
if __name__ == "__main__":
    pass