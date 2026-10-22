"""
db.py

Conexão com o banco (MySQL local, via SQLAlchemy) e definição da tabela.

A URL de conexão vem da variável de ambiente DATABASE_URL (pode ficar num
arquivo .env na raiz do projeto), por exemplo:

    DATABASE_URL=mysql+pymysql://usuario:senha@localhost:3306/safeway?charset=utf8mb4
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Date,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

metadata = MetaData()

# Chave natural: um preço por posto (CNPJ), produto e data de coleta.
# É ela que garante que rodar a carga duas vezes não duplica dados.
CHAVE_UNICA = ["cnpj", "produto", "data_coleta"]

precos_combustiveis = Table(
    "precos_combustiveis",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cnpj", String(14), nullable=False),
    Column("produto", String(30), nullable=False),
    Column("data_coleta", Date, nullable=False),
    Column("estado", String(2)),
    Column("municipio", String(100)),
    Column("revenda", String(150)),
    Column("endereco", String(255)),
    Column("bairro", String(100)),
    Column("cep", String(8)),
    Column("preco_venda", Numeric(8, 3), nullable=False),
    Column("unidade_medida", String(30)),
    Column("bandeira", String(50)),
    UniqueConstraint(*CHAVE_UNICA, name="uq_posto_produto_data"),
    # Consulta típica da IA: postos de um município, por produto e data
    Index("ix_municipio_produto_data", "municipio", "produto", "data_coleta"),
)


def get_engine(url: str | None = None) -> Engine:
    """
    Cria o engine do SQLAlchemy. Se `url` não for informada, lê DATABASE_URL
    do ambiente (carregando o .env, se existir).
    """
    if url is None:
        load_dotenv()
        url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "URL do banco não informada. Defina DATABASE_URL no ambiente/.env "
            "ou passe a url para get_engine()."
        )
    return create_engine(url, pool_pre_ping=True)


def criar_tabelas(engine: Engine) -> None:
    """Cria as tabelas que ainda não existem (não mexe nas existentes)."""
    metadata.create_all(engine)
    logger.info("Tabelas verificadas/criadas.")
