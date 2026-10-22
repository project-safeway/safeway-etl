"""
main.py

Ponto de entrada do ETL. Exemplos:

    # Rodar com um arquivo já baixado (ou uma URL direta):
    python main.py --origem data/raw/arquivo.xlsx

    # Modo agendado: acha sozinho a planilha mais recente na página da ANP
    # (usa ANP_PAGINA_URL do .env, ou --pagina):
    python main.py

Código de saída: 0 = sucesso, 1 = falha (útil para o agendador do Windows).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dotenv import load_dotenv  # noqa: E402

from db import criar_tabelas, get_engine  # noqa: E402
from pipeline import executar_pipeline, executar_semanal  # noqa: E402

logger = logging.getLogger("main")


def configurar_logging(pasta_logs: str | Path = "logs") -> None:
    """Loga no console e em logs/etl.log (rotaciona em 1 MB, guarda 5 arquivos)."""
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    if any(isinstance(h, RotatingFileHandler) for h in raiz.handlers):
        return  # já configurado
    pasta = Path(pasta_logs)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = RotatingFileHandler(
        pasta / "etl.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    arquivo.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    raiz.addHandler(arquivo)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configurar_logging()

    parser = argparse.ArgumentParser(description="ETL de preços de combustíveis da ANP")
    parser.add_argument("--origem", help="URL direta ou caminho local da planilha")
    parser.add_argument("--pagina", help="URL da página da ANP (padrão: ANP_PAGINA_URL do .env)")
    args = parser.parse_args(argv)

    try:
        engine = get_engine()
        criar_tabelas(engine)

        if args.origem:
            resumo = executar_pipeline(args.origem, engine)
        else:
            pagina = args.pagina or os.getenv("ANP_PAGINA_URL")
            if not pagina:
                raise ValueError(
                    "Informe --origem, --pagina ou defina ANP_PAGINA_URL no .env."
                )
            resumo = executar_semanal(pagina, engine)

        logger.info("ETL finalizado com sucesso: %s", resumo)
        return 0
    except Exception:
        logger.exception("ETL falhou")
        return 1


if __name__ == "__main__":
    sys.exit(main())
