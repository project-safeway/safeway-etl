SafeWay ETL — Preços de Combustíveis da ANP
Pipeline de ETL (Extract, Transform, Load) desenvolvido em Python para coletar dados públicos de preços de combustíveis divulgados pela Agência Nacional do Petróleo, Gás Natural e Biocombustíveis (ANP), padronizar os registros e carregá-los em um banco de dados relacional.

Por padrão, o pipeline mantém dados de gasolina na Região Metropolitana de São Paulo, com estado SP e municípios definidos em src/config.py. Os filtros podem ser ajustados na chamada do pipeline.
Sumário
- Visão geral
- Fluxo do ETL
- Tecnologias
- Estrutura do projeto
- Configuração
- Instalação e execução
- Módulos e métodos
- Banco de dados
- Testes
- Logs e tratamento de erros
- Observações
Visão geral
O projeto automatiza o processamento da planilha “Preços por posto revendedor” publicada pela ANP. Ele pode receber um arquivo local, uma URL direta para o arquivo ou descobrir o link da publicação mais recente a partir da página da ANP.

O pipeline foi desenvolvido para lidar com variações comuns nos arquivos de origem, como CSV ou XLSX, diferenças de codificação e separador, cabeçalhos precedidos por linhas de título, acentuação e formatos de dados inconsistentes.
Fluxo do ETL
Página da ANP ou arquivo local
            |
            v
        EXTRAÇÃO
  Download, leitura e validação
            |
            v
      TRANSFORMAÇÃO
  Limpeza, conversão e filtros
            |
            v
          CARGA
  Inserção/atualização no banco
            |
            v
  Tabela precos_combustiveis
Ao final, o pipeline retorna um resumo com a quantidade de linhas extraídas, transformadas e processadas na carga.
Tecnologias
- Python — implementação do pipeline.
- pandas — leitura, manipulação e transformação dos dados.
- Requests — requisições HTTP para a página da ANP e download de arquivos.
- Beautiful Soup 4 — identificação do link da planilha na página HTML.
- SQLAlchemy — conexão, definição da tabela e operações no banco.
- MySQL + PyMySQL — banco de dados previsto para uso principal.
- SQLite — suporte usado nos testes automatizados.
- python-dotenv — carregamento de variáveis de ambiente a partir de .env.
- pytest — testes unitários e de integração.
- openpyxl — leitura de arquivos Excel .xlsx.
Estrutura do projeto
safeway-etl/
├── README.md
└── etl/
    ├── main.py                 # Ponto de entrada e argumentos CLI
    ├── requirements.txt        # Dependências Python
    ├── .env                    # Configuração local; não versionar credenciais
    ├── data/
    │   └── raw/                # Arquivos de origem baixados/localizados
    ├── logs/
    │   └── etl.log             # Log da execução
    ├── src/
    │   ├── config.py           # Constantes e filtros padrão
    │   ├── db.py               # Conexão e esquema do banco
    │   ├── extract.py          # Extração e validação
    │   ├── transform.py        # Limpeza e transformação
    │   ├── load.py             # Persistência e upsert
    │   ├── pipeline.py         # Orquestração das etapas
    │   └── utils.py            # Funções auxiliares
    └── tests/
        ├── test_extract.py
        ├── test_load.py
        ├── test_pipeline.py
        ├── test_transform.py
        └── test_utils.py
A pasta data/raw/ guarda arquivos de origem e pode crescer ao longo do tempo. Evite versionar arquivos grandes ou dados que não sejam necessários ao repositório.

Configuração
Execute os comandos a partir da pasta etl/.
1. Criar ambiente virtual e instalar dependências
python -m venv .venv
No Windows:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
No Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
2. Configurar variáveis de ambiente
Crie um arquivo .env dentro de etl/ ou defina as variáveis diretamente no ambiente:
DATABASE_URL=mysql+pymysql://usuario:senha@localhost:3306/safeway?charset=utf8mb4
ANP_PAGINA_URL=https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/levantamento-de-precos-de-combustiveis
- DATABASE_URL: URL de conexão SQLAlchemy com o banco. É obrigatória para executar a carga.
- ANP_PAGINA_URL: página usada para descobrir automaticamente a planilha mais recente; necessária quando a execução não recebe --origem nem --pagina.
Ajuste usuário, senha, host, porta, nome do banco e URL da página conforme o ambiente. Não publique o .env nem credenciais reais no Git. O banco indicado em DATABASE_URL precisa existir e aceitar conexões; a aplicação cria as tabelas ausentes, mas não cria o banco MySQL em si.
Instalação e execução
Entre na pasta do ETL:
cd etl
Executar com arquivo local
python main.py --origem data/raw/arquivo.xlsx
Também é possível informar um CSV:
python main.py --origem data/raw/arquivo.csv
Executar com URL direta do arquivo
python main.py --origem "https://servidor.exemplo/arquivo.xlsx"
Descobrir e processar a publicação mais recente
Usando ANP_PAGINA_URL configurada no .env:
python main.py
Ou informando a página diretamente:
python main.py --pagina "https://www.gov.br/anp/..."
O módulo procura na página o primeiro link cujo texto corresponde a Preços por posto revendedor. Essa lógica pressupõe que a página apresente a publicação mais recente primeiro e que o texto do link continue reconhecível.
Código de saída
- 0: execução concluída com sucesso.
- 1: ocorreu uma falha. Útil para automação e agendadores, como o Agendador de Tarefas do Windows.
Módulos e métodos
main.py — entrada da aplicação
Responsável por ler os argumentos da linha de comando, carregar as configurações, preparar os logs, conectar ao banco e iniciar o pipeline.
Método	Descrição
configurar_logging(pasta_logs="logs")	Configura o registro de mensagens no console e em logs/etl.log. O arquivo usa rotação ao atingir 1 MB e mantém até cinco arquivos antigos.
main(argv=None)	Carrega o .env, interpreta --origem e --pagina, cria o engine e as tabelas, escolhe entre execução direta e semanal e retorna o código de saída 0 ou 1.


src/config.py — configurações de negócio
Centraliza constantes utilizadas pelas demais etapas.
Constante	Descrição
MUNICIPIOS_GRANDE_SP	Lista padrão dos 39 municípios da Região Metropolitana de São Paulo usados como filtro geográfico.
ESTADO_PADRAO	Estado padrão do pipeline: SP.
TEXTO_LINK_POSTOS	Texto usado para localizar o link da planilha de preços por posto na página da ANP.
ESTADOS_SIGLAS	Mapeamento de nomes de estados normalizados para suas siglas.


src/extract.py — extração
Responsável por localizar, baixar, ler e validar os arquivos publicados pela ANP. Aceita CSV e XLSX.
Método	Descrição
encontrar_link_planilha(html, base_url, texto_link=...)	Analisa o HTML, procura um link cujo texto contenha o texto-alvo sem diferenciar acentos ou maiúsculas/minúsculas e retorna a URL absoluta. Lança LookupError se não encontrar.
obter_url_planilha_da_semana(pagina_url, texto_link=...)	Faz uma requisição HTTP à página da ANP e usa encontrar_link_planilha para obter o endereço da planilha mais recente.
baixar_arquivo(url, pasta_destino="data/raw")	Baixa o arquivo, cria a pasta de destino quando necessário e salva uma cópia com data e hora no nome. Identifica XLSX pela assinatura inicial do arquivo; caso contrário, usa a extensão CSV.
normalizar_coluna(nome)	Produz uma versão comparável do nome de uma coluna, removendo acentos, diferenças de caixa e pontuação.
padronizar_colunas(df, colunas_esperadas=...)	Renomeia colunas para os nomes canônicos esperados quando as diferenças são apenas de acentuação, caixa ou pontuação.
localizar_cabecalho(caminho, colunas_esperadas=..., max_linhas=30, minimo_colunas=3)	Procura nas primeiras linhas de um XLSX a linha que parece conter o cabeçalho real, ignorando títulos e informações introdutórias.
ler_planilha_anp(caminho)	Lê um CSV ou XLSX em um DataFrame. Para CSV, tenta diferentes combinações de separador e codificação; para XLSX, localiza o cabeçalho antes da leitura.
validar_colunas(df, colunas_esperadas=...)	Verifica se todas as colunas obrigatórias estão presentes e lança ValueError informando as colunas ausentes.
extrair(origem, colunas_esperadas=...)	Ponto de entrada da extração: baixa uma URL direta ou lê um caminho local, valida as colunas e devolve o DataFrame bruto validado.


A constante COLUNAS_ESPERADAS lista os campos que o arquivo da ANP deve fornecer. Se a agência alterar o layout, essa lista e as regras de leitura podem precisar de atualização.
src/transform.py — transformação
Converte os dados brutos em registros padronizados, filtrados e preparados para o banco.
Método/constante	Descrição
RENOMEAR_COLUNAS	Mapeia os nomes originais da planilha para nomes internos, como PREÇO DE REVENDA → preco_venda.
PRODUTOS_PADRAO	Define os produtos de gasolina considerados por padrão: GASOLINA, GASOLINA COMUM e GASOLINA ADITIVADA.
COLUNAS_TEXTO	Lista as colunas textuais que passam por padronização de espaços e caixa.
COLUNAS_FINAIS	Define as colunas e a ordem do DataFrame final enviado à carga.
apenas_digitos(valor, tamanho=None)	Remove caracteres não numéricos, completa com zeros à esquerda quando necessário e retorna None se o valor estiver vazio ou exceder o tamanho esperado. Trata números do Excel que chegam como float.
converter_preco(serie)	Converte preços com vírgula ou ponto decimal para valores numéricos; valores inválidos viram NaN.
_limpar(valor)	Remove espaços extras e converte valores nulos ou vazios em None.
formatar_numero(valor)	Formata o número do endereço, removendo a parte decimal desnecessária (1852.0 → 1852) e preservando valores como S/N.
montar_endereco(logradouro, numero, complemento)	Combina logradouro, número e complemento em um único campo de endereço.
transformar(df, produtos=None, municipios=None, estado=None)	Executa a transformação completa: seleciona e renomeia colunas, normaliza textos, filtra produtos e localização, define o nome da revenda, monta endereço, normaliza CNPJ/CEP, converte preço/data e remove registros inválidos e duplicados.


Regras principais de transformação
1. Mantém apenas os produtos configurados; por padrão, as opções de gasolina definidas em PRODUTOS_PADRAO.
2. Converte o estado para sigla e, quando informados, aplica filtros de estado e municípios.
3. Compara nomes de municípios ignorando acentos e diferenças entre maiúsculas e minúsculas.
4. Usa o nome fantasia como revenda; se estiver vazio, usa a razão social.
5. Normaliza CNPJ para 14 dígitos e CEP para 8 dígitos.
6. Converte preços para números e datas para o formato de data reconhecido pelo pandas.
7. Descarta registros sem CNPJ válido, preço válido/positivo ou data válida.
8. Remove duplicatas pela combinação de CNPJ, produto e data de coleta, mantendo a última ocorrência.
src/load.py — carga
Persiste o DataFrame transformado no banco usando upsert: insere novos registros e atualiza os existentes que tenham a mesma chave única.
Método/constante	Descrição
COLUNAS_OBRIGATORIAS	Campos que devem existir no DataFrame para a carga.
COLUNAS_ATUALIZAVEIS	Campos atualizados quando um registro com a mesma chave já existe.
_valor_para_banco(coluna, valor)	Converte nulos do pandas para None, timestamps para date, preços para Decimal e limita textos ao tamanho definido no esquema.
preparar_registros(df)	Valida as colunas necessárias e transforma as linhas do DataFrame em uma lista de dicionários compatível com o banco.
_montar_upsert(engine)	Monta a instrução específica do banco: ON DUPLICATE KEY UPDATE no MySQL ou ON CONFLICT DO UPDATE no SQLite. Outros dialetos não são suportados por esse método.
carregar(df, engine, tamanho_lote=1000)	Insere/atualiza os registros em lotes dentro de uma única transação. Retorna a quantidade de registros processados; se um lote falhar, a transação é revertida.


src/pipeline.py — orquestração
Conecta as etapas de extração, transformação e carga.
Método	Descrição
executar_pipeline(origem, engine, municipios=..., estado=..., produtos=None)	Executa o ETL completo a partir de uma URL ou arquivo local. Retorna um dicionário com linhas_extraidas, linhas_transformadas e linhas_carregadas. Lança RuntimeError se nenhum registro sobreviver aos filtros.
executar_semanal(pagina_url, engine, **kwargs)	Localiza a planilha mais recente na página da ANP e chama executar_pipeline com a URL encontrada.


Por padrão, executar_pipeline utiliza MUNICIPIOS_GRANDE_SP e ESTADO_PADRAO. Para ampliar ou alterar o escopo, passe outros valores para municipios, estado ou produtos. Para não filtrar por municípios ou estado, passe municipios=None ou estado=None, respectivamente.
src/db.py — banco de dados
Define a tabela, a chave de unicidade, o índice de consulta e a conexão via SQLAlchemy.
Método/constante	Descrição
metadata	Objeto SQLAlchemy que reúne a definição das tabelas.
CHAVE_UNICA	Chave natural composta por cnpj, produto e data_coleta, usada para evitar duplicação lógica.
precos_combustiveis	Definição da tabela precos_combustiveis, incluindo tipos, chave primária, restrição de unicidade e índice para consultas por município, produto e data.
get_engine(url=None)	Cria o engine SQLAlchemy usando a URL fornecida ou a variável DATABASE_URL. Lança ValueError se a URL não estiver configurada.
criar_tabelas(engine)	Cria as tabelas definidas que ainda não existem, sem substituir as tabelas existentes.


src/utils.py — funções auxiliares
Reúne funções de normalização reutilizadas por outros módulos.
Método	Descrição
normalizar_texto(valor)	Remove acentos, normaliza espaços e converte o texto para maiúsculas. Retorna None para valores nulos. Ajuda a comparar, por exemplo, São Paulo e SAO PAULO.
para_sigla_uf(valor)	Converte o nome normalizado de um estado para a sigla correspondente; se já receber uma sigla de duas letras, retorna essa sigla em maiúsculas. Retorna None para valores nulos ou nomes não reconhecidos.


Banco de dados
A tabela precos_combustiveis possui os seguintes campos principais:
Campo	Finalidade
id	Identificador numérico da linha.
cnpj	CNPJ do posto revendedor.
produto	Combustível registrado.
data_coleta	Data em que o preço foi coletado.
estado, municipio	Localização do posto.
revenda, endereco, bairro, cep	Identificação e endereço da revenda.
preco_venda	Preço de revenda, armazenado com precisão decimal.
unidade_medida, bandeira	Unidade declarada e bandeira da revenda.


A restrição única (cnpj, produto, data_coleta) permite manter o histórico por data sem duplicar o mesmo registro quando o processo é executado novamente. Se o mesmo posto, produto e data aparecerem de novo, o upsert atualiza os demais campos.

O índice ix_municipio_produto_data foi definido para apoiar consultas por município, produto e data.
Testes
Os testes ficam em etl/tests/ e cobrem as etapas de extração, transformação, carga, pipeline e utilitários. Os testes de banco usam SQLite em memória ou temporário, evitando a necessidade de um MySQL para essa parte da suíte.

A partir da pasta etl/, instale as dependências e execute:
python -m pytest tests/ -v
Para executar um arquivo específico:
python -m pytest tests/test_transform.py -v
Os testes verificam, entre outros casos, a padronização de dados, tratamento de valores nulos, filtros geográficos, remoção de duplicatas, idempotência da carga e rollback quando uma operação falha.
Logs e tratamento de erros
As mensagens de execução são registradas no console e em etl/logs/etl.log. O arquivo de log usa rotação para limitar seu tamanho e preservar arquivos anteriores.

O processo registra erros e retorna código de saída 1 quando ocorre uma exceção. Entre os erros que podem interromper o pipeline estão:
- DATABASE_URL ausente ou conexão com o banco indisponível;
- arquivo local inexistente ou falha no download;
- alteração no texto do link ou no formato da publicação da ANP;
- colunas obrigatórias ausentes;
- nenhuma linha restante depois dos filtros de transformação.
Observações
- A planilha publicada pela ANP pode mudar de estrutura, nomenclatura ou formato. A extração valida as colunas esperadas e falha de forma explícita quando elas não são encontradas.
- A descoberta automática depende de a página da ANP listar a publicação mais recente primeiro e de o texto do link continuar correspondendo a TEXTO_LINK_POSTOS.
- O escopo geográfico e os produtos padrão são definidos no código e podem ser ajustados conforme a necessidade do projeto.
- A carga foi implementada para MySQL e SQLite; outros bancos exigem implementação do upsert correspondente.
- Não inclua senhas, tokens, arquivos .env reais ou outros segredos no repositório.