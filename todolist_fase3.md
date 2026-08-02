# TO-DO — Fase 3: validação ponta a ponta + escala

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi Cavalcante · João — CESUPA
**Base:** `fase3_validacao_escala.md` · **Harness:** `validation/equivalence.py::compare` · **Bugs:** `bugs_originais.md`
**Pré-requisito:** Fases 0, 1 e 2 fechadas

> Esta fase não porta nada — **mede**. O produto é evidência: CSVs e tabelas. O
> código que entra é de bateria (orquestração, cronometragem, coleta).
>
> **Risco dominante: afirmar número que não foi medido.** Todo valor sai de uma
> corrida registrada, não de um `.md` anterior.

## Estado em 02/08/2026

| Bloco | Situação |
|---|---|
| **3.0** infra | fechado |
| **3.1** corretude | **fechado** — Northwind (dois caminhos) e grafo (4 escalas × oráculo semeado); Sakila descartado |
| **3.2** escala | **fechado** — 40 corridas, quatro CSVs; a interpretação dos números é 3.4 |
| **3.3** bugs | **fechado** — #6/#7 sem patch em escala, #8 medido dos dois lados |
| **3.4** análise | não começou — depende da re-execução no formato novo (ver abaixo) |

**Todos os números deste documento saíram de uma única sessão de medição**
(02/08, ~1h30, kernel **6.17.0-40**): `run_oracle_neo4j.py --seed 23` seguido de
`run_scale_suite.sh` com as sementes 23, 69 e 207. Nenhuma tabela mistura
ambientes.

> **Pendência de evidência, não de conclusão.** Aquela sessão gravou no formato
> **antigo** de CSV — um arquivo por bateria. O formato foi refeito depois (uma
> tabela por grão, ver §3.0), e os arquivos antigos saíram de `results/`. As
> conclusões abaixo continuam válidas, porque vieram de corridas reais no kernel
> pinado; o que falta é **regenerar os arquivos** no formato novo. São ~1h30, os
> mesmos comandos, mais o `run_oracle_mongo.py`, que **nunca rodou**.

## Regras da fase

1. **O critério é casar com o oráculo, não com o volume real.** O #8 é replicado de propósito (`bugs_originais.md` §#8: "Decisão no porte: replicar"), e o oráculo também não o corrige — `oracle/patches/` tem `0001`, `0004`(×2), `0005`, `0006`, `0007`, **não existe `0008`**. Um resultado que "acertasse" o volume real no paradigma documento estaria **fora** do gate. O 50/50 do User Profiles e o 17/17 do Northwind são do experimento original **com** a correção: contexto do que o bug custa, nunca alvo.
2. **Todo `count` publicado vem com o caminho de extração que o produziu** — a quantidade de divergências do #8 é ordem-dependente.
3. **Todo par de números declara dataset e tamanho.** Já se chegou a contrastar grafo `larger` (800k) com Northwind (397 documentos).
4. **Comparar tendência, nunca tempo absoluto** — Python × JVM, e o baseline do artigo é outra máquina.

---

## 3.0 — Infra de bateria — **FECHADO**

> O guia assumia "ler o tempo de inferência do log do Spark". Não existe log de
> executor: a 2.0 decidiu driver nativo, pura-Python. A medição é em processo.

### Scripts

| Script | Papel |
|---|---|
| `output.py` | escrita das quatro tabelas de resultado — usado por todas as baterias |
| `run_scale_mongo.py` | bateria de escala do documento (2 rotas × 4 tamanhos) |
| `run_scale_neo4j.py` | bateria de escala do grafo (4 escalas), compara com `resources/` |
| `run_oracle_mongo.py` | cadeia porte × **oráculo semeado** no documento (`--kind mongodb`) |
| `run_oracle_neo4j.py` | cadeia porte × **oráculo semeado** no grafo: regera, roda os dois lados sobre a mesma instância, compara |
| `run_scale_suite.sh` | encadeia N sementes nas duas baterias de escala, sequencialmente |
| `run_northwind.py` | corretude do Northwind pelos dois caminhos de leitura (arquivo e banco) |
| `check_northwind_invariants.py` | invariantes estruturais do Northwind, lidos do XMI |
| `gen_userprofiles{,_neo4j}.py` | geradores, ambos com `--seed` |
| `clean_databases.py` | apaga só os `up_*` e o grafo — nunca o `northwind` |

O módulo se chama `output.py` e não `results.py` porque o diretório de saída na
raiz é **`results/`**: um módulo homônimo vira *namespace package* e o mypy passa
a resolver o import para a pasta de dados.

- [x] **Cronometragem em processo**, separando **extração** (I/O do driver) de **inferência+construção**. Resultado: nos dois paradigmas a inferência é ≤0,05s e **o custo é todo de extração** — o rótulo "tempo de inferência" do artigo mede, na prática, extração.
- [x] **Sem `cli.py`/`[project.scripts]`.** Um script por bateria com `argparse`. A entrega é a equivalência demonstrada, não uma ferramenta de linha de comando.
- [x] **Baterias não rodam em paralelo.** Os clientes Python não disputam, mas mongod e Neo4j disputam CPU e disco. No grafo nem cabe paralelismo: Community tem um banco só.
- [x] **Guarda de cabeçalho** nos CSVs: recusa anexar num arquivo de esquema antigo em vez de corromper em silêncio.

### Formato dos CSVs — fixado em 02/08/2026

`roteiro_experimental.md` §6–7, que definia o formato, **não existe neste
repositório**. O esquema abaixo passa a ser a referência.

**Refeito em 02/08/2026: uma tabela por grão.** A primeira versão dava um CSV
por bateria, o que misturava três granularidades no mesmo arquivo — os tempos da
corrida repetidos em cada linha de entidade, o veredito repetido em cada linha
de divergência — e obrigava a deduplicar antes de analisar. Pior: o mesmo fato
saía *long* numa bateria e *wide* noutra. Escrita em `scripts/output.py`.

| Arquivo | Grão | Chave |
|---|---|---|
| `corridas.csv` | uma corrida | `corrida_id` |
| `entidades.csv` | uma entidade por corrida | `corrida_id` + `entidade` |
| `comparacoes.csv` | um confronto com um XMI de referência | `corrida_id` + `referencia` |
| `divergencias.csv` | uma divergência | `corrida_id` + `referencia` |

O `corrida_id` é determinístico — `escala-mongodb-up_a_small-23`,
`oraculo-neo4j-movies_min-23`, `corretude-mongodb-northwind-arquivo` —, montado
a partir de bateria, paradigma, alvo, semente e origem. A **bateria** entra na
chave porque a mesma escala com a mesma semente é medida duas vezes, na bateria
de escala e na cadeia do oráculo, e são corridas distintas.

Decisões de coluna:

- **`origem`** (`arquivo`/`banco`) e **`referencia`** (`resources`/`oraculo_semeado`) são o que torna as linhas comparáveis: o #8 é sensível ao caminho de leitura, e o mesmo dataset confrontado com referências diferentes dá resultados diferentes **de propósito**.
- **`capturado` saiu** — é `modelo / real`, conta da análise, não dado.
- **`linhas_tripla` e `arquetipos` continuam separadas**, vazias no paradigma que não as produz. Fundi-las esconderia que os dois não passam pelo mesmo núcleo de construção.
- **`pico_memoria` não entra**: nenhuma corrida mediu isso, e coluna vazia num CSV de evidência é pior que coluna ausente.

### Máquina de referência

| | |
|---|---|
| **CPU** | Intel Core i9-14900K — 24 núcleos (8P + 16E), 32 threads, até 6,0 GHz, L3 36 MiB |
| **RAM** | 64 GB (62 GiB úteis) + swap de 2 GB em arquivo |
| **Disco** | NVMe Kingston SNV3S1000G 931,5 GB, ext4 na raiz (os bancos moram aqui) |
| **SO** | Linux Mint 22.3 |
| **Kernel** | **6.17.0-40-generic** — o pin da fase |
| **Python** | 3.12.3 (uv 0.11.14) |
| **MongoDB** | 8.0.28 · **Neo4j** 2026.06.0 Community |
| **Docker** | 29.7.1 · imagem `extrator-uschema`: Temurin JDK 1.8.0_492, Maven 3.9.16, Spark 3.0.1 |

Ressalvas que mudam a leitura dos tempos:

1. **O `6.17.0-40` é o único kernel onde as duas metades rodam** — o `mongod` 8.0.28 não sobe no 7.0.0-28 (ver Riscos), e o Neo4j sobe nos dois. Por isso o pin. As corridas anteriores, feitas no 7.0.0-28, foram descartadas e refeitas aqui.
2. **Corretude não depende de kernel nem de máquina** — `equivalent=True`, as zero divergências e o 19/17 do Northwind saem da semente e do código. Só a tabela de **tempo** é sensível ao ambiente.
3. **O baseline do artigo também é um i9**, de geração não informada. A coincidência de nome não autoriza comparação absoluta.
4. **Bancos e saídas em sistemas de arquivos diferentes:** os bancos em `/var/lib/...` (ext4 no NVMe, sem cifra); o repositório, e portanto `out/` e `results/`, em `/home/davi`, que é **eCryptfs**. A extração mede I/O sem cifra; a escrita dos XMIs passa pela camada cifrada.
5. **Governor `powersave` com turbo ligado** — frequência não fixa. Mantido de propósito (medir a máquina como ela é usada), mas explica parte da dispersão entre sementes.
6. **A identidade da imagem do oráculo não precisa entrar no CSV:** o que determina o XMI é o fonte, pinado por SHA no `Dockerfile`. O único resíduo é a tag base `maven:3.9-eclipse-temurin-8`, que flutua e mexe marginalmente no `t_oraculo` — e as versões que ela entrega estão na tabela acima.

---

## 3.1 — Corretude

### Northwind — **fecha**

- [x] **`equivalent=True` pelos dois caminhos de leitura**, com só divergências não-fatais, todas na assinatura do #8. 17 coleções, 397 documentos, **49 linhas de tripla nos dois** (`scripts/run_northwind.py`, evidência em `results/comparacoes.csv`).
- [x] **A ordem-dependência do #8 está medida numa corrida só, com os dois caminhos lado a lado** — 15 divergências lendo os arquivos, 12 lendo o cursor do Mongo, mesmo dado:

| | arquivo | banco (cursor) |
|---|---|---|
| divergências | 15 | 12 |
| coleções fechando | **14/17** | **14/17** |
| `orders` (48 reais) | 24 | 38 |
| `products` (45 reais) | 40 | 40 |
| `purchase_orders` (28 reais) | 22 | 23 |

- [x] **O que é invariante e o que não é** — a distinção que o número sozinho esconde: **quais** coleções o #8 atinge não muda (sempre `orders`, `products`, `purchase_orders`, sempre 14/17 fechando), e `products` até captura o mesmo 40 nos dois. O que muda é **quanto** ele come nas outras duas. Citável: `equivalent=True` + não-fatais + 14/17. Não citável sem dizer a origem: o número de divergências e o `count` de `orders`.
- [x] **SHA-256 do dataset registrado** na saída do script (`3700157b…`), já que os JSONs não são versionados e não têm outro identificador.
- [x] **Invariantes estruturais confirmados** (`check_northwind_invariants.py`, 02/08), idênticos no XMI do oráculo e no do porte: **19 `EntityType`**, **17 raiz**, as duas não-raiz sendo `Detail` e `_id`, e `Aggregate` para `Detail` com `upperBound=-1`/`optional=true` em `Orders` e `Purchase_orders`.
  - **Não é redundante com o `compare()`:** o harness afirma que os dois lados são **iguais**, não **o que** o modelo contém. Se `Detail` sumisse dos dois, ele seguiria dando `equivalent=True`. E o invariante é **livre de contagem**, então escapa da ordem-dependência do #8.
  - **Vale por variação, não por entidade:** 9 `Aggregate` para `Detail` em `Orders` e 8 em `Purchase_orders`, um por variação que tem `details`.
  - **Achado: `fase3_validacao_escala.md:42` erra ao dizer "17 coleções, `_id` inteiros".** `sales_reports` e `strings` têm `_id` **objeto** — é daí que sai a entidade não-raiz `_id`, agregada com `upperBound=1`/`optional=false`, forma oposta à do `Detail`.
- [x] **Proveniência do dataset levantada (02/08/2026)** — detalhe em `resources/README.md`, "De onde vem o dataset do Northwind":
  - Os JSONs vêm de **<https://github.com/jasny/mongodb-northwind>** (Arnold Daniels, 2020): a versão MongoDB do banco de exemplo **Northwind** do Microsoft Access 2010, derivada do MyWind (MySQL). O clone local está no commit inicial `967bfec`.
  - **Licença BSD 2-Clause** — redistribuir em forma de fonte é permitido mantendo o aviso de copyright e o disclaimer. **Versionar os 17 arquivos neste repo é legítimo**, levando o `LICENSE` junto.
  - As transformações relacional → documento são daquele repositório, não do U-Schema: `_id` como chave primária de toda coleção, `order_details` embutido como `details` em `orders` (e idem em `purchase_order`), `products.supplier_ids` como lista de `int`. **A entidade `Detail` do invariante 19/17 nasce daí.**
  - **A entrada do oráculo não é publicada, só a saída.** Nos dois clones Java existe um único arquivo citando Northwind — o `outputs/model_northwind.xmi`, origem do nosso `resources/mongodb/model_northwind.xmi`. Sem dados, sem script de carga, sem lista de coleções. Não se prova que usaram este dataset; a evidência é indireta — 14/17 coleções com `count` idêntico, e as 3 restantes falhando pelo #8, não por volume.
- [x] **JSONs versionados em `resources/datasets/northwind/`** (02/08/2026, decisão do Davi): os 17 arquivos (304 KB) mais o `LICENSE` exigido pela BSD 2-Clause e um `README.md` com proveniência, commit de origem e o digest. O `run_northwind.py` passou a ler daí por padrão e reproduz **o mesmo SHA-256 e o mesmo resultado** da cópia externa. **O único dataset da fase que não se regenera por semente agora está preso ao repositório.**
- [x] **Decidido: o Northwind NÃO vira teste de CI.** Com os dados versionados o caminho `arquivo` roda offline, então o teste seria viável (~2s, sem banco) — e foi por isso que se cogitou. **Recusado porque a intenção declarada é corrigir os bugs catalogados no futuro:** um teste afirmando `14/17` cimentaria em CI justamente o comportamento que se pretende consertar, e viraria alarme falso no dia da correção. O resultado continua sendo produzido sob demanda pelo `run_northwind.py`, com CSV.
- [x] **Decidido (02/08/2026): a "variação estrutural sobre o aninhado" (`fase3_validacao_escala.md:45`) NÃO entra no `check_northwind_invariants.py`.** O que ela descreve foi investigado no fonte e é **design do original, não defeito**: o agregado é nomeado pelo campo, sem o caminho, então `orders.details` e `purchase_orders.details` colapsam num único `Detail` com 5 variações em duas famílias disjuntas. Evidência de linha em `bugs_originais.md`, "O que **não** é defeito". Sem defeito contra o que proteger, não há verificação a acrescentar.
  - **Limitação que fica declarada:** o `compare_aggregate` casa as variações agregadas **só pelo nome do container** (deliberado, é o que evita recursão em agregado cíclico), então o mapeamento variação-pai → variação-filha é a única parte do modelo que a equivalência estrutural não verifica. Nenhuma evidência de que divirja — apenas não é coberto.

### User Profiles / grafo — **fecha nas quatro escalas**

`run_oracle_neo4j.py --seed 23` roda os dois lados sobre **a mesma instância** —
mesma entrada, duas implementações. É o padrão-ouro da corretude do grafo.

| escala | `User` | `Movie` | vs oráculo semeado | vs `resources/` |
|---|---|---|---|---|
| small (100k) | 100.000 — 100% | 50.000 — 100% | **True, 0** | True, 7 não-fatais |
| medium (200k) | 200.000 — 100% | 100.000 — 100% | **True, 0** | True, 7 não-fatais |
| large (400k) | 400.000 — 100% | 200.000 — 100% | **True, 0** | True, 7 não-fatais |
| larger (800k) | 800.000 — 100% | 400.000 — 100% | **True, 0** | True, 7 não-fatais |

- [x] **9 arquétipos nas quatro escalas** — a estrutura não muda com o volume. **Leitura integral confirmada**: soma dos `count` == volume gerado, contra banco real. O grafo tem núcleo próprio; o #8 não passa por lá.
- [x] **As 7 não-fatais contra `resources/` não são defeito do porte** — são de `count`, nas 5 variações de `User` mais `WATCHED`/`FAVORITE`, dentro do ruído de amostragem. Os XMIs de `resources/` vêm de uma instância de **semente desconhecida**; contra a mesma instância, zero. A variável isolada é o dataset.
- [x] **É a extração do grafo que passou a ser confrontada com o oráculo.** A 2.2 comparava arquétipos **reconstruídos a partir do próprio XMI**; aqui eles vêm do banco, por bolt.
- [x] **O container aguenta o `larger`** — 10,2M arestas com `--memory=6g`, sem estouro. Era o risco declarado: a 0.5 só tinha exercitado `--kind neo4j` em grafo mínimo.
- [x] **Achado que destrava o Neo4j Community** (lido no `Neo4j2USchema.java` do SHA pinado): o `--db` **não é usado para conectar** — o `SparkProcess` recebe só `(samplingRatio, bolt, user, password)` e sempre lê o banco padrão. O nome vai para `Json2USchemaModel`, ou seja, é o **nome do schema**. Consequência: um único banco de usuário não é obstáculo, mas o valor tem de casar com o do porte — divergência de `SCHEMA_NAME` é **fatal** no harness.
- [x] **`N1` não disparou** e não podia: nenhum nó multi-label no dataset (`size(labels(n)) > 1` = 0). Segue sem confirmação empírica.
- [x] **Três pendências fechadas como dispensáveis (02/08/2026), decisão do Davi:**
  - **Nenhum XMI-oráculo semeado é promovido para `resources/`.** Aquele diretório é a amarra com o experimento publicado e é imutável (`resources/README.md`); XMI nosso lá borraria a distinção que a fase usa como método. Os quatro ficam em `out/oraculo/`, regeneráveis por semente + imagem.
  - **Dono `root` dos XMIs do oráculo: não corrigir.** Arquivos legíveis, em `out/`, fora do git, regeneráveis.
  - **Sem segunda semente.** O gate não pede — a equivalência é estrutural, não estatística, e uma semente já deu zero divergência nas quatro escalas.

### Sakila — **descartado em 02/08/2026**

Levantamento do que existe publicado, antes de decidir:

| Repositório | Licença | Formato | Modelagem |
|---|---|---|---|
| `lilhuss26/sakila25` | **MIT** | dump `mongorestore`, 3 coleções, ~200 KB | aninhada (`films` com actors/categories, `customers` com address/payments) |
| `SouthbankSoftware/dbkoda-data` | nenhuma | dump BSON, 4,8 MB | aninhada (porte do Guy Harrison) |
| `Ciges/MongoDB_Sample_Databases` | nenhuma | `sakila.tar.bz2`, 345 KB | migração 1:1 do MySQL, plana |
| `vitorecarpe/Sakila-NoSQL` | nenhuma | CSV + script | aninhada; **é o único com Neo4j** |

- [x] **Decidido: não entra.** Existe versão MongoDB publicada e licenciada (`sakila25`, MIT), mas **em grafo não existe dataset nenhum** — o único candidato é um pipeline acadêmico que exige montar o Sakila no MySQL e converter, o que produziria um grafo **nosso**, não de terceiros. E o `sakila25` não é o Sakila clássico: é o esquema repovoado em 2025 com dados da API do TMDB.
- [x] **Limitação assumida, e ela é a mais séria da fase:** a validação de corretude usa **um único dataset real**, o Northwind — e só no paradigma documento. O grafo é validado **inteiramente sobre dado sintético** gerado por script nosso (`gen_userprofiles_neo4j.py`), com 9 arquétipos e nenhum nó multi-label, que é por que o `N1` nunca disparou. Consequências a declarar sem rodeio na 3.4:
  - o *overfitting* ao Northwind **não está descartado** no documento;
  - nenhuma corrida do grafo encontrou estrutura que não tenha sido desenhada por nós;
  - o que sustenta a generalização não é variedade de dataset, e sim a **variedade de caminhos**: dois paradigmas, dois núcleos de construção, duas origens de leitura no Northwind, e o confronto com o oráculo Java sobre a mesma instância.

**Saída:** CSV de equivalência cobrindo Northwind (dois caminhos de leitura) e User Profiles (4 escalas, grafo), com toda divergência fatal explicada por bug catalogado.

---

## 3.2 — Escala

Quatro tamanhos: 100k/200k/400k/800k `User` (50k/100k/200k/400k `Movie`).
**Rota A** com `_id` ObjectId nativo; **Rota B** com `_id` inteiro e ~15% de
arrays vazios (cenário relacional→NoSQL, que exercita #6 e #7).

> **Aviso sobre os números derivados desta seção.** Só valem como registrados os
> valores que estão **crus no CSV**: tempos por corrida, contagens, percentuais
> de captura, `linhas_tripla`, vereditos. Tudo que é **derivado** — as medianas
> entre sementes, os fatores de crescimento (18,0× · 15,3× · 26,3× · 5,25× ·
> 3,57× · 2,08×) e as razões porte/oráculo (1,8× a 8,9×) — foi calculado **ad
> hoc durante a sessão de 02/08/2026, sem script versionado**, e portanto não
> atende ao critério de rastreabilidade que a própria fase impõe.
>
> **A EDA do Davi sobre os CSVs é quem passa a valer.** Quando ela existir, os
> derivados abaixo são substituídos pelos dela; até lá, tratar como indicativos,
> não como resultado publicável.

- [x] Gerar os 4 tamanhos, rodar Mongo (A e B) e grafo, coletar CSV.
- [x] **Leitura integral** — fecha no grafo (100% em todas as corridas), **não** fecha no documento, e não deve: é o #8 replicado.
- [x] **Sem `OutOfMemoryError`/`MemoryError`** em nenhuma corrida, apesar de pura-Python nos 800k. Se um dia estourar, `mapPartitions` entra sem reescrever a lógica (o `reduce_pairs` é comutativo e associativo, provado na 2.0) e os testes novos levam `@pytest.mark.spark`.
- [x] **Extração domina a geração nas quatro escalas do grafo** — 6,18 vs 16,36s (`small`), 15,88 vs 36,78s (`medium`), 49,85 vs 120,34s (`large`), 173,41 vs 429,85s (`larger`). A afirmação do guia ("a geração custa mais") **não se sustenta**: a evidência que a sustentava vinha de um cronômetro que incluía apagar o grafo anterior, por causa do `--drop`. Hoje a limpeza é etapa própria, com coluna `t_limpeza`.
- [x] **`t_limpeza` de uma linha é o custo de apagar o grafo da linha anterior** — 2,58s (apagando `small`), 7,29s (`medium`), 26,47s (`large`), ~110s (`larger`, 10,2M arestas). Ler ao contrário inverte a conclusão.
- [x] **A Rota B é ~2× mais rápida que a A** (14,52 vs 30,07s no `larger`). O artigo também tem B mais rápida, mas por ~15%. Suspeita: o ObjectId da Rota A exige extrair `generation_time` e montar o agregado `{"$oid": …}` por documento.

### Documento — subcontagem do #8 por escala (semente 23)

| Rota | Escala | `t_extração` | Linhas de tripla | `User` capturado |
|---|---|---|---|---|
| **A** | small | 1,67s | 13 | 22.377 — 22,38% |
| | medium | 3,75s | 31 | 24.252 — 12,13% |
| | large | 10,01s | 111 | 21.867 — 5,47% |
| | larger | 30,07s | 421 | 20.988 — **2,62%** |
| **B** | small | 0,95s | 21 | 31.170 — **31,17%** |
| | medium | 2,10s | 43 | 42.154 — 21,08% |
| | large | 5,26s | 133 | 57.810 — 14,45% |
| | larger | 14,52s | 463 | 91.981 — 11,50% |

`Movie` capturou **100%** nas 24 corridas — é o controle interno. Análise em §3.3.

### Reprodutibilidade entre sementes (23, 69, 207)

**Os percentuais do #8 são reprodutíveis**: amplitude máxima de **0,4 ponto** e
`linhas_tripla` **idêntico** (13/31/111/421 na Rota A; 21/43/133/463 na B). O
que decide o resultado é a **ordem de leitura**, não o sorteio do dado.

| Rota | Escala | seed 23 | seed 69 | seed 207 |
|---|---|---|---|---|
| A | small | 22,38% | 22,00% | 22,35% |
| A | larger | 2,62% | 2,60% | 2,64% |
| B | small | 31,17% | 31,00% | 31,11% |
| B | larger | 11,50% | 11,47% | 11,53% |

**O tempo do documento também é firme:** a extração varia menos de **2%** entre
sementes em todas as oito combinações (Rota A `larger`: 30,07 / 30,29 / 30,51s).

### O tempo do grafo tem outliers esporádicos de 2–5× — usar mediana

Ao contrário do documento, a extração do grafo tem corridas isoladas muito
acima do modo, **sempre nas escalas menores**:

| escala | seed 23 | seed 69 | seed 207 | mediana |
|---|---|---|---|---|
| small | 16,36s | **25,31s** | 16,02s | 16,36s |
| medium | 36,78s | 36,72s | **148,69s** | 36,78s |
| large | **267,43s** | 120,34s | 118,95s | 120,34s |
| larger | 426,73s | 433,39s | 429,85s | **429,85s** |

- [x] **O `larger` é o mais reprodutível de todos** — dispersão de **0,8%** —, e são as escalas pequenas que sujam. Isso descarta "o volume torna a medida instável".
- [x] **A causa provável é trabalho de fundo do servidor após deleção massiva.** A corrida do oráculo semeado começou apagando um grafo de 800k (limpeza de **120,68s**) e teve `small` em 63,80s e `medium` em 184,77s — ~4× a mediana da bateria, nas duas escalas seguidas da deleção. O mesmo padrão explica os três outliers da tabela.
- [x] **Regra de leitura, e recomendação para quem medir de novo:** citar **mediana** de 3, nunca a média — o outlier arrasta a média. Numa medição futura, uma espera de estabilização entre a limpeza e o cronômetro (ou 5 sementes em vez de 3) tiraria o efeito na origem. Não é pendência desta fase: nenhuma corrida nova está prevista.

### Tendência: preservada em direção, **não** em fator de crescimento

Porte × oráculo sobre **a mesma instância** (semente 23). O `t_porte` é a
mediana das 3 sementes; o `t_oráculo` vem de `run_oracle_neo4j.py`.

| escala | oráculo (container) | porte (extração) | razão |
|---|---|---|---|
| small | 9,21s | 16,36s | 1,8× |
| medium | 13,04s | 36,78s | 2,8× |
| large | 23,27s | 120,34s | 5,2× |
| larger | **48,38s** | **429,85s** | **8,9×** |

- [x] **A razão porte/oráculo cresce com a escala — 1,8× a 8,9×.** Isso **descarta "Python é N vezes mais lento"** como explicação: fosse constante de linguagem, a razão não subiria.
- [x] **`t_oraculo` é relógio de parede do `docker run`**, não tempo de inferência: engole boot de Maven + JVM + Spark. Nesta sessão o custo fixo ficou visível — o `small` gastou 9,21s para 150k nós, quase tudo boot.
- [x] **Medido: o porte cresce mais que o oráculo nos dois paradigmas.**
  - **Documento:** Rota A cresce **18,0×** para 8× de dado (1,67 → 30,07s), contra 8,7× do oráculo; Rota B, **15,3×** contra 8,1×.
  - **Grafo:** o porte cresce **26,3×** para 8× de dado, contra **5,25×** do oráculo; em 2× de dado (`large`→`larger`), **3,57×** contra **2,08×** — o oráculo é praticamente linear, o porte não.
  - **Fato estrutural que restringe as explicações:** no documento o número de esquemas distintos cresce 13 → 421 (**32×**); no grafo são **9 arquétipos em todas as escalas**. Qualquer explicação única para os dois paradigmas esbarra nisso. **Interpretar é 3.4**, não aqui.
- [ ] **Assimetria a fechar: os números do oráculo no documento vêm do artigo, não desta máquina.** O `8,7×` e o `8,1×` acima são das tabelas publicadas — outro i9, medida que ninguém aqui reproduziu. É exatamente o confundidor que a corrida do grafo eliminou, e que no documento continuava de pé porque não existia bateria equivalente. **`scripts/run_oracle_mongo.py` foi escrito para fechar isso** (02/08) e **ainda não rodou**: o `--kind mongodb` do container só viu os 397 documentos do Northwind, na Fase 0.5, então o custo sobre 800 mil é desconhecido. Rodar pelas escalas menores primeiro.

**Saída:** CSV de escala completo + curva tempo × volume, porte vs. oráculo.

---

## 3.3 — Bugs: #6/#7 por construção, #8 replicado

| Bug | No oráculo | No porte | O que a fase mede |
|---|---|---|---|
| **#6** `_id` inteiro | corrigido por **patch** (`0006`) | corrigido **por construção** | roda os 800k da Rota B sem `TypeError` |
| **#7** array vazio | corrigido por **patch** (`0007`) | corrigido **por construção** | roda os ~15% de `[]` sem `IndexError` |
| **#8** subcontagem | **não corrigido** (não há patch `0008`) | **replicado fielmente** | a subcontagem do porte casa com a do oráculo |

- [x] **#6/#7 demonstrados em escala.** A Rota B rodou os quatro tamanhos, até 800.000 `User`, **sem exceção e sem patch**. A afirmação do TCC é sobre o **mecanismo**, não o resultado: os dois lados chegam ao mesmo modelo; muda como se chega.
- [x] **#8 — a faixa do experimento original foi reproduzida nas duas pontas:** **2,62%** (A/`larger`) e **31,17%** (B/`small`), contra os "~2,6%–31%" registrados. Intervalo inteiro, não aproximação.
- [x] **O achado que vale mais que o percentual:** na Rota A a massa capturada é praticamente **constante** — 22.377 → 24.252 → 21.867 → 20.988 — enquanto o volume real cresce 8×. O #8 não subconta proporcionalmente: **trava num teto quase fixo**, e o percentual só despenca porque o denominador cresce. Citar "captura 2,6%" sem dizer o tamanho é citar um artefato.
- [x] **O gatilho está isolado sem ambiguidade:** `Movie` captura 100% em todas as corridas, e a única diferença para `User` é o array de tamanho variável — o `ArraySC.__eq__` que ignora tamanho.
- [x] **A estrutura sai correta, só a contagem é comida:** `User` tem as 2 variações certas; no `up_a_larger`, 420 linhas de tripla colapsam nelas e sobrevive só o `count` da primeira de cada grupo (954 e 20.059).
- [x] **Decidido (02/08/2026): não entra dataset mínimo versionado.** O item pedia uma fixture nova para #6, #7 e #8. O **#8 sai** pela mesma razão que barrou o teste do Northwind (§3.1) — corrigi-lo é intenção declarada, e travar a subcontagem em CI viraria alarme falso no dia da correção. **#6 e #7 saem por redundância**: já estão travados nas duas camadas onde o defeito ocorre, e a fixture só acrescentaria a cola entre elas, que o `test_mintest_golden_master.py` já exercita.

| Bug | Onde já está travado |
|---|---|
| **#6** | `tests/regression/test_objectid.py::test_id_nao_objectid_infere_sem_estourar` (regressão portada do JUnit) e `tests/unit/test_extractors_mongo.py::test_generate_document_pair_id_nao_object_id_usa_timestamp_zero` — a camada de **extração**, que é onde o Java estourava |
| **#7** | `tests/unit/test_builder.py::test_feature_from_array_vazio_nao_estoura_bug_7` — e o dado do teste é o `privileges` do Northwind, hoje versionado em `resources/datasets/northwind/` |
| **#8** | `tests/unit/test_schema_inference.py` — cobertura existente, mantida como está |

- [x] **Regra observada: o #8 não foi "consertado" no meio da bateria.** Nenhuma das 24 corridas do documento fechou com o volume real — se tivesse fechado, seria sinal de que o porte divergiu do oráculo, a investigar como regressão. Não é mais pendência: as baterias acabaram.

**Saída:** tabela de contagens por bug, com #6/#7 rodando sem patch em escala e a subcontagem do #8 casada com a do oráculo.

---

## 3.4 — Coleta e análise

- [ ] **EDA sobre os CSVs — do Davi.** É ela que substitui os derivados calculados ad hoc em §3.2 (medianas entre sementes, fatores de crescimento, razões porte/oráculo) por números com script por trás.
- [ ] **Investigar a divergência de crescimento** (medida em §3.2, não explicada). As causas têm de ser diferentes por paradigma, porque o fato estrutural difere: no documento a variedade estrutural explode (13 → 421 esquemas distintos), no grafo é constante (9 arquétipos em todas as escalas). Duas hipóteses **não testadas**: (a) documento — o custo é linear em documentos × variedade estrutural, não em documentos; (b) grafo — o gargalo é o consumo de resultado por aresta no driver nativo (10,2M registros pelo bolt e pelo loop Python) contra o `countByValue` distribuído do Spark. É este item que o gate cobra como "declarado **e** investigado".
- [ ] Consolidar os CSVs no formato da 3.0.
- [ ] Visualizações: equivalência por dataset/paradigma; curva tempo × volume (porte vs. oráculo); contagens por bug.
- [ ] Redigir a avaliação: **corretude** (equivalência estrutural), **escala** (tendência), **correções por construção** (#6/#7 sem patch; #8 medido dos dois lados).
- [ ] **Escrever a investigação da tendência** — hoje está medida, com duas hipóteses distintas, e não redigida.
- [ ] Declarar as **limitações**: a corretude do documento repousa sobre **um único dataset real** (Sakila descartado — *overfitting* ao Northwind não descartado); a entrada do oráculo do Northwind não é publicada, só a saída (ver `resources/README.md`); os CSVs de evidência ficam fora do git, então o que sustenta os números é a prosa destes `.md` mais a regeneração por semente; o `$numberLong` não tem fixture-oráculo; a comparação é estrutural, não byte a byte.

---

## Housekeeping

- [x] `resources/README.md` — o item pedia corrigir a descrição de `movies_min.xmi` ("modelo mínimo Neo4j", quando é o User Profiles **Small**, 100.000 `User`) e listar os `up_*.xmi`. **Já estava feito**; o item é que estava desatualizado.
- [ ] **`run_scale_mongo.py` e `run_scale_neo4j.py` têm o buraco da guarda de cabeçalho:** ele só chega ao disco no primeiro `flush`, então uma corrida interrompida deixa um CSV de zero byte que a guarda recusa para sempre. Corrigido só no `run_oracle_neo4j.py` (arquivo vazio conta como novo + `flush` imediato); são duas linhas em cada.
- [ ] Documentos citados pelos guias de fase e ausentes do repo: `resultado_mongodb.md`, `resultado_neo4j.md`, `resultado_bug8_subcontagem_user.md`, `analise_ferramenta_uschema.md`. Recuperar ou remover as referências. **`roteiro_experimental.md` saiu da lista** — o que ele definia foi redefinido na §3.0.
- [x] **CSVs não serão versionados** (decisão de 02/08). `.gitignore` cobre `out/` e `results/`. Já custou uma vez: o CSV da bateria do grafo, apagado em 01/08, levou junto o respaldo da dispersão entre sementes.
- [x] **Saída separada por produtor:** `out/porte/`, `out/oraculo/`, `resources/` (versionado). Convenção em `resources/README.md`.
- [x] **Scripts em inglês** — `check_extraction_{mongo,neo4j}.py`, `check_northwind_invariants.py`. Seguem em português o diretório `results/` e os cabeçalhos dos CSVs; mudar agora invalidaria os arquivos já produzidos.
- [x] **`cli.py` não será criado** — decisão da 3.0, registrada no `CLAUDE.md`.

---

## Gate de aceite

- [x] **Corretude:** Northwind fecha pelos dois caminhos de leitura (`equivalent=True`, só não-fatais do #8, invariantes estruturais confirmados) e o grafo fecha nas 4 escalas contra o oráculo semeado com **zero divergências**. **Sakila descartado** — com a limitação declarada de que o documento fica com um dataset real só.
- [x] **Escala: 40 corridas numa sessão só** — 24 do documento (3 sementes × 2 rotas × 4 tamanhos), 12 do grafo (3 × 4) e 4 do oráculo semeado. Leitura integral no grafo em todas, subcontagem do documento reprodutível dentro de **0,4 ponto**, sem estouro de memória em nenhuma.
- [ ] **Tendência:** preservada em direção, **não** em fator de crescimento, nos dois paradigmas (documento 18,0× e grafo 26,3× para 8× de dado, contra 8,7× e 5,25× do oráculo). Medido em §3.2; **falta investigar**, e a investigação é item da **3.4** — o gate não fecha com "curva preservada" arredondado.
- [x] **Bugs #6/#7:** Rota B rodou os 4 tamanhos até 800k sem patch e sem exceção.
- [x] **Bug #8:** medido e casando com a subcontagem do oráculo (2,62%–31,17% no User Profiles, `Movie` a 100% como controle), e o **Northwind entrou na mesma planilha** — `comparacoes.csv`, pelos dois caminhos de leitura, com 14/17 coleções fechando nos dois. Nenhum número do documento fechou com o volume real, que é o que o gate exige.
- [~] **Rastreabilidade: todo número sai de uma corrida registrada** — vale para os valores crus. **Os derivados de §3.2 (medianas, fatores de crescimento, razões porte/oráculo) foram calculados ad hoc, sem script**, e só fecham quando a EDA sobre os CSVs existir. A sessão de 02/08 cobriu os dois paradigmas em escala, a cadeia porte × oráculo do grafo e o Northwind pelos dois caminhos de leitura — tudo do mesmo kernel; falta **regravar no formato novo** (ver o aviso no topo). **Exceção declarada:** os invariantes estruturais do Northwind (19/17, `Aggregate`) saem do `check_northwind_invariants.py`, que imprime e não escreve arquivo — são livres de contagem e reproduzíveis por um comando.

**Entregáveis:** `scripts/` (geradores + baterias), `results/` (CSVs), os gráficos e o material da avaliação experimental.

---

## Riscos

- **Afirmar número não medido** — os `.md` anteriores citam valores do experimento original, não do porte.
- **Citar número ordem-dependente como invariante** — aconteceu com as "15 divergências" do Northwind.
- **Comparar escalas diferentes sob o mesmo rótulo** — aconteceu com grafo `larger` × Northwind.
- **MongoDB não sobe em kernel ≥6.19.** O `mongod` 8.0.28 recusa iniciar (`SERVER-125742` só remove o guard para kernel **≥7.0.14**, e o apt não oferece nada nessa faixa). Contorno: bootar o **6.17.0-40-generic**. Docker **não** resolve — o container compartilha o kernel do host. A bateria exige kernel <6.19 **ou** MongoDB ≥8.0.30 com kernel ≥7.0.14.
- **Alvo do #8 conflitante com a fidelidade** — se passar batido, ou o gate de equivalência quebra ou se publica um número que o porte não produz.
- **Memória em pura-Python** nos 800k — perfil diferente do Spark; `mapPartitions` é a saída, não a reescrita.
- **Sakila descartado (02/08/2026)** — a corretude do documento fica com um dataset real só, o Northwind, e o *overfitting* a ele não está descartado. Deixa de ser risco em aberto e passa a ser limitação declarada.
- **`N1` (nós multi-label)** aparecendo pela primeira vez numa extração real — diagnosticar pelo `.java`, não pelo sintoma.
