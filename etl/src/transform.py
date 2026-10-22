"""
transform.py

Etapa de TRANSFORMAÇÃO do ETL de preços de combustíveis (ANP).

Recebe o DataFrame bruto validado pelo extract.py (layout real da planilha
"Preços por posto revendedor") e devolve um DataFrame limpo, com nomes de
colunas em snake_case e tipos corretos, pronto para ser carregado no MySQL.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from utils import normalizar_texto, para_sigla_uf

logger = logging.getLogger(__name__)

# Mapeamento: nome na planilha da ANP (já padronizado pelo extract) -> nome interno
RENOMEAR_COLUNAS = {
    "CNPJ": "cnpj",
    "RAZÃO": "razao",
    "FANTASIA": "fantasia",
    "ENDEREÇO": "logradouro",
    "NÚMERO": "numero",
    "COMPLEMENTO": "complemento",
    "Bairro": "bairro",
    "Cep": "cep",
    "Municipio": "municipio",
    "ESTADO": "estado",
    "Bandeira": "bandeira",
    "Produto": "produto",
    "Unidade de Medida": "unidade_medida",
    "PREÇO DE REVENDA": "preco_venda",
    "Data da Coleta": "data_coleta",
}

# A planilha traz "GASOLINA COMUM"; "GASOLINA" fica por compatibilidade.
PRODUTOS_PADRAO = ["GASOLINA", "GASOLINA COMUM", "GASOLINA ADITIVADA"]

COLUNAS_TEXTO = ["razao", "fantasia", "logradouro", "complemento", "bairro",
                 "municipio", "estado", "bandeira", "produto", "unidade_medida"]

# Colunas que seguem para o banco (na ordem)
COLUNAS_FINAIS = ["cnpj", "revenda", "endereco", "bairro", "cep", "municipio", "estado",
                  "bandeira", "produto", "unidade_medida", "preco_venda", "data_coleta"]


def apenas_digitos(valor, tamanho: int | None = None) -> str | None:
    """
    Remove tudo que não for dígito. Se `tamanho` for informado, preenche
    com zeros à esquerda e devolve None se o resultado exceder o tamanho
    ou vier vazio (dado inválido).

    Aceita números vindos do Excel: 11111111000111.0 vira "11111111000111"
    (sem o ".0" virar um dígito a mais).
    """
    if pd.isna(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
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


def _limpar(valor) -> str | None:
    """Texto sem espaços repetidos; None para nulo ou vazio."""
    if pd.isna(valor):
        return None
    texto = " ".join(str(valor).split())
    return texto or None


def formatar_numero(valor) -> str | None:
    """Número do endereço: 1852.0 -> '1852'; 'S/N' continua 'S/N'."""
    if pd.isna(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return _limpar(valor)


def montar_endereco(logradouro, numero, complemento) -> str | None:
    """Junta os três campos: 'AV PAULISTA, 1000 - LOJA 1'."""
    rua = _limpar(logradouro)
    num = formatar_numero(numero)
    comp = _limpar(complemento)

    endereco = rua or ""
    if num:
        endereco = f"{endereco}, {num}" if endereco else num
    if comp:
        endereco = f"{endereco} - {comp}" if endereco else comp
    return endereco or None


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
      4. converte o estado (por extenso ou sigla) para sigla e, se informado,
         filtra por estado e/ou lista de municípios (sem acento, sem caixa)
      5. define o nome do posto (fantasia, ou razão social se vazio) e monta o endereço
      6. normaliza CNPJ (14 dígitos) e CEP (8 dígitos)
      7. converte preço e data
      8. descarta linhas inválidas e duplicadas
    """
    produtos = [p.upper() for p in (produtos or PRODUTOS_PADRAO)]
    total_inicial = len(df)

    out = df[list(RENOMEAR_COLUNAS)].rename(columns=RENOMEAR_COLUNAS).copy()

    for coluna in COLUNAS_TEXTO:
        out[coluna] = out[coluna].astype("string").str.strip().str.upper()

    out = out[out["produto"].isin(produtos)].copy()

    out["estado"] = out["estado"].map(para_sigla_uf)
    if estado:
        out = out[out["estado"] == para_sigla_uf(estado)].copy()

    if municipios:
        alvo = {normalizar_texto(m) for m in municipios}
        out = out[out["municipio"].map(normalizar_texto).isin(alvo)].copy()

    sem_fantasia = (out["fantasia"].isna() | (out["fantasia"] == "")).fillna(True).astype(bool)
    out["revenda"] = out["fantasia"].where(~sem_fantasia, out["razao"])
    out["endereco"] = [
        montar_endereco(rua, num, comp)
        for rua, num, comp in zip(out["logradouro"], out["numero"], out["complemento"])
    ]

    out["cnpj"] = out["cnpj"].map(lambda v: apenas_digitos(v, 14))
    out["cep"] = out["cep"].map(lambda v: apenas_digitos(v, 8))

    out["preco_venda"] = converter_preco(out["preco_venda"])
    out["data_coleta"] = pd.to_datetime(out["data_coleta"], dayfirst=True, errors="coerce")

    # Sem CNPJ, preço válido ou data, a linha não serve para a análise
    out = out.dropna(subset=["cnpj", "preco_venda", "data_coleta"])
    out = out[out["preco_venda"] > 0]

    out = out.drop_duplicates(subset=["cnpj", "produto", "data_coleta"], keep="last")
    out = out[COLUNAS_FINAIS].reset_index(drop=True)

    logger.info("Transformação concluída: %d -> %d linhas.", total_inicial, len(out))
    return out
