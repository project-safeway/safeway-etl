"""Testes de utils.py. Rodar com: python -m pytest tests/test_utils.py -v"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from utils import normalizar_texto


def test_normalizar_texto_remove_acentos_e_padroniza_caixa():
    assert normalizar_texto("  São   Bernardo do Campo ") == "SAO BERNARDO DO CAMPO"


def test_normalizar_texto_nulos_viram_none():
    assert normalizar_texto(None) is None
    assert normalizar_texto(pd.NA) is None
    assert normalizar_texto(float("nan")) is None


def test_para_sigla_uf_aceita_nome_por_extenso_sigla_e_acentos():
    from utils import para_sigla_uf

    assert para_sigla_uf("SAO PAULO") == "SP"
    assert para_sigla_uf("São Paulo") == "SP"
    assert para_sigla_uf("sp") == "SP"
    assert para_sigla_uf("MATO GROSSO DO SUL") == "MS"
    assert para_sigla_uf("CEARA") == "CE"


def test_para_sigla_uf_desconhecido_ou_nulo_vira_none():
    from utils import para_sigla_uf

    assert para_sigla_uf("ESTADO INEXISTENTE") is None
    assert para_sigla_uf(None) is None
    assert para_sigla_uf(pd.NA) is None
