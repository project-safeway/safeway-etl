import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transform import apenas_digitos, converter_preco, transformar


# ---------- Helpers ----------

def linha(**sobrescrever) -> dict:
    """Uma linha válida no formato bruto da ANP; sobrescreva o que quiser testar."""
    base = {
        "Regiao - Sigla": "SE",
        "Estado - Sigla": "SP",
        "Municipio": "  sao paulo ",
        "Revenda": "Posto Exemplo Ltda",
        "CNPJ da Revenda": "11.111.111/0001-11",
        "Bairro": "Centro",
        "Cep": "01000-000",
        "Produto": "gasolina",
        "Data da Coleta": "12/09/2026",
        "Valor de Venda": "5,79",
        "Unidade de Medida": "R$ / litro",
        "Bandeira": "Branca",
    }
    base.update(sobrescrever)
    return base


def df_bruto(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


# ---------- apenas_digitos ----------

def test_apenas_digitos_remove_pontuacao_do_cnpj():
    assert apenas_digitos("11.111.111/0001-11", 14) == "11111111000111"


def test_apenas_digitos_completa_cep_com_zeros_a_esquerda():
    assert apenas_digitos("1000000", 8) == "01000000"


def test_apenas_digitos_retorna_none_para_vazio_ou_nulo():
    assert apenas_digitos(None, 14) is None
    assert apenas_digitos("sem numeros", 14) is None


def test_apenas_digitos_retorna_none_quando_excede_tamanho():
    assert apenas_digitos("123456789012345", 14) is None


# ---------- converter_preco ----------

def test_converter_preco_aceita_virgula_e_ponto():
    resultado = converter_preco(pd.Series(["5,79", "6.05", " 5,99 "]))
    assert resultado.tolist() == [5.79, 6.05, 5.99]


def test_converter_preco_invalido_vira_nan():
    resultado = converter_preco(pd.Series(["abc", ""]))
    assert resultado.isna().all()


def test_converter_preco_mantem_numericos():
    resultado = converter_preco(pd.Series([5.79, 6.0]))
    assert resultado.tolist() == [5.79, 6.0]


# ---------- transformar ----------

def test_transformar_renomeia_colunas_e_padroniza_textos():
    resultado = transformar(df_bruto(linha()))

    assert "preco_venda" in resultado.columns
    assert "Valor de Venda" not in resultado.columns
    assert resultado.loc[0, "municipio"] == "SAO PAULO"
    assert resultado.loc[0, "produto"] == "GASOLINA"


def test_transformar_converte_tipos():
    resultado = transformar(df_bruto(linha()))

    assert resultado.loc[0, "preco_venda"] == pytest.approx(5.79)
    assert resultado.loc[0, "data_coleta"] == pd.Timestamp("2026-09-12")
    assert resultado.loc[0, "cnpj"] == "11111111000111"
    assert resultado.loc[0, "cep"] == "01000000"


def test_transformar_filtra_apenas_produtos_de_interesse():
    df = df_bruto(
        linha(),
        linha(Produto="ETANOL", **{"CNPJ da Revenda": "22.222.222/0001-22"}),
        linha(Produto="DIESEL S10", **{"CNPJ da Revenda": "33.333.333/0001-33"}),
    )
    resultado = transformar(df)

    assert resultado["produto"].tolist() == ["GASOLINA"]


def test_transformar_aceita_lista_de_produtos_customizada():
    df = df_bruto(linha(), linha(Produto="ETANOL"))
    resultado = transformar(df, produtos=["etanol"])

    assert resultado["produto"].tolist() == ["ETANOL"]


def test_transformar_descarta_preco_invalido_ou_nao_positivo():
    df = df_bruto(
        linha(**{"Valor de Venda": "abc"}),
        linha(**{"Valor de Venda": "0", "CNPJ da Revenda": "22.222.222/0001-22"}),
        linha(**{"Valor de Venda": "5,50", "CNPJ da Revenda": "33.333.333/0001-33"}),
    )
    resultado = transformar(df)

    assert len(resultado) == 1
    assert resultado.loc[0, "preco_venda"] == pytest.approx(5.50)


def test_transformar_descarta_cnpj_ou_data_invalidos():
    df = df_bruto(
        linha(**{"CNPJ da Revenda": None}),
        linha(**{"Data da Coleta": "data-quebrada", "CNPJ da Revenda": "22.222.222/0001-22"}),
    )
    resultado = transformar(df)

    assert resultado.empty


def test_transformar_remove_duplicados_mantendo_a_ultima():
    df = df_bruto(
        linha(**{"Valor de Venda": "5,79"}),
        linha(**{"Valor de Venda": "5,89"}),  # mesmo posto, produto e data
    )
    resultado = transformar(df)

    assert len(resultado) == 1
    assert resultado.loc[0, "preco_venda"] == pytest.approx(5.89)


def test_transformar_nao_altera_o_dataframe_original():
    df = df_bruto(linha())
    copia = df.copy()
    transformar(df)

    pd.testing.assert_frame_equal(df, copia)