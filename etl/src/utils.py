from __future__ import annotations

import unicodedata

import pandas as pd


def normalizar_texto(valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    sem_acento = unicodedata.normalize("NFKD", str(valor))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.split()).upper()