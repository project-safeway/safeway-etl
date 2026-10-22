"""
Testes de integração do pipeline e do main.py (extract -> transform -> load),
com CSV local e SQLite em memória (sem internet, sem MySQL).

Rodar com:
    python -m pytest tests/test_pipeline.py -v
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))

from db import criar_tabelas, precos_combustiveis
from pipeline import executar_pipeline, executar_semanal
import main as main_modulo

CABECALHO = (
    "CNPJ;RAZÃO;FANTASIA;ENDEREÇO;NÚMERO;COMPLEMENTO;BAIRRO;CEP;MUNICÍPIO;ESTADO;"
    "BANDEIRA;PRODUTO;UNIDADE DE MEDIDA;PREÇO DE REVENDA;DATA DA COLETA\n"
)


def _posto(cnpj, municipio, estado, produto, preco):
    return (f"{cnpj};RAZAO {cnpj};POSTO {cnpj};RUA A;10;;CENTRO;01000-000;{municipio};"
            f"{estado};BRANCA;{produto};R$ / litro;{preco};12/10/2026\n")


CSV = CABECALHO + (
    # Dentro do escopo (Grande SP, gasolina; acento/caixa diferentes do config)
    _posto("11111111000111", "SÃO PAULO", "SAO PAULO", "GASOLINA COMUM", "5,79")
    + _posto("22222222000122", "SANTO ANDRE", "SAO PAULO", "GASOLINA ADITIVADA", "6,09")
    # Fora do escopo: município, produto e estado
    + _posto("33333333000133", "CAMPINAS", "SAO PAULO", "GASOLINA COMUM", "5,59")
    + _posto("44444444000144", "SAO PAULO", "SAO PAULO", "ETANOL", "4,19")
    + _posto("55555555000155", "SANTA ISABEL", "PARA", "GASOLINA COMUM", "6,99")
)


@pytest.fixture(autouse=True)
def limpar_handlers_de_arquivo():
    """O main() registra um handler de arquivo global; isola e fecha entre testes."""
    def remover():
        raiz = logging.getLogger()
        for h in list(raiz.handlers):
            if isinstance(h, RotatingFileHandler):
                h.close()
                raiz.removeHandler(h)
    remover()
    yield
    remover()


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    criar_tabelas(eng)
    return eng


@pytest.fixture
def csv_anp(tmp_path) -> Path:
    caminho = tmp_path / "anp.csv"
    caminho.write_text(CSV, encoding="latin1")
    return caminho


def contar(engine) -> int:
    with engine.connect() as con:
        return con.execute(select(func.count()).select_from(precos_combustiveis)).scalar()


# ---------- executar_pipeline ----------

def test_pipeline_filtra_escopo_e_carrega_no_banco(csv_anp, engine):
    resumo = executar_pipeline(str(csv_anp), engine)

    assert resumo == {
        "linhas_extraidas": 5,
        "linhas_transformadas": 2,  # só Grande SP + gasolina
        "linhas_carregadas": 2,
    }
    assert contar(engine) == 2


def test_pipeline_rodado_duas_vezes_nao_duplica(csv_anp, engine):
    executar_pipeline(str(csv_anp), engine)
    executar_pipeline(str(csv_anp), engine)

    assert contar(engine) == 2


def test_pipeline_falha_quando_nada_sobra_apos_filtros(csv_anp, engine):
    with pytest.raises(RuntimeError):
        executar_pipeline(str(csv_anp), engine, municipios=["Município Inexistente"])

    assert contar(engine) == 0


# ---------- executar_semanal ----------

def test_executar_semanal_descobre_url_e_roda_pipeline(engine):
    with patch("pipeline.obter_url_planilha_da_semana", return_value="https://x/anp.xlsx") as achar, \
         patch("pipeline.executar_pipeline", return_value={"ok": 1}) as rodar:
        resumo = executar_semanal("https://www.gov.br/anp/pagina", engine)

    achar.assert_called_once_with("https://www.gov.br/anp/pagina")
    assert rodar.call_args.args[0] == "https://x/anp.xlsx"
    assert resumo == {"ok": 1}


# ---------- main ----------

def test_main_com_origem_local_retorna_zero_e_grava(csv_anp, tmp_path, monkeypatch):
    banco = tmp_path / "teste.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{banco.as_posix()}")

    codigo = main_modulo.main(["--origem", str(csv_anp)])

    assert codigo == 0
    eng = create_engine(f"sqlite:///{banco.as_posix()}")
    assert contar(eng) == 2


def test_main_sem_database_url_retorna_um(csv_anp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("main.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("db.load_dotenv", lambda *a, **k: None)

    assert main_modulo.main(["--origem", str(csv_anp)]) == 1


def test_main_sem_origem_e_sem_pagina_retorna_um(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("ANP_PAGINA_URL", raising=False)
    monkeypatch.setattr("main.load_dotenv", lambda *a, **k: None)

    assert main_modulo.main([]) == 1


def test_main_arquivo_inexistente_retorna_um(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    assert main_modulo.main(["--origem", str(tmp_path / "nao_existe.csv")]) == 1


def test_main_cria_arquivo_de_log(csv_anp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    main_modulo.main(["--origem", str(csv_anp)])

    assert (tmp_path / "logs" / "etl.log").exists()
