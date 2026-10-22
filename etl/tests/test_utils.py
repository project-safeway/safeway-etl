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