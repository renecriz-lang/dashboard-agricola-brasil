# Geração do Mapa Municipal para o Power BI

Este documento descreve, passo a passo, o processo de criação do arquivo
`municipios_brasil.topojson` a partir do shapefile oficial do IBGE. O objetivo é
que qualquer pessoa — mesmo sem conhecimento técnico aprofundado — possa entender
o que foi feito e por quê.

---

## 1. Objetivo

O Power BI possui um visual chamado **Shape Map** (Mapa de Formas) que permite
colorir regiões geográficas conforme dados numéricos — por exemplo, exibir a
produção de soja por município com gradiente de cor. Para funcionar, esse visual
precisa de um arquivo no formato **TopoJSON** contendo os contornos de cada região.

O IBGE disponibiliza a malha municipal em formato **Shapefile**, que é o padrão
usado em softwares de geoprocessamento profissional (QGIS, ArcGIS etc.), mas que o
Power BI não aceita diretamente. Por isso, foi necessário converter o Shapefile para
TopoJSON, reprojetar as coordenadas para o padrão internacional e reduzir o tamanho
do arquivo para que o Power BI carregue o mapa com fluidez.

---

## 2. Fonte dos dados

| Item | Detalhe |
|------|---------|
| **Órgão** | Instituto Brasileiro de Geografia e Estatística (IBGE) |
| **Produto** | Malha Municipal Digital — 2025 |
| **Cobertura** | 5.570 municípios brasileiros |
| **Link oficial** | https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html |
| **Formato original** | Shapefile (`.shp`, `.dbf`, `.shx`, `.prj`, `.cpg`) |
| **Sistema de coordenadas original** | SIRGAS 2000 — EPSG:4674 (padrão geodésico oficial do Brasil) |

---

## 3. Bibliotecas utilizadas

O script foi escrito em **Python 3** e usa duas bibliotecas externas:

| Biblioteca | O que faz |
|-----------|-----------|
| **geopandas** | Lê e manipula dados geográficos (shapefiles, GeoJSON, etc.), oferecendo a mesma interface do pandas mas para geometrias. |
| **topojson** | Converte geometrias para o formato TopoJSON, detectando automaticamente fronteiras compartilhadas entre polígonos vizinhos para que a simplificação não crie lacunas ou sobreposições entre municípios. |

Para instalar:

```bash
pip install geopandas topojson
```

---

## 4. Passo a passo

### Etapa 1 — Leitura e inspeção do shapefile

O primeiro passo é carregar o shapefile e inspecionar sua estrutura para entender
o que está disponível.

```python
import geopandas as gpd

gdf = gpd.read_file("BR_Municipios_2025/BR_Municipios_2025.shp")

print(f"Feições carregadas : {len(gdf):,}")   # deve ser 5.573
print(f"CRS original       : {gdf.crs}")       # EPSG:4674 (SIRGAS 2000)
print(f"Colunas            : {gdf.columns.tolist()}")
print(gdf.head(3).to_string())
```

**Resultado observado:** 5.573 feições (a malha 2025 inclui 3 feições além das
5.570 municípios padrão — ilhas oceânicas contabilizadas separadamente). As colunas
relevantes são `CD_MUN` (código IBGE de 7 dígitos) e `NM_MUN` (nome do município).

O script identifica automaticamente a coluna de código procurando por colunas cujos
valores sejam inteiramente compostos por exatamente 7 dígitos numéricos, sem depender
de um nome fixo — o que torna o processo robusto caso o IBGE renomeie as colunas
em edições futuras.

---

### Etapa 2 — Preparação e reprojeção

O Power BI Shape Map exige que as coordenadas estejam no sistema **WGS84
(EPSG:4326)**, que é o mesmo utilizado pelo GPS e pelo Google Maps: latitude e
longitude em graus decimais. O shapefile do IBGE usa SIRGAS 2000 (EPSG:4674), que
é muito próximo do WGS84, mas tecnicamente diferente — a reprojeção elimina qualquer
desvio.

```python
# Reprojetar para WGS84
gdf = gdf.to_crs(epsg=4326)

# Manter apenas as colunas necessárias e renomear
gdf = gdf[["CD_MUN", "NM_MUN", "geometry"]].copy()
gdf = gdf.rename(columns={"CD_MUN": "cod_ibge", "NM_MUN": "nome_municipio"})

# Garantir que cod_ibge seja inteiro (sem zeros à esquerda, sem ".0")
gdf["cod_ibge"] = gdf["cod_ibge"].astype(int)
```

**Por que manter só 2 colunas?** Cada propriedade armazenada em cada feição aumenta
o tamanho do arquivo JSON. O shapefile original tem 15 colunas (nome da região
geográfica imediata, nome da região intermediária, área em km², etc.) — nenhuma delas
é necessária para o Power BI. Mantendo apenas `cod_ibge` e `nome_municipio`, o arquivo
final fica até 40% menor.

**Por que `cod_ibge` precisa ser int?** O CSV de dados (`dados_consolidados.csv`) também
armazena o código como inteiro. Se os tipos forem diferentes (um inteiro e outro string),
o Power BI não consegue fazer o cruzamento entre mapa e dado — os municípios aparecem
no mapa mas ficam sem cor.

---

### Etapa 3 — Simplificação topológica

Esta é a etapa mais crítica. O shapefile original tem resolução muito alta (coordenadas
precisas ao milímetro em escala geográfica), o que resulta em arquivos de 50–80 MB após
conversão direta. O Power BI não carrega arquivos tão grandes com fluidez.

A solução é **simplificar as geometrias** — reduzir o número de pontos que formam o
contorno de cada município, mantendo a forma reconhecível mas eliminando detalhes
imperceptíveis na escala de um mapa nacional.

**Por que usar a biblioteca `topojson` em vez do `simplify` do shapely?**

O método `simplify()` padrão do shapely simplifica cada polígono de forma
**independente**. Isso quebra fronteiras compartilhadas: o município A simplifica sua
borda norte de uma forma e o município B (que é vizinho) simplifica a mesma borda de
outra forma — criando lacunas ou sobreposições visíveis no mapa.

A biblioteca `topojson` detecta automaticamente todos os arcos (segmentos de fronteira)
que são **compartilhados** entre municípios vizinhos e os representa uma única vez. A
simplificação é aplicada sobre esses arcos compartilhados, garantindo que ambos os
lados de uma fronteira permaneçam idênticos após a simplificação.

```python
import topojson

# Construir a topologia com presimplify=0.01 graus (algoritmo Douglas-Peucker)
topo = topojson.Topology(
    gdf,
    prequantize=1e4,      # quantiza coordenadas antes da computação (reduz uso de memória)
    presimplify=0.01,     # simplifica vértices antes de construir a topologia
    topology=True,        # ativa a detecção de fronteiras compartilhadas
    object_name="municipios",
)
```

**Sobre a tolerância de 0,01 graus:** Em latitude/longitude, 0,01 grau equivale a
aproximadamente 1,1 km. Isso significa que detalhes menores que ~1 km são descartados.
Em uma tela de 1920×1080 exibindo o Brasil inteiro, 1 km equivale a menos de 1 pixel —
portanto a simplificação é visualmente imperceptível.

O script testa automaticamente tolerâncias em sequência crescente (0,005 → 0,01 →
0,02 → ...) e para quando o arquivo gerado fica entre 1 MB e 3 MB — intervalo que
oferece boa fluidez no Power BI sem deformar visivelmente os contornos.

**Resultado:** tolerância de 0,01 graus → arquivo de **2,14 MB** (versus ~70 MB sem
simplificação).

---

### Etapa 4 — Exportação

```python
topo.to_json(fp="municipios_brasil.topojson")
```

O método `to_json()` salva o arquivo em formato **JSON compacto** (sem espaços
desnecessários), com encoding **UTF-8**, preservando acentos nos nomes dos municípios
(São Paulo, Açailândia, Conceição do Araguaia, etc.).

O formato TopoJSON é um superconjunto do GeoJSON: além de armazenar as geometrias,
registra explicitamente quais arcos são compartilhados — o que é exatamente o que
permite a simplificação sem lacunas descrita acima.

---

### Etapa 5 — Validação

Após salvar, o script reabre o arquivo e verifica:

```python
import json

with open("municipios_brasil.topojson", encoding="utf-8") as f:
    topo_dict = json.load(f)

features = topo_dict["objects"]["municipios"]["geometries"]
print(f"Municípios: {len(features):,}")   # deve ser próximo de 5.570

# Verificar códigos conhecidos
for cod in [3550308, 3304557, 4106902]:   # SP, RJ, Curitiba
    encontrado = next(
        (f["properties"]["nome_municipio"] for f in features
         if f["properties"]["cod_ibge"] == cod), None
    )
    print(f"{cod} -> {encontrado}")
```

**Resultado da validação:**
- 5.573 municípios no arquivo (corresponde ao shapefile de origem)
- 5.573 com `cod_ibge` preenchido (100%)
- São Paulo (3550308) ✓ — Rio de Janeiro (3304557) ✓ — Curitiba (4106902) ✓

---

## 5. Resultado final

| Item | Valor |
|------|-------|
| **Arquivo gerado** | `municipios_brasil.topojson` |
| **Tamanho** | 2,14 MB |
| **Municípios** | 5.573 feições |
| **Tolerância de simplificação** | 0,01 graus (~1,1 km) |
| **Encoding** | UTF-8 |
| **CRS** | EPSG:4326 (WGS84) |

### Como usar no Power BI

1. **Habilitar o Shape Map:** Arquivo → Opções e configurações → Opções →
   Versão Prévia dos Recursos → ativar **Shape Map**.

2. **Adicionar o visual Shape Map** ao relatório.

3. **Importar o TopoJSON:** No painel de formato do visual, em **Mapa** →
   clique em **Adicionar mapa** e selecione o arquivo `municipios_brasil.topojson`.

4. **Configurar o campo de localização:** Arraste o campo `cod_ibge` do seu
   conjunto de dados para o campo **Localização** do visual.

5. **Importante:** O valor de `cod_ibge` no seu conjunto de dados precisa ser
   do mesmo tipo (inteiro) e conter os mesmos 7 dígitos. O campo `cod_ibge` no
   arquivo `dados_consolidados.csv` já está formatado corretamente para este fim.

---

## 6. Possíveis problemas e soluções

### O mapa carrega lento ou o Power BI trava

O arquivo de 2,14 MB é adequado para a maioria dos computadores. Se houver lentidão,
regenere o mapa com `presimplify=0.04` para reduzir para ~1,1 MB (leve redução de
qualidade, aceitável para mapas nacionais).

### Municípios aparecem no mapa mas ficam sem cor

Isso indica que o `cod_ibge` do CSV não está sendo reconhecido como igual ao do
TopoJSON. Verifique:
- O campo está configurado como **número inteiro** (não texto) no Power BI
- Não há zeros à esquerda nem sufixo `.0` nos valores do CSV
- O campo de localização no visual está mapeado para `cod_ibge` (e não para o nome)

### Municípios não aparecem no mapa

Se um município está no CSV mas não aparece colorido no mapa, o `cod_ibge` desse
município provavelmente não existe no TopoJSON. Isso pode ocorrer para municípios
criados após 2025 (data da malha) ou para municípios com código diferente do
padrão IBGE. Use o visual de tabela para identificar os códigos sem correspondência.

### Erro de encoding (caracteres estranhos nos nomes)

O arquivo TopoJSON é salvo em UTF-8. Se os nomes aparecerem com caracteres errados
no Power BI, verifique se o arquivo não foi aberto e salvo novamente por outro
programa que o converteu para Latin-1 (Windows-1252). Sempre use o arquivo gerado
diretamente pelo script.

### Erro ao executar o script: `ModuleNotFoundError`

Execute antes:

```bash
pip install geopandas topojson
```

Se o `pip` não encontrar o geopandas (comum no Windows), tente:

```bash
pip install geopandas --find-links https://girder.github.io/large_image_wheels
```
