# Dashboard Agrícola Brasileiro

Dashboard interativo de produção agrícola municipal no Brasil, combinando dados históricos do IBGE/PAM com estimativas mensais da CONAB.

## Dados

| Arquivo | Fonte | Atualização |
|---|---|---|
| `dados_consolidados.csv` | IBGE/PAM — municípios, 1974–2024 | Manual |
| `conab_atual.csv` | CONAB — boletim mensal por UF | Automática (diária) |

## Pipeline automatizado (CONAB)

O workflow `atualizar_conab.yml` roda todo dia às **9h BRT** via GitHub Actions:

1. `conab/baixar_conab.py` — acessa o site da CONAB e baixa o XLSX se houver versão nova
2. `conab/etl_conab.py` — lê o XLSX e gera `conab_atual.csv` com validação de estrutura
3. Se o XLSX ou a estrutura das abas mudarem de forma incompatível, o CSV existente é preservado e o job termina com aviso

O arquivo `conab/raw/ultimo_baixado.txt` registra qual versão foi baixada (controle de idempotência).

## Como rodar localmente

```bash
pip install -r requirements.txt

# Baixar XLSX mais recente (só faz algo se houver versão nova)
python conab/baixar_conab.py

# Gerar conab_atual.csv a partir do XLSX atual
python conab/etl_conab.py
```

Ambos os scripts devem ser executados **a partir da raiz do repositório**.

## Estrutura

```
├── conab/
│   ├── raw/               # XLSX baixado + registro de versão
│   ├── baixar_conab.py    # download do boletim CONAB
│   └── etl_conab.py       # ETL: XLSX → CSV
├── ibge/                  # scripts de coleta IBGE (futuro)
├── powerbi/               # arquivos auxiliares Power BI
├── docs/                  # documentação técnica
├── .github/workflows/     # automação GitHub Actions
├── dados_consolidados.csv # dados IBGE por município
└── conab_atual.csv        # estimativas CONAB por UF (atualizado automaticamente)
```
