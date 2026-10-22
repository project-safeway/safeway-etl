"""
utils.py

Funções auxiliares compartilhadas entre as etapas do ETL.
"""

from __future__ import annotations

import unicodedata

import pandas as pd

from config import ESTADOS_SIGLAS


def normalizar_texto(valor) -> str | None:
    """
    Remove acentos, espaços extras e padroniza em maiúsculas, para comparar
    textos sem depender de como a fonte escreveu ("São Paulo" == "SAO PAULO").
    Devolve None para valores nulos.
    """
    if valor is None or pd.isna(valor):
        return None
    sem_acento = unicodedata.normalize("NFKD", str(valor))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.split()).upper()


def para_sigla_uf(valor) -> str | None:
    """
    Converte "São Paulo", "SAO PAULO" ou "sp" para a sigla "SP".
    Devolve None se for nulo ou não reconhecido.
    """
    normalizado = normalizar_texto(valor)
    if not normalizado:
        return None
    if len(normalizado) == 2:
        return normalizado
    return ESTADOS_SIGLAS.get(normalizado)
