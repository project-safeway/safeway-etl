"""
transform.py

Etapa de TRANSFORMAÇÃO do ETL de preços de combustíveis (ANP).

Recebe o DataFrame bruto validado pelo extract.py e devolve um DataFrame
limpo, com nomes de colunas em snake_case e tipos corretos, pronto para
ser carregado no MySQL.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from utils import normalizar_texto

logger = logging.getLogger(__name__)

# Mapeamento: nome na planilha da ANP -> nome no banco
RENOMEAR_COLUNAS = {
    "Regiao - Sigla": "regiao",
    "Estado - Sigla": "estado",
    "Municipio": "municipio",
    "Revenda": "revenda",
    "CNPJ da Revenda": "cnpj",
    "Bairro": "bairro",
    "Cep": "cep",
    "Produto": "produto",
    "Data da Coleta": "data_coleta",
    "Valor de Venda": "preco_venda",
    "Unidade de Medida": "unidade_medida",
    "Bandeira": "bandeira",
}

PRODUTOS_PADRAO = ["GASOLINA", "GASOLINA ADITIVADA"]

COLUNAS_TEXTO = ["regiao", "estado", "municipio", "revenda", "bairro",
                 "produto", "unidade_medida", "bandeira"]


def apenas_digitos(valor, tamanho: int | None = None) -> str | None:
    """
    Remove tudo que não for dígito. Se `tamanho` for informado, preenche
    com zeros à esquerda e devolve None se o resultado exceder o tamanho
    ou vier vazio (dado inválido).
    """
    if pd.isna(valor):
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if not digitos:
        return None
    if tamanho is None:
        return digitos
    digitos = digitos.zfill(tamanho)
    return digitos if len(digitos) == tamanho else None


def converter_preco(serie: pd.Series) -> pd.Series:
    """
    Converte preços para float. Aceita '5,79' (vírgula decimal), '5.79'
    e números já numéricos. Valores inválidos viram NaN.
    """
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    texto = serie.astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def transformar(
    df: pd.DataFrame,
    produtos: list[str] | None = None,
    municipios: list[str] | None = None,
    estado: str | None = None,
) -> pd.DataFrame:
    """
    Pipeline de transformação:
      1. seleciona e renomeia colunas
      2. padroniza textos (strip + maiúsculas)
      3. filtra os produtos de interesse (padrão: gasolina comum e aditivada)
      3b. se informado, filtra por estado e/ou lista de municípios
          (comparação sem acento e sem diferenciar maiúsculas)
      4. normaliza CNPJ (14 dígitos) e CEP (8 dígitos)
      5. converte preço e data
      6. descarta linhas inválidas e duplicadas
    """
    produtos = [p.upper() for p in (produtos or PRODUTOS_PADRAO)]
    total_inicial = len(df)

    out = df[list(RENOMEAR_COLUNAS)].rename(columns=RENOMEAR_COLUNAS).copy()

    for coluna in COLUNAS_TEXTO:
        out[coluna] = out[coluna].astype("string").str.strip().str.upper()

    out = out[out["produto"].isin(produtos)].copy()

    if estado:
        out = out[out["estado"] == normalizar_texto(estado)].copy()

    if municipios:
        alvo = {normalizar_texto(m) for m in municipios}
        out = out[out["municipio"].map(normalizar_texto).isin(alvo)].copy()

    out["cnpj"] = out["cnpj"].map(lambda v: apenas_digitos(v, 14))
    out["cep"] = out["cep"].map(lambda v: apenas_digitos(v, 8))

    out["preco_venda"] = converter_preco(out["preco_venda"])
    out["data_coleta"] = pd.to_datetime(out["data_coleta"], dayfirst=True, errors="coerce")

    # Sem CNPJ, preço válido ou data, a linha não serve para a análise
    out = out.dropna(subset=["cnpj", "preco_venda", "data_coleta"])
    out = out[out["preco_venda"] > 0]

    out = out.drop_duplicates(subset=["cnpj", "produto", "data_coleta"], keep="last")
    out = out.reset_index(drop=True)

    logger.info("Transformação concluída: %d -> %d linhas.", total_inicial, len(out))
    return out