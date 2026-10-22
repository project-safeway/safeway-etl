"""
load.py

Etapa de CARGA do ETL: grava o DataFrame transformado no banco com UPSERT.

Se já existir uma linha com o mesmo (cnpj, produto, data_coleta), ela é
atualizada; senão, é inserida. Assim a carga pode rodar várias vezes com
segurança e o banco acumula o histórico semana a semana.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pandas as pd
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from db import CHAVE_UNICA, precos_combustiveis

logger = logging.getLogger(__name__)

COLUNAS_OBRIGATORIAS = [
    "cnpj", "produto", "data_coleta", "regiao", "estado", "municipio",
    "revenda", "bairro", "cep", "preco_venda", "unidade_medida", "bandeira",
]

# Colunas que são atualizadas quando o registro já existe (tudo, menos a chave)
COLUNAS_ATUALIZAVEIS = [c for c in COLUNAS_OBRIGATORIAS if c not in CHAVE_UNICA]


def _valor_para_banco(coluna: str, valor):
    """Converte um valor do pandas para algo que o driver do banco aceita."""
    if pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if coluna == "preco_venda":
        return Decimal(str(round(float(valor), 3)))
    return valor


def preparar_registros(df: pd.DataFrame) -> list[dict]:
    """
    Transforma o DataFrame em lista de dicionários prontos para inserir:
    NaN/NA viram None, Timestamp vira date e o preço vira Decimal.
    """
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes no DataFrame para carga: {faltando}")

    registros = df[COLUNAS_OBRIGATORIAS].to_dict("records")
    return [
        {coluna: _valor_para_banco(coluna, valor) for coluna, valor in registro.items()}
        for registro in registros
    ]


def _montar_upsert(engine: Engine):
    """Monta o INSERT ... ON DUPLICATE KEY UPDATE conforme o banco em uso."""
    dialeto = engine.dialect.name

    if dialeto == "mysql":
        stmt = mysql_insert(precos_combustiveis)
        return stmt.on_duplicate_key_update(
            {c: stmt.inserted[c] for c in COLUNAS_ATUALIZAVEIS}
        )
    if dialeto == "sqlite":  # usado nos testes
        stmt = sqlite_insert(precos_combustiveis)
        return stmt.on_conflict_do_update(
            index_elements=CHAVE_UNICA,
            set_={c: stmt.excluded[c] for c in COLUNAS_ATUALIZAVEIS},
        )
    raise NotImplementedError(f"Upsert não implementado para o banco '{dialeto}'.")


def carregar(df: pd.DataFrame, engine: Engine, tamanho_lote: int = 1000) -> int:
    """
    Grava o DataFrame na tabela `precos_combustiveis` em lotes, dentro de uma
    única transação (se algum lote falhar, nada é gravado).

    Retorna a quantidade de registros processados.
    """
    registros = preparar_registros(df)
    if not registros:
        logger.warning("Nenhum registro para carregar.")
        return 0

    stmt = _montar_upsert(engine)

    with engine.begin() as conexao:
        for inicio in range(0, len(registros), tamanho_lote):
            lote = registros[inicio:inicio + tamanho_lote]
            conexao.execute(stmt, lote)
            logger.info("Lote gravado: %d registros.", len(lote))

    logger.info("Carga concluída: %d registros processados.", len(registros))
    return len(registros)