"""
Este módulo cobre dois cenários:
1) Você já baixou o arquivo manualmente -> use `ler_planilha_anp()`.
2) Você tem a URL direta do arquivo daquela semana -> use `extrair()`,
   que baixa e já retorna o DataFrame validado.

IMPORTANTE: confira as colunas do arquivo que você baixar contra
`COLUNAS_ESPERADAS` abaixo — a ANP já mudou o layout dessas planilhas
mais de uma vez ao longo dos anos, então vale um `df.columns.tolist()`
rápido antes de rodar em produção.
"""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from config import TEXTO_LINK_POSTOS
from utils import normalizar_texto

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

COLUNAS_ESPERADAS = [
    "Regiao - Sigla",
    "Estado - Sigla",
    "Municipio",
    "Revenda",
    "CNPJ da Revenda",
    "Bairro",
    "Cep",
    "Produto",
    "Data da Coleta",
    "Valor de Venda",
    "Unidade de Medida",
    "Bandeira",
]

TENTATIVAS_LEITURA = [
    {"sep": ";", "encoding": "latin1"},
    {"sep": ";", "encoding": "utf-8"},
    {"sep": ",", "encoding": "utf-8"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; safeway-etl/1.0)"}


def encontrar_link_planilha(html: str, base_url: str, texto_link: str = TEXTO_LINK_POSTOS) -> str:
    """
    Procura na página da ANP o primeiro link cujo texto contém `texto_link`
    (comparação sem acento e sem diferenciar maiúsculas) e devolve a URL
    absoluta. A página lista a semana mais recente primeiro, então o primeiro
    link encontrado é o da última semana.

    Levanta LookupError se nenhum link for encontrado (ex.: a ANP mudou o texto).
    """
    alvo = normalizar_texto(texto_link)
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all("a", href=True):
        if alvo in (normalizar_texto(tag.get_text(" ", strip=True)) or ""):
            return urljoin(base_url, tag["href"])

    raise LookupError(f"Nenhum link com o texto '{texto_link}' encontrado em {base_url}")


def obter_url_planilha_da_semana(pagina_url: str, texto_link: str = TEXTO_LINK_POSTOS) -> str:
    """Abre a página da ANP e devolve a URL da planilha mais recente."""
    logger.info("Procurando a planilha mais recente em: %s", pagina_url)
    resposta = requests.get(pagina_url, headers=HEADERS, timeout=30)
    resposta.raise_for_status()
    url = encontrar_link_planilha(resposta.text, pagina_url, texto_link)
    logger.info("Planilha encontrada: %s", url)
    return url


def baixar_arquivo(url: str, pasta_destino: str | Path = "data/raw") -> Path:
    """
    Baixa o arquivo da ANP a partir da URL e salva em `pasta_destino`
    com timestamp no nome (evita sobrescrever downloads anteriores).

    Levanta requests.HTTPError se o download falhar.
    """
    pasta_destino = Path(pasta_destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)

    logger.info("Baixando arquivo da ANP: %s", url)
    resposta = requests.get(url, headers=HEADERS, timeout=60)
    resposta.raise_for_status()

    # XLSX é um .zip e começa com "PK"; a URL nem sempre tem extensão
    extensao = ".xlsx" if resposta.content[:2] == b"PK" else ".csv"
    nome_arquivo = f"anp_precos_{datetime.now():%Y%m%d_%H%M%S}{extensao}"
    caminho_destino = pasta_destino / nome_arquivo

    caminho_destino.write_bytes(resposta.content)
    logger.info("Arquivo salvo em: %s", caminho_destino)
    return caminho_destino


def ler_planilha_anp(caminho: str | Path) -> pd.DataFrame:
    """
    Lê o arquivo (CSV ou XLSX) baixado da ANP e retorna um DataFrame.
    Tenta algumas combinações de separador/encoding antes de desistir,
    já que a ANP não é 100% consistente entre publicações.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    if caminho.suffix.lower() == ".xlsx":
        logger.info("Lendo XLSX: %s", caminho)
        df = pd.read_excel(caminho)
        return df

    ultimo_erro: Exception | None = None
    for tentativa in TENTATIVAS_LEITURA:
        try:
            logger.info("Tentando ler CSV com %s", tentativa)
            df = pd.read_csv(caminho, **tentativa)
            if df.shape[1] > 1:  # separador errado geralmente gera 1 coluna só
                return df
        except (UnicodeDecodeError, pd.errors.ParserError) as erro:
            ultimo_erro = erro
            continue

    raise ValueError(
        f"Não foi possível ler o CSV com nenhuma combinação testada. "
        f"Último erro: {ultimo_erro}"
    )


def validar_colunas(df: pd.DataFrame, colunas_esperadas: list[str] = COLUNAS_ESPERADAS) -> None:
    """
    Garante que as colunas mínimas necessárias para o pipeline existem.
    Levanta ValueError listando o que está faltando, para falhar cedo
    e não deixar lixo seguir para a transformação.
    """
    colunas_faltando = [c for c in colunas_esperadas if c not in df.columns]
    if colunas_faltando:
        raise ValueError(
            f"Colunas ausentes na planilha da ANP: {colunas_faltando}. "
            f"Colunas encontradas: {df.columns.tolist()}"
        )
    logger.info("Validação de colunas OK.")


def extrair(origem: str, colunas_esperadas: list[str] = COLUNAS_ESPERADAS) -> pd.DataFrame:
    """
    Ponto de entrada da extração.

    `origem` pode ser:
      - uma URL (http/https) -> baixa e depois lê
      - um caminho local já baixado -> só lê

    Retorna o DataFrame já validado.
    """
    if origem.startswith("http://") or origem.startswith("https://"):
        caminho = baixar_arquivo(origem)
    else:
        caminho = Path(origem)

    df = ler_planilha_anp(caminho)
    validar_colunas(df, colunas_esperadas)
    logger.info("Extração concluída: %d linhas, %d colunas.", *df.shape)
    return df


if __name__ == "__main__":
    # Exemplo de uso manual (ajuste o caminho para o arquivo baixado):
    # df = extrair("data/raw/precos-postos-01_a_07-09-2026.csv")
    # print(df.head())
    pass