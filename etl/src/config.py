"""
config.py

Constantes de negócio do ETL.
"""

# Região Metropolitana de São Paulo (39 municípios), que inclui o Grande ABC
# (Santo André, São Bernardo do Campo, São Caetano do Sul, Diadema, Mauá,
# Ribeirão Pires e Rio Grande da Serra).
# Obs.: a pesquisa da ANP não cobre todos os municípios; os que não tiverem
# postos na planilha simplesmente não aparecem.
MUNICIPIOS_GRANDE_SP = [
    "Arujá", "Barueri", "Biritiba-Mirim", "Caieiras", "Cajamar", "Carapicuíba",
    "Cotia", "Diadema", "Embu das Artes", "Embu-Guaçu", "Ferraz de Vasconcelos",
    "Francisco Morato", "Franco da Rocha", "Guararema", "Guarulhos",
    "Itapecerica da Serra", "Itapevi", "Itaquaquecetuba", "Jandira", "Juquitiba",
    "Mairiporã", "Mauá", "Mogi das Cruzes", "Osasco", "Pirapora do Bom Jesus",
    "Poá", "Ribeirão Pires", "Rio Grande da Serra", "Salesópolis", "Santa Isabel",
    "Santana de Parnaíba", "Santo André", "São Bernardo do Campo",
    "São Caetano do Sul", "São Lourenço da Serra", "São Paulo", "Suzano",
    "Taboão da Serra", "Vargem Grande Paulista",
]

ESTADO_PADRAO = "SP"

# Texto do link da planilha por posto na página da ANP
TEXTO_LINK_POSTOS = "Preços por posto revendedor"

# Nome do estado (sem acento, maiúsculas) -> sigla. Usado porque a planilha
# da ANP pode trazer o estado por extenso ou já como sigla.
ESTADOS_SIGLAS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARA": "CE", "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO",
    "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
