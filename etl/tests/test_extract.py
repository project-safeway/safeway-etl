"""
Testes da etapa de extração (extract.py).

Rodar com:
    pytest tests/test_extract.py -v
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from extract import (
    baixar_arquivo,
    ler_planilha_anp,
    validar_colunas,
    extrair,
    COLUNAS_ESPERADAS,
)

CSV_VALIDO = (
    "Regiao - Sigla;Estado - Sigla;Municipio;Revenda;CNPJ da Revenda;Bairro;"
    "Cep;Produto;Data da Coleta;Valor de Venda;Unidade de Medida;Bandeira\n"
    "SE;SP;SAO PAULO;POSTO EXEMPLO LTDA;11.111.111/0001-11;CENTRO;"
    "01000-000;GASOLINA;12/09/2026;5,79;R$ / litro;BRANCA\n"
)


@pytest.fixture
def csv_valido(tmp_path) -> Path:
    caminho = tmp_path / "anp_precos_teste.csv"
    caminho.write_text(CSV_VALIDO, encoding="latin1")
    return caminho


@pytest.fixture
def csv_colunas_faltando(tmp_path) -> Path:
    conteudo = "Estado - Sigla;Municipio;Produto\nSP;SAO PAULO;GASOLINA\n"
    caminho = tmp_path / "anp_incompleto.csv"
    caminho.write_text(conteudo, encoding="latin1")
    return caminho


def test_ler_planilha_anp_le_csv_valido(csv_valido):
    df = ler_planilha_anp(csv_valido)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert "Produto" in df.columns
    assert df.iloc[0]["Produto"] == "GASOLINA"


def test_ler_planilha_anp_arquivo_inexistente_levanta_erro(tmp_path):
    caminho_falso = tmp_path / "nao_existe.csv"

    with pytest.raises(FileNotFoundError):
        ler_planilha_anp(caminho_falso)


def test_ler_planilha_anp_csv_ilegivel_levanta_value_error(tmp_path):
    # Bytes que não são um CSV válido em nenhuma das combinações tentadas
    caminho = tmp_path / "lixo.csv"
    caminho.write_bytes(b"\xff\xfe\x00\x01\x02lixo binario")

    with pytest.raises(ValueError):
        ler_planilha_anp(caminho)


def test_validar_colunas_aceita_dataframe_completo(csv_valido):
    df = ler_planilha_anp(csv_valido)
    # Não deve levantar exceção
    validar_colunas(df)


def test_validar_colunas_rejeita_dataframe_incompleto(csv_colunas_faltando):
    df = ler_planilha_anp(csv_colunas_faltando)

    with pytest.raises(ValueError) as erro:
        validar_colunas(df)

    mensagem = str(erro.value)
    assert "Colunas ausentes" in mensagem
    # Confirma que aponta pelo menos uma coluna que realmente falta
    assert "Revenda" in mensagem


@patch("extract.requests.get")
def test_baixar_arquivo_salva_conteudo_da_resposta(mock_get, tmp_path):
    conteudo_fake = CSV_VALIDO.encode("latin1")
    resposta_mock = Mock()
    resposta_mock.content = conteudo_fake
    resposta_mock.raise_for_status = Mock()
    mock_get.return_value = resposta_mock

    caminho = baixar_arquivo("https://exemplo.gov.br/precos.csv", pasta_destino=tmp_path)

    assert caminho.exists()
    assert caminho.read_bytes() == conteudo_fake
    mock_get.assert_called_once()


@patch("extract.requests.get")
def test_baixar_arquivo_propaga_erro_http(mock_get, tmp_path):
    resposta_mock = Mock()
    resposta_mock.raise_for_status.side_effect = Exception("Erro HTTP 404")
    mock_get.return_value = resposta_mock

    with pytest.raises(Exception):
        baixar_arquivo("https://exemplo.gov.br/nao-existe.csv", pasta_destino=tmp_path)



def test_extrair_com_arquivo_local(csv_valido):
    df = extrair(str(csv_valido))

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    for coluna in COLUNAS_ESPERADAS:
        assert coluna in df.columns


@patch("extract.requests.get")
def test_extrair_com_url_baixa_e_le(mock_get, tmp_path, monkeypatch):
    conteudo_fake = CSV_VALIDO.encode("latin1")
    resposta_mock = Mock()
    resposta_mock.content = conteudo_fake
    resposta_mock.raise_for_status = Mock()
    mock_get.return_value = resposta_mock

    monkeypatch.chdir(tmp_path)

    df = extrair("https://exemplo.gov.br/precos.csv")

    assert len(df) == 1
    assert (tmp_path / "data" / "raw").exists()