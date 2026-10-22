"""
extract.py

Etapa de EXTRAÇÃO do ETL de preços de combustíveis (ANP).

A ANP não disponibiliza uma API REST: os dados são publicados semanalmente
como planilha (CSV ou XLSX) em:
https://www.gov.br/anp/pt-br/.../levantamento-de-precos-de-combustiveis

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
import re
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

# Colunas do arquivo "Preços por posto revendedor" da ANP (conferidas com o
# arquivo real da semana 11/10 a 17/10/2026). Ajuste aqui se o layout mudar.
COLUNAS_ESPERADAS = [
    "CNPJ",
    "RAZÃO",
    "FANTASIA",
    "ENDEREÇO",
    "NÚMERO",
    "COMPLEMENTO",
    "Bairro",
    "Cep",
    "Municipio",
    "ESTADO",
    "Bandeira",
    "Produto",
    "Unidade de Medida",
    "PREÇO DE REVENDA",
    "Data da Coleta",
]

# A ANP costuma exportar com ';' como separador e encoding latin1.
# Deixamos uma lista de tentativas caso o arquivo baixado varie.
TENTATIVAS_LEITURA = [
    {"sep": ";", "encoding": "latin1"},
    {"sep": ";", "encoding": "utf-8"},
    {"sep": ",", "encoding": "utf-8"},
]

# Alguns sites do governo bloqueiam o User-Agent padrão do requests
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


def normalizar_coluna(nome) -> str:
    """
    Forma "comparável" de um nome de coluna: sem acento, maiúsculas e sem
    pontuação. Ex.: 'Região - Sigla' e 'REGIAO SIGLA' viram 'REGIAO SIGLA'.
    """
    texto = normalizar_texto(nome) or ""
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


def padronizar_colunas(df: pd.DataFrame, colunas_esperadas: list[str] = COLUNAS_ESPERADAS) -> pd.DataFrame:
    """
    Renomeia as colunas do DataFrame para os nomes canônicos de
    `colunas_esperadas` quando só diferem em acento, caixa ou pontuação.
    Colunas que não correspondem a nenhuma esperada ficam como estão.
    """
    canonicos = {normalizar_coluna(c): c for c in colunas_esperadas}
    renomear = {}
    for coluna in df.columns:
        canonico = canonicos.get(normalizar_coluna(coluna))
        if canonico and canonico != coluna:
            renomear[coluna] = canonico
    return df.rename(columns=renomear)


def localizar_cabecalho(caminho: str | Path, colunas_esperadas: list[str] = COLUNAS_ESPERADAS,
                        max_linhas: int = 30, minimo_colunas: int = 3) -> int:
    """
    Os XLSX da ANP trazem linhas de título (nome da agência, período etc.)
    acima da tabela. Procura nas primeiras `max_linhas` linhas a primeira que
    contém pelo menos `minimo_colunas` nomes de coluna esperados e devolve o
    índice dela (0 = primeira linha). Se não achar, devolve 0.
    """
    esperados = {normalizar_coluna(c) for c in colunas_esperadas}
    topo = pd.read_excel(caminho, header=None, nrows=max_linhas)

    for indice, linha in topo.iterrows():
        nomes = {normalizar_coluna(v) for v in linha if pd.notna(v)}
        if len(nomes & esperados) >= minimo_colunas:
            return int(indice)
    return 0


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
        linha_cabecalho = localizar_cabecalho(caminho)
        logger.info("Cabeçalho encontrado na linha %d do arquivo.", linha_cabecalho)
        df = pd.read_excel(caminho, header=linha_cabecalho)
        return padronizar_colunas(df)

    ultimo_erro: Exception | None = None
    for tentativa in TENTATIVAS_LEITURA:
        try:
            logger.info("Tentando ler CSV com %s", tentativa)
            df = pd.read_csv(caminho, **tentativa)
            if df.shape[1] > 1:  # separador errado geralmente gera 1 coluna só
                return padronizar_colunas(df)
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
