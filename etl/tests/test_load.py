"""
Testes da etapa de carga (db.py e load.py).

Usam SQLite em memória para não depender de um MySQL rodando. O comando
específico do MySQL (ON DUPLICATE KEY UPDATE) é validado compilando o SQL.

Rodar com:
    python -m pytest tests/test_load.py -v
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import mysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db import criar_tabelas, get_engine, precos_combustiveis
from load import _montar_upsert, carregar, preparar_registros


# ---------- Helpers / fixtures ----------

def linha(**sobrescrever) -> dict:
    """Uma linha já transformada (formato que sai do transform.py)."""
    base = {
        "cnpj": "11111111000111",
        "produto": "GASOLINA",
        "data_coleta": pd.Timestamp("2026-09-12"),
        "estado": "SP",
        "municipio": "SAO PAULO",
        "revenda": "POSTO EXEMPLO",
        "endereco": "AV PAULISTA, 1000 - LOJA 1",
        "bairro": "CENTRO",
        "cep": "01000000",
        "preco_venda": 5.79,
        "unidade_medida": "R$ / LITRO",
        "bandeira": "BRANCA",
    }
    base.update(sobrescrever)
    return base


def df_de(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    criar_tabelas(eng)
    return eng


def contar(engine) -> int:
    with engine.connect() as con:
        return con.execute(select(func.count()).select_from(precos_combustiveis)).scalar()


def buscar_todos(engine):
    with engine.connect() as con:
        return con.execute(select(precos_combustiveis)).mappings().all()


# ---------- db.py ----------

def test_criar_tabelas_cria_a_tabela(engine):
    from sqlalchemy import inspect
    assert "precos_combustiveis" in inspect(engine).get_table_names()


def test_get_engine_sem_url_levanta_erro(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Evita que um .env real da máquina interfira no teste
    monkeypatch.setattr("db.load_dotenv", lambda *a, **k: None)

    with pytest.raises(ValueError):
        get_engine()


def test_get_engine_le_url_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setattr("db.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    eng = get_engine()

    assert eng.dialect.name == "sqlite"


# ---------- preparar_registros ----------

def test_preparar_registros_converte_tipos():
    registros = preparar_registros(df_de(linha()))

    assert registros[0]["data_coleta"] == date(2026, 9, 12)
    assert registros[0]["preco_venda"] == Decimal("5.79")
    assert isinstance(registros[0]["preco_venda"], Decimal)


def test_preparar_registros_converte_nulos_em_none():
    df = df_de(linha(bairro=pd.NA, bandeira=None))
    df["bairro"] = df["bairro"].astype("string")

    registros = preparar_registros(df)

    assert registros[0]["bairro"] is None
    assert registros[0]["bandeira"] is None


def test_preparar_registros_exige_todas_as_colunas():
    df = df_de(linha()).drop(columns=["bandeira"])

    with pytest.raises(ValueError) as erro:
        preparar_registros(df)

    assert "bandeira" in str(erro.value)


# ---------- carregar ----------

def test_carregar_insere_registros(engine):
    df = df_de(
        linha(),
        linha(cnpj="22222222000122", preco_venda=5.99),
    )

    processados = carregar(df, engine)

    assert processados == 2
    assert contar(engine) == 2


def test_carregar_e_idempotente(engine):
    df = df_de(linha())

    carregar(df, engine)
    carregar(df, engine)

    assert contar(engine) == 1


def test_carregar_atualiza_preco_quando_registro_ja_existe(engine):
    carregar(df_de(linha(preco_venda=5.79)), engine)
    carregar(df_de(linha(preco_venda=5.89)), engine)

    registros = buscar_todos(engine)

    assert len(registros) == 1
    assert float(registros[0]["preco_venda"]) == pytest.approx(5.89)


def test_carregar_acumula_historico_de_datas_diferentes(engine):
    carregar(df_de(linha(data_coleta=pd.Timestamp("2026-09-05"))), engine)
    carregar(df_de(linha(data_coleta=pd.Timestamp("2026-09-12"))), engine)

    assert contar(engine) == 2


def test_carregar_dataframe_vazio_retorna_zero(engine):
    df = df_de(linha()).iloc[0:0]

    assert carregar(df, engine) == 0
    assert contar(engine) == 0


def test_carregar_em_lotes_pequenos(engine):
    df = df_de(*[linha(cnpj=f"{i:014d}") for i in range(1, 6)])

    processados = carregar(df, engine, tamanho_lote=2)  # 3 lotes: 2 + 2 + 1

    assert processados == 5
    assert contar(engine) == 5


def test_carregar_faz_rollback_se_um_lote_falhar(engine):
    # O último registro viola NOT NULL (produto vazio) e derruba a transação inteira
    df = df_de(
        linha(cnpj="00000000000001"),
        linha(cnpj="00000000000002"),
        linha(cnpj="00000000000003", produto=None),
    )

    with pytest.raises(Exception):
        carregar(df, engine, tamanho_lote=2)

    assert contar(engine) == 0


# ---------- SQL do MySQL ----------

def test_upsert_mysql_usa_on_duplicate_key_update():
    # Engine falso: não conecta em nada, só expõe o dialeto para o _montar_upsert
    class EngineFalso:
        dialect = mysql.dialect()

    stmt = _montar_upsert(EngineFalso())
    sql = str(stmt.compile(dialect=mysql.dialect()))

    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "preco_venda" in sql


def test_carregar_corta_textos_maiores_que_a_coluna(engine):
    texto_gigante = "A" * 500  # a coluna endereco aceita 255
    carregar(df_de(linha(endereco=texto_gigante)), engine)

    registros = buscar_todos(engine)

    assert len(registros[0]["endereco"]) == 255
