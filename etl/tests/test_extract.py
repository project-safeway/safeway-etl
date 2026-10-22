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

# Permite rodar os testes sem precisar instalar o pacote (ajusta o path pra achar src/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from extract import (
    baixar_arquivo,
    encontrar_link_planilha,
    obter_url_planilha_da_semana,
    ler_planilha_anp,
    validar_colunas,
    extrair,
    COLUNAS_ESPERADAS,
)


# ---------- Fixtures ----------

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


# ---------- Testes: ler_planilha_anp ----------

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


# ---------- Testes: validar_colunas ----------

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


# ---------- Testes: baixar_arquivo (com mock, sem chamar a internet) ----------

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


# ---------- Testes: extrair (fluxo completo) ----------

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

    # Garante que o download caia em uma pasta temporária, não em ./data/raw real
    monkeypatch.chdir(tmp_path)

    df = extrair("https://exemplo.gov.br/precos.csv")

    assert len(df) == 1
    assert (tmp_path / "data" / "raw").exists()


# ---------- Testes: descoberta do link da semana ----------

HTML_PAGINA_ANP = """
<html><body>
  <h3>06/09/2026 a 12/09/2026</h3>
  <ul>
    <li><a href="/arquivos/precos-medios-semanais.xlsx">Preços médios semanais: Brasil, regiões, estados e municípios</a></li>
    <li><a href="/arquivos/precos-postos-semana-37.xlsx">Preços por posto revendedor (combustíveis automotivos e GLP P13)</a></li>
  </ul>
  <h3>30/08/2026 a 05/09/2026</h3>
  <ul>
    <li><a href="/arquivos/precos-postos-semana-36.xlsx">Preços por posto revendedor (combustíveis automotivos e GLP P13)</a></li>
  </ul>
</body></html>
"""


def test_encontrar_link_planilha_devolve_o_primeiro_link_de_postos():
    url = encontrar_link_planilha(HTML_PAGINA_ANP, "https://www.gov.br/anp/pagina")

    # Primeiro = semana mais recente; e o link de "médias" não deve ser escolhido
    assert url == "https://www.gov.br/arquivos/precos-postos-semana-37.xlsx"


def test_encontrar_link_planilha_ignora_acento_e_caixa():
    html = '<a href="https://x.gov.br/a.csv">PRECOS POR POSTO REVENDEDOR</a>'

    assert encontrar_link_planilha(html, "https://x.gov.br") == "https://x.gov.br/a.csv"


def test_encontrar_link_planilha_levanta_erro_quando_nao_acha():
    with pytest.raises(LookupError):
        encontrar_link_planilha("<a href='/x'>Outra coisa</a>", "https://x.gov.br")


@patch("extract.requests.get")
def test_obter_url_planilha_da_semana_le_a_pagina_e_acha_o_link(mock_get):
    resposta_mock = Mock()
    resposta_mock.text = HTML_PAGINA_ANP
    resposta_mock.raise_for_status = Mock()
    mock_get.return_value = resposta_mock

    url = obter_url_planilha_da_semana("https://www.gov.br/anp/pagina")

    assert url.endswith("precos-postos-semana-37.xlsx")
    mock_get.assert_called_once()


@patch("extract.requests.get")
def test_baixar_arquivo_detecta_xlsx_pelo_conteudo(mock_get, tmp_path):
    resposta_mock = Mock()
    resposta_mock.content = b"PK\x03\x04conteudo-zip-fake"  # assinatura de arquivo .xlsx/.zip
    resposta_mock.raise_for_status = Mock()
    mock_get.return_value = resposta_mock

    # URL sem extensão: o formato precisa vir do conteúdo
    caminho = baixar_arquivo("https://exemplo.gov.br/download/12345", pasta_destino=tmp_path)

    assert caminho.suffix == ".xlsx"