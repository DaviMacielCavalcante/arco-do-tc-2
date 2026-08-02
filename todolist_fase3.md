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
| **3.1** corretude | Northwind e grafo fechados; **Sakila** é o único bloqueio externo |
| **3.2** escala | medido; falta investigar a divergência de tendência |
| **3.3** bugs | #6/#7 demonstrados; #8 medido; falta dataset mínimo em CI |
| **3.4** análise | não começou |

**Todos os números deste documento saíram de uma única sessão de medição**
(02/08, ~1h30, kernel **6.17.0-40**): `run_oracle_neo4j.py --seed 23` seguido de
`run_scale_suite.sh` com as sementes 23, 69 e 207. Nenhuma tabela mistura
ambientes.

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
| `run_scale_mongo.py` | bateria de escala do documento (2 rotas × 4 tamanhos) |
| `run_scale_neo4j.py` | bateria de escala do grafo (4 escalas), compara com `resources/` |
| `run_oracle_neo4j.py` | cadeia porte × **oráculo semeado**: regera, roda os dois lados sobre a mesma instância, compara |
| `run_scale_suite.sh` | encadeia N sementes nas duas baterias de escala, sequencialmente |
| `run_northwind.py` | corretude do Northwind pelos dois caminhos de leitura (arquivo e banco) |
| `check_northwind_invariants.py` | invariantes estruturais do Northwind, lidos do XMI |
| `gen_userprofiles{,_neo4j}.py` | geradores, ambos com `--seed` |
| `clean_databases.py` | apaga só os `up_*` e o grafo — nunca o `northwind` |

- [x] **Cronometragem em processo**, separando **extração** (I/O do driver) de **inferência+construção**. Resultado: nos dois paradigmas a inferência é ≤0,05s e **o custo é todo de extração** — o rótulo "tempo de inferência" do artigo mede, na prática, extração.
- [x] **Sem `cli.py`/`[project.scripts]`.** Um script por bateria com `argparse`. A entrega é a equivalência demonstrada, não uma ferramenta de linha de comando.
- [x] **Baterias não rodam em paralelo.** Os clientes Python não disputam, mas mongod e Neo4j disputam CPU e disco. No grafo nem cabe paralelismo: Community tem um banco só.
- [x] **Guarda de cabeçalho** nos CSVs: recusa anexar num arquivo de esquema antigo em vez de corromper em silêncio.

### Formato dos CSVs — fixado em 02/08/2026

`roteiro_experimental.md` §6–7, que definia o formato, **não existe neste
repositório**. O esquema abaixo passa a ser a referência.

| Arquivo | Colunas |
|---|---|
| `equivalencia.csv` | `dataset,paradigma,origem,semente,referencia,equivalente,n_divergencias,categoria,mensagem` — uma linha por divergência, ou uma de campos vazios quando deu zero |
| `oraculo_neo4j.csv` | uma linha por corrida, tempos dos dois lados e os dois vereditos (`equivalente_oraculo`, `equivalente_resources`) |
| `escala_mongo.csv`, `escala_neo4j.csv` | como as baterias já escreviam |

`origem` (`arquivo` ou `banco`), `semente` e `referencia` foram **acrescentados**
ao esquema do guia: sem eles a linha não é rastreável até a corrida, e o #8 é
sensível ao caminho de leitura — as duas linhas do Northwind seriam idênticas no
CSV e contraditórias entre si. `pico_memoria` **não** entra: nenhuma corrida
mediu isso, e coluna vazia num CSV de evidência é pior que coluna ausente.

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
4. **Bancos e saídas em sistemas de arquivos diferentes:** os bancos em `/var/lib/...` (ext4 no NVMe, sem cifra); o repositório, e portanto `out/` e `resultados/`, em `/home/davi`, que é **eCryptfs**. A extração mede I/O sem cifra; a escrita dos XMIs passa pela camada cifrada.
5. **Governor `powersave` com turbo ligado** — frequência não fixa. Mantido de propósito (medir a máquina como ela é usada), mas explica parte da dispersão entre sementes.
6. **A identidade da imagem do oráculo não precisa entrar no CSV:** o que determina o XMI é o fonte, pinado por SHA no `Dockerfile`. O único resíduo é a tag base `maven:3.9-eclipse-temurin-8`, que flutua e mexe marginalmente no `t_oraculo` — e as versões que ela entrega estão na tabela acima.

---

## 3.1 — Corretude

### Northwind — **fecha**

- [x] **`equivalent=True` pelos dois caminhos de leitura**, com só divergências não-fatais, todas na assinatura do #8. 17 coleções, 397 documentos, **49 linhas de tripla nos dois** (`scripts/run_northwind.py`, evidência em `resultados/equivalencia.csv`).
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
- [ ] Decidir se a **variação estrutural sobre o aninhado** (`fase3_validacao_escala.md:45`) entra no `check_northwind_invariants.py`.

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
- [ ] Decidir se algum XMI-oráculo semeado é **promovido** para `resources/`, com proveniência (semente, escala, SHA da imagem). Os quatro estão em `out/oraculo/`, fora do git.
- [ ] Os XMIs do oráculo saem com dono `root` (o container escreve como root no volume). Inócuo para leitura; `sudo chown` se atrapalhar.
- [ ] Repetir com uma segunda semente. Uma basta para o gate — a equivalência é estrutural, não estatística.

### Sakila — nada existe

- [ ] Obter o dataset (documento e/ou grafo). **Único bloqueio externo da fase.**
- [ ] Gerar o XMI-oráculo pelo Docker (`--db <nome> --kind mongodb|neo4j`), rodar o porte, comparar.
- [ ] Objetivo declarado: reduzir *overfitting* ao Northwind. Uma divergência **nova** aqui vale mais que a confirmação do que já se sabe.

**Saída:** CSV de equivalência cobrindo Northwind, User Profiles (4 escalas) e Sakila, com toda divergência fatal explicada por bug catalogado.

---

## 3.2 — Escala

Quatro tamanhos: 100k/200k/400k/800k `User` (50k/100k/200k/400k `Movie`).
**Rota A** com `_id` ObjectId nativo; **Rota B** com `_id` inteiro e ~15% de
arrays vazios (cenário relacional→NoSQL, que exercita #6 e #7).

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
- [ ] **Mitigar na próxima medição:** uma espera de estabilização entre a limpeza e o cronômetro, ou 5 sementes em vez de 3 para a mediana aguentar um outlier. **Enquanto isso, citar mediana de 3 e declarar os outliers** — nunca a média, que o outlier arrasta.

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
- [ ] **A divergência de crescimento tem causas diferentes por paradigma, e não se pode tratar como uma só.**
  - **Documento:** Rota A cresce **18,0×** para 8× de dado (1,67 → 30,07s), contra 8,7× do oráculo; Rota B, **15,3×** contra 8,1×. Hipótese: o número de esquemas distintos cresce 13 → 421 (**32×**), então o custo não é linear em documentos, é linear em documentos × variedade estrutural.
  - **Grafo:** o porte cresce **26,3×** para 8× de dado, contra **5,25×** do oráculo; em 2× de dado (`large`→`larger`), **3,57×** contra **2,08×** — o oráculo é praticamente linear, o porte não. Aqui a hipótese acima **não serve**: são 9 arquétipos em todas as escalas, variedade constante. O suspeito é o consumo de resultado por aresta no driver nativo (10,2M registros pelo bolt e pelo loop Python) contra o `countByValue` distribuído do Spark.

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
- [ ] **Dataset mínimo versionado — só para #6 e #7.** Eles estão corrigidos por construção, então travar o comportamento em CI protege uma correção, não um defeito. **O #8 fica de fora pela mesma razão que barrou o teste do Northwind** (§3.1): a intenção declarada é corrigi-lo no futuro, e uma fixture nova afirmando a subcontagem viraria alarme falso no dia da correção. A cobertura unitária que já existe (`test_objectid.py`, `test_builder.py`, `test_schema_inference.py`) permanece como está.
- [ ] **Não "consertar" o #8 no meio da bateria.** Se algum número do documento fechar com o volume real, o porte **divergiu** do oráculo — investigar como regressão.

**Saída:** tabela de contagens por bug, com #6/#7 rodando sem patch em escala e a subcontagem do #8 casada com a do oráculo.

---

## 3.4 — Coleta e análise

- [ ] Consolidar os CSVs no formato da 3.0.
- [ ] Visualizações: equivalência por dataset/paradigma; curva tempo × volume (porte vs. oráculo); contagens por bug.
- [ ] Redigir a avaliação: **corretude** (equivalência estrutural), **escala** (tendência), **correções por construção** (#6/#7 sem patch; #8 medido dos dois lados).
- [ ] **Escrever a investigação da tendência** — hoje está medida, com duas hipóteses distintas, e não redigida.
- [ ] Declarar as **limitações**: a entrada do oráculo do Northwind não é publicada, só a saída (ver `resources/README.md`); os CSVs de evidência ficam fora do git, então o que sustenta os números é a prosa destes `.md` mais a regeneração por semente; o `$numberLong` não tem fixture-oráculo; a comparação é estrutural, não byte a byte.

---

## Housekeeping

- [x] `resources/README.md` — o item pedia corrigir a descrição de `movies_min.xmi` ("modelo mínimo Neo4j", quando é o User Profiles **Small**, 100.000 `User`) e listar os `up_*.xmi`. **Já estava feito**; o item é que estava desatualizado.
- [ ] **`run_scale_mongo.py` e `run_scale_neo4j.py` têm o buraco da guarda de cabeçalho:** ele só chega ao disco no primeiro `flush`, então uma corrida interrompida deixa um CSV de zero byte que a guarda recusa para sempre. Corrigido só no `run_oracle_neo4j.py` (arquivo vazio conta como novo + `flush` imediato); são duas linhas em cada.
- [ ] Documentos citados pelos guias de fase e ausentes do repo: `resultado_mongodb.md`, `resultado_neo4j.md`, `resultado_bug8_subcontagem_user.md`, `analise_ferramenta_uschema.md`. Recuperar ou remover as referências. **`roteiro_experimental.md` saiu da lista** — o que ele definia foi redefinido na §3.0.
- [x] **CSVs não serão versionados** (decisão de 02/08). `.gitignore` cobre `out/` e `resultados/`. Já custou uma vez: o `escala_neo4j.csv` apagado em 01/08 levou junto o respaldo da dispersão entre sementes.
- [x] **Saída separada por produtor:** `out/porte/`, `out/oraculo/`, `resources/` (versionado). Convenção em `resources/README.md`.
- [x] **Scripts em inglês** — `check_extraction_{mongo,neo4j}.py`, `check_northwind_invariants.py`. Seguem em português o diretório `resultados/` e os cabeçalhos dos CSVs; mudar agora invalidaria os arquivos já produzidos.
- [x] **`cli.py` não será criado** — decisão da 3.0, registrada no `CLAUDE.md`.

---

## Gate de aceite

- [~] **Corretude:** Northwind fecha (`equivalent=True`, só não-fatais do #8, invariantes confirmados) e o grafo fecha nas 4 escalas contra o oráculo semeado com **zero divergências**. Falta o **Sakila**.
- [x] **Escala: 40 corridas numa sessão só** — 24 do documento (3 sementes × 2 rotas × 4 tamanhos), 12 do grafo (3 × 4) e 4 do oráculo semeado. Leitura integral no grafo em todas, subcontagem do documento reprodutível dentro de **0,4 ponto**, sem estouro de memória em nenhuma.
- [ ] **Tendência:** preservada em direção, **não** em fator de crescimento, nos dois paradigmas (documento 18,0× e grafo 26,3× para 8× de dado, contra 8,7× e 5,25× do oráculo). O gate só fecha se isso for declarado e investigado, não arredondado para "curva preservada".
- [x] **Bugs #6/#7:** Rota B rodou os 4 tamanhos até 800k sem patch e sem exceção.
- [ ] **Bug #8:** medido e casando com a subcontagem do oráculo (2,62%–31,17%, `Movie` a 100% como controle). Falta o Northwind entrar na mesma planilha.
- [x] **Rastreabilidade: todo número sai de uma corrida registrada.** Grafo (`oraculo_neo4j.csv`, `escala_neo4j.csv`), documento em escala (`escala_mongo.csv`), equivalência dos dois paradigmas (`equivalencia.csv`, 60 linhas: 32 do grafo + 27 do Northwind pelos dois caminhos). Tudo da mesma sessão e do mesmo kernel. **Exceção declarada:** os invariantes estruturais do Northwind (19/17, `Aggregate`) saem do `check_northwind_invariants.py`, que imprime e não escreve arquivo — são livres de contagem e reproduzíveis por um comando.

**Entregáveis:** `scripts/` (geradores + baterias), `resultados/` (CSVs), os gráficos e o material da avaliação experimental.

---

## Riscos

- **Afirmar número não medido** — os `.md` anteriores citam valores do experimento original, não do porte.
- **Citar número ordem-dependente como invariante** — aconteceu com as "15 divergências" do Northwind.
- **Comparar escalas diferentes sob o mesmo rótulo** — aconteceu com grafo `larger` × Northwind.
- **MongoDB não sobe em kernel ≥6.19.** O `mongod` 8.0.28 recusa iniciar (`SERVER-125742` só remove o guard para kernel **≥7.0.14**, e o apt não oferece nada nessa faixa). Contorno: bootar o **6.17.0-40-generic**. Docker **não** resolve — o container compartilha o kernel do host. A bateria exige kernel <6.19 **ou** MongoDB ≥8.0.30 com kernel ≥7.0.14.
- **Alvo do #8 conflitante com a fidelidade** — se passar batido, ou o gate de equivalência quebra ou se publica um número que o porte não produz.
- **Memória em pura-Python** nos 800k — perfil diferente do Spark; `mapPartitions` é a saída, não a reescrita.
- **Sakila indisponível** — sem ele a corretude do documento fica só no Northwind.
- **`N1` (nós multi-label)** aparecendo pela primeira vez numa extração real — diagnosticar pelo `.java`, não pelo sintoma.
