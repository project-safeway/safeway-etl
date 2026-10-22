# safeway-etl
"""
Ponto de entrada do ETL. Exemplos:

    # Rodar com um arquivo já baixado (ou uma URL direta):
    python main.py --origem data/raw/arquivo.xlsx

    # Modo agendado: acha sozinho a planilha mais recente na página da ANP
    # (usa ANP_PAGINA_URL do .env, ou --pagina):
    python main.py

Código de saída: 0 = sucesso, 1 = falha (útil para o agendador do Windows).
"""