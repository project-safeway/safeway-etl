"""
Testes da etapa de transformação (transform.py).

Rodar com:
    python -m pytest tests/test_transform.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from extract import COLUNAS_ESPERADAS
from transform import (
    RENOMEAR_COLUNAS,
    apenas_digitos,
    converter_preco,
    formatar_numero,
    montar_endereco,
    transformar,
)


# ---------- Helpers ----------

def linha(**sobrescrever) -> dict:
    """Uma linha válida no formato bruto da ANP; sobrescreva o que quiser testar."""
    base = {
        "CNPJ": "11.111.111/0001-11",
        "RAZÃO": "Posto Exemplo Ltda",
        "FANTASIA": "Posto Exemplo",
        "ENDEREÇO": "Av Paulista",
        "NÚMERO": 1000,
        "COMPLEMENTO": "Loja 1",
        "Bairro": "Centro",
        "Cep": "01000-000",
        "Municipio": "  sao paulo ",
        "ESTADO": "SAO PAULO",
        "Bandeira": "Branca",
        "Produto": "gasolina comum",
        "Unidade de Medida": "R$ / litro",
        "PREÇO DE REVENDA": "5,79",
        "Data da Coleta": "12/09/2026",
    }
    base.update(sobrescrever)
    return base


def df_bruto(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


def outro_posto(n: int, **extra) -> dict:
    """Linha de um posto diferente (CNPJ distinto) para evitar deduplicação."""
    return linha(CNPJ=f"{n}{n}.222.222/0001-{n}{n}", **extra)


# ---------- consistência com o extract ----------

def test_renomear_colunas_cobre_exatamente_as_colunas_esperadas_do_extract():
    assert set(RENOMEAR_COLUNAS) == set(COLUNAS_ESPERADAS)


# ---------- apenas_digitos ----------

def test_apenas_digitos_remove_pontuacao_do_cnpj():
    assert apenas_digitos("11.111.111/0001-11", 14) == "11111111000111"


def test_apenas_digitos_completa_cep_com_zeros_a_esquerda():
    assert apenas_digitos("1000000", 8) == "01000000"


def test_apenas_digitos_aceita_numero_do_excel_como_float():
    # CNPJ numérico no Excel pode chegar como float; o ".0" não pode virar dígito
    assert apenas_digitos(11111111000111.0, 14) == "11111111000111"
    assert apenas_digitos(1000000.0, 8) == "01000000"


def test_apenas_digitos_completa_cnpj_numerico_que_perdeu_zero_a_esquerda():
    assert apenas_digitos(1234567000189, 14) == "01234567000189"


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


# ---------- endereço ----------

def test_formatar_numero_remove_decimal_e_mantem_sn():
    assert formatar_numero(1852.0) == "1852"
    assert formatar_numero(3220) == "3220"
    assert formatar_numero("S/N") == "S/N"
    assert formatar_numero(None) is None


def test_montar_endereco_completo():
    assert montar_endereco("AV PAULISTA", 1000, "LOJA 1") == "AV PAULISTA, 1000 - LOJA 1"


def test_montar_endereco_sem_complemento_ou_numero():
    assert montar_endereco("RUA A", "S/N", None) == "RUA A, S/N"
    assert montar_endereco("RUA A", None, None) == "RUA A"
    assert montar_endereco(None, None, None) is None


# ---------- transformar ----------

def test_transformar_devolve_apenas_colunas_finais_em_snake_case():
    resultado = transformar(df_bruto(linha()))

    assert resultado.columns.tolist() == [
        "cnpj", "revenda", "endereco", "bairro", "cep", "municipio", "estado",
        "bandeira", "produto", "unidade_medida", "preco_venda", "data_coleta",
    ]


def test_transformar_padroniza_textos_e_converte_tipos():
    resultado = transformar(df_bruto(linha()))

    assert resultado.loc[0, "municipio"] == "SAO PAULO"
    assert resultado.loc[0, "produto"] == "GASOLINA COMUM"
    assert resultado.loc[0, "preco_venda"] == pytest.approx(5.79)
    assert resultado.loc[0, "data_coleta"] == pd.Timestamp("2026-09-12")
    assert resultado.loc[0, "cnpj"] == "11111111000111"
    assert resultado.loc[0, "cep"] == "01000000"


def test_transformar_converte_estado_por_extenso_em_sigla():
    df = df_bruto(
        linha(ESTADO="SAO PAULO"),
        outro_posto(2, ESTADO="sp"),
        outro_posto(3, ESTADO="São Paulo"),
    )

    assert transformar(df)["estado"].tolist() == ["SP", "SP", "SP"]


def test_transformar_estado_desconhecido_vira_nulo_e_nao_quebra():
    resultado = transformar(df_bruto(linha(ESTADO="ESTADO INEXISTENTE")))

    assert resultado.loc[0, "estado"] is None


def test_transformar_usa_fantasia_como_nome_do_posto():
    resultado = transformar(df_bruto(linha()))

    assert resultado.loc[0, "revenda"] == "POSTO EXEMPLO"


def test_transformar_usa_razao_social_quando_fantasia_vazia():
    df = df_bruto(linha(FANTASIA=None), outro_posto(2, FANTASIA="  "))

    assert transformar(df)["revenda"].tolist() == ["POSTO EXEMPLO LTDA"] * 2


def test_transformar_monta_endereco():
    resultado = transformar(df_bruto(linha()))

    assert resultado.loc[0, "endereco"] == "AV PAULISTA, 1000 - LOJA 1"


def test_transformar_aceita_cnpj_e_cep_numericos_do_excel():
    resultado = transformar(df_bruto(linha(CNPJ=11111111000111.0, Cep=1000000.0)))

    assert resultado.loc[0, "cnpj"] == "11111111000111"
    assert resultado.loc[0, "cep"] == "01000000"


def test_transformar_filtra_apenas_produtos_de_interesse():
    df = df_bruto(
        linha(),
        outro_posto(2, Produto="ETANOL"),
        outro_posto(3, Produto="DIESEL S10"),
        outro_posto(4, Produto="GLP"),
    )
    resultado = transformar(df)

    assert resultado["produto"].tolist() == ["GASOLINA COMUM"]


def test_transformar_aceita_lista_de_produtos_customizada():
    df = df_bruto(linha(), outro_posto(2, Produto="DIESEL S10"))
    resultado = transformar(df, produtos=["diesel s10"])

    assert resultado["produto"].tolist() == ["DIESEL S10"]


def test_transformar_descarta_preco_invalido_ou_nao_positivo():
    df = df_bruto(
        linha(**{"PREÇO DE REVENDA": "abc"}),
        outro_posto(2, **{"PREÇO DE REVENDA": "0"}),
        outro_posto(3, **{"PREÇO DE REVENDA": "5,50"}),
    )
    resultado = transformar(df)

    assert len(resultado) == 1
    assert resultado.loc[0, "preco_venda"] == pytest.approx(5.50)


def test_transformar_descarta_cnpj_ou_data_invalidos():
    df = df_bruto(
        linha(CNPJ=None),
        outro_posto(2, **{"Data da Coleta": "data-quebrada"}),
    )

    assert transformar(df).empty


def test_transformar_remove_duplicados_mantendo_a_ultima():
    df = df_bruto(
        linha(**{"PREÇO DE REVENDA": "5,79"}),
        linha(**{"PREÇO DE REVENDA": "5,89"}),  # mesmo posto, produto e data
    )
    resultado = transformar(df)

    assert len(resultado) == 1
    assert resultado.loc[0, "preco_venda"] == pytest.approx(5.89)


def test_transformar_nao_altera_o_dataframe_original():
    df = df_bruto(linha())
    copia = df.copy()
    transformar(df)

    pd.testing.assert_frame_equal(df, copia)


# ---------- filtro geográfico ----------

def test_transformar_filtra_por_municipios_ignorando_acento_e_caixa():
    df = df_bruto(
        linha(Municipio="SÃO PAULO"),
        outro_posto(2, Municipio="Santo Andre"),
        outro_posto(3, Municipio="CAMPINAS"),
    )
    resultado = transformar(df, municipios=["São Paulo", "Santo André"])

    assert sorted(resultado["municipio"].tolist()) == ["SANTO ANDRE", "SÃO PAULO"]


def test_transformar_filtra_por_estado_aceitando_sigla_ou_nome():
    df = df_bruto(
        linha(ESTADO="SAO PAULO"),
        outro_posto(2, ESTADO="RIO DE JANEIRO"),
    )

    assert transformar(df, estado="SP")["estado"].tolist() == ["SP"]
    assert transformar(df, estado="são paulo")["estado"].tolist() == ["SP"]


def test_transformar_municipio_homonimo_de_outro_estado_e_excluido():
    df = df_bruto(
        linha(Municipio="SANTA ISABEL", ESTADO="SAO PAULO"),
        outro_posto(2, Municipio="SANTA ISABEL", ESTADO="PARA"),
    )
    resultado = transformar(df, municipios=["Santa Isabel"], estado="SP")

    assert resultado["estado"].tolist() == ["SP"]


def test_transformar_sem_filtro_geografico_mantem_todos():
    df = df_bruto(linha(Municipio="SAO PAULO"), outro_posto(2, Municipio="CAMPINAS"))

    assert len(transformar(df)) == 2
