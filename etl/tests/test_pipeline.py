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
    "Regiao - Sigla;Estado - Sigla;Municipio;Revenda;CNPJ da Revenda;Bairro;"
    "Cep;Produto;Data da Coleta;Valor de Venda;Unidade de Medida;Bandeira\n"
)

CSV = CABECALHO + (
    # Dentro do escopo (acento + caixa diferentes do config)
    "SE;SP;SÃO PAULO;POSTO A;11.111.111/0001-11;CENTRO;01000-000;GASOLINA;12/09/2026;5,79;R$ / litro;BRANCA\n"
    "SE;SP;SANTO ANDRE;POSTO B;22.222.222/0001-22;CENTRO;09000-000;GASOLINA ADITIVADA;12/09/2026;6,09;R$ / litro;SHELL\n"
    # Fora do escopo: município e produto
    "SE;SP;CAMPINAS;POSTO C;33.333.333/0001-33;CENTRO;13000-000;GASOLINA;12/09/2026;5,59;R$ / litro;BRANCA\n"
    "SE;SP;SAO PAULO;POSTO D;44.444.444/0001-44;CENTRO;01000-000;ETANOL;12/09/2026;4,19;R$ / litro;BRANCA\n"
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
        "linhas_extraidas": 4,
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