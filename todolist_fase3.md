# TO-DO — Fase 3: ponta a ponta + escala + correções por construção

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi Cavalcante · João — CESUPA
**Base:** `fase3_validacao_escala.md` · **Harness:** `validation/equivalence.py::compare` (Fase 0.3) · **Bugs:** `bugs_originais.md`
**Pré-requisito:** Fases 0, 1 e 2 (gates fechados; Northwind e os 4 XMIs Neo4j equivalentes ao oráculo)

> **Organização por entrega.** Tarefas agrupadas por **entregável** (3.0–3.4),
> não por autor. Cada bloco define uma **Saída** que serve de critério de
> "pronto".
>
> **Ideia central.** Esta fase não porta mais nada — ela **mede**. O produto é
> evidência: CSVs, curvas e tabelas que sustentam o capítulo de avaliação
> experimental do TCC. O código que entra é de **bateria** (orquestração,
> cronometragem, coleta), não de inferência.
>
> **Abrir o `.java` antes de afirmar** continua valendo (`~/Documents/GitHub/uschema{,-inference}`,
> commits pinados no `oracle/Dockerfile`). Mas o risco desta fase é outro:
> **afirmar número que não foi medido.** Todo valor do capítulo tem de sair de
> uma corrida registrada, não de um `.md` anterior.

---

## Correção da spec (já aplicada): **não há número-alvo "com a correção do #8"**

`fase3_validacao_escala.md` §3.3 listava o **#8** ao lado do #6/#7 como
"corrigido por construção" e fixava alvos *com a correção* (50/50 no User
Profiles; 17/17 no Northwind). **Contradizia a decisão de fidelidade do
projeto** — corrigido em 31/07/2026 no guia e em `scripts/README.md`.

Verificado:

- `bugs_originais.md` §#8 — **"Decisão no porte: replicar."** `combine_metadata` não é chamado no ponto de colapso, de propósito.
- `oracle/patches/` tem `0001`, `0004`(×2), `0005`, `0006`, `0007` — **não existe `0008`**. O oráculo também não corrige.
- `todolist_fase2.md` §2.3 — o Northwind fecha com `equivalent=True` e **só divergências não-fatais**, justamente a assinatura do #8 nos dois lados (a quantidade varia com a ordem de leitura — ver o achado de ordem-dependência em `bugs_originais.md` §#8).

**Regra da fase:** o critério é **casar com o oráculo**, não com o volume real.
O porte reproduz a subcontagem; a Fase 3 a **mede e documenta**, não a corrige.
Um resultado que "acertasse" o volume real no paradigma documento estaria
**fora** do gate.

O 50/50 e o 17/17 são resultados do experimento **original**, citáveis como
contexto do que o bug custa — nunca como alvo. Medir a correção exigiria uma
variante corrigida do pipeline, que **não entra nesta fase**.

---

## Achado: a maior lacuna herdada é o **Neo4j ponta a ponta** — e ela é fechável sem Docker

A 2.2 fechou com `compare()` zerado nos 4 XMIs, mas o teste
(`tests/datasets/test_movies_min_golden_master.py`, docstring) valida **só a
camada de construção**: os arquétipos foram **reconstruídos lendo a estrutura do
próprio XMI-oráculo**, não extraídos de um Neo4j real. A cadeia
`Neo4j real → extract → build → compare` nunca encontrou o oráculo.

**Isso é fechável agora**, e a Fase 2 até deixou as peças:

- `scripts/gen_userprofiles_neo4j.py` — o gerador **original** do dataset, localizado no clone Java e trazido pro repo.
- Os **4 XMIs-oráculo** estão versionados em `resources/neo4j/`.

**Verificado hoje** (contagens lidas dos próprios XMIs) — os quatro são o mesmo
dataset em escalas que **dobram exatamente**:

| XMI | `User` (soma das 5 variações) | `Movie` | Escala |
|---|---|---|---|
| `movies_min.xmi` | **100.000** | 50.000 | Small |
| `up_medium.xmi` | **200.000** | 100.000 | Medium |
| `up_large.xmi` | **400.000** | 200.000 | Large |
| `up_larger.xmi` | **800.000** | 400.000 | Larger |

Dois corolários:

1. **`movies_min.xmi` não é um "modelo mínimo"** — é o User Profiles **Small**. `resources/README.md` o descreve errado e nem lista os `up_*.xmi`. Corrigir.
2. **A soma dos `count` de `User` já bate o volume gerado no próprio oráculo** (o caminho grafo tem núcleo próprio, o #8 não passa por ele). Ou seja: a bateria de escala do grafo e o gate de corretude do grafo são **a mesma corrida**.

---

## Cadeia de desbloqueio

```text
Fases 1+2 ─→ 3.0 (infra de bateria: cronometragem + coleta) ─┬─→ 3.1 corretude ─┬─→ 3.4 análise
                                                                ├─→ 3.2 escala ────┤
                                                                └─→ 3.3 bugs ──────┘
```

| Etapa | Depende de | Libera | Bloqueio conhecido |
|---|---|---|---|
| **3.0** infra de bateria | — | 3.1, 3.2, 3.3 | nenhum |
| **3.1** corretude | 3.0 | 3.4 | Sakila: dataset não está no repo |
| **3.2** escala | 3.0 | 3.4 | nenhum — os 8 bancos `up_*` já estão materializados |
| **3.3** bugs | 3.0, 3.2 | 3.4 | nenhum — o #8 é medido, não corrigido (acima) |
| **3.4** análise | 3.1–3.3 | capítulo | formato dos CSVs a redefinir (doc ausente) |

---

## 3.0 — Infra de bateria (não estava no guia)

> O guia assume "ler o tempo de inferência do log do Spark". **Não existe log
> de executor** — a 2.0 decidiu driver nativo, pura-Python. A medição tem de
> ser em processo.

- [x] **Cronometragem em processo**, separando as duas metades que o artigo trata como uma: **extração** (I/O do driver) e **inferência+construção** (`BuildUSchema` / `build_uschema_from_archetypes`). Feito e já rendeu resultado: nos dois paradigmas a inferência é desprezível (≤0,05s) e **o custo é todo de extração** — o rótulo "tempo de inferência" do artigo mede, na prática, extração.
- [ ] **Entry-point das baterias.** **Recomendação: um script por bateria em `scripts/`, com `argparse`, no mesmo padrão dos `verificar_extracao_*.py`** — e **não** criar `cli.py`/`[project.scripts]` agora. Motivo: a entrega do TCC é a equivalência demonstrada, não uma ferramenta de linha de comando; um CLI genérico adiciona superfície (subcomandos, validação de config, testes) que nenhuma tarefa desta fase exige. A dívida do `cli.py` fica registrada no `CLAUDE.md`, sem dono.
- [ ] **Formato de saída fixado antes da primeira corrida**: um CSV de escala (`dataset,paradigma,rota,tamanho,t_extracao,t_inferencia,soma_counts,volume_gerado,pico_memoria`) e um de equivalência (`dataset,paradigma,equivalente,n_divergencias,categoria,mensagem`). `roteiro_experimental.md` §6–7 — que definia esse formato — **não existe neste repositório** (nem em nenhum outro no disco); ou o documento é recuperado, ou o formato é redefinido aqui e vira a referência.
- [x] Artefatos: CSVs em `resultados/` (`escala_mongo.csv` pronto), XMIs gerados em `out/` — **fora** do git (grandes e reprodutíveis). Falta a regra de `out/` no `.gitignore`.
- [x] **Baterias consolidadas em `scripts/`** (31/07/2026): `run_scale_mongo.py` e `run_scale_neo4j.py`, com `argparse`, `--seed` obrigatório, CSV em append e **guarda de cabeçalho** (recusa anexar num CSV de esquema antigo em vez de corromper silenciosamente). `scripts/run_scale_suite.sh` encadeia N sementes nas duas, **sequencialmente**.
- [x] **Decidido: baterias não rodam em paralelo.** Os clientes Python não disputam (single-thread, 32 threads na máquina), mas mongod e Neo4j disputam CPU e disco — e os tempos medidos vão para o capítulo. Ganho seria ~25-30% de relógio; o custo seria medir sob carga variável do outro paradigma. Dentro de uma bateria o grafo nem admite paralelismo: Community tem um banco só.
- [ ] Decidir a máquina de referência e registrá-la (o baseline do artigo é um i9; comparar **tendência**, nunca tempo absoluto).

**Saída:** script(s) de bateria com medição em processo e esquema de CSV congelado.

---

## 3.1 — Corretude (datasets reais)

### Northwind — herdado da 2.3 e re-executado em 31/07/2026

- [x] `compare()` contra `model_northwind.xmi`: **`equivalent=True`, só divergências não-fatais** (todas na assinatura do #8), re-executado contra um MongoDB local real (17 coleções, 397 documentos, 49 linhas de tripla; extração 0,00s, inferência 0,17s).
- [x] **Achado: a quantidade de divergências é ordem-dependente** — 15 lendo os arquivos, **12** lendo o cursor do Mongo, mesmo dado. Invariante citável: `equivalent=True` + não-fatais + **14/17** coleções fechando (falham `orders` 48→38, `products` 45→40, `purchase_orders` 28→23). Detalhe e evidência em `bugs_originais.md` §#8.
- [ ] **Reprodutibilidade.** Hoje o resultado é prosa: os JSONs não foram vendorizados (decisão registrada), então nada trava esse número em CI. Os dados estão em `~/Documents/GitHub/mongodb-northwind` (2,1 MB, 17 arquivos). **Recomendação: vendorizar** — 2,1 MB é barato perto de um número que sustenta o gate da fase, e sem isso o capítulo cita um resultado que ninguém re-executa. Se a decisão de não vendorizar for mantida, então **um script de carga** (`scripts/carregar_northwind.py`) com o SHA dos arquivos é o mínimo.
- [ ] Confirmar os invariantes que o guia lista: **19 `EntityType`** (17 raiz + `_id` + `Detail`), `Detail` ligada a `Orders`/`Purchase_orders` por `Aggregate` (`upperBound="-1"`, `optional="true"`).

### Neo4j / User Profiles — **lacuna fechada em 31/07/2026 (escala Larger)**

- [x] Dataset **já materializado** no Neo4j local: 800.000 `User` + 400.000 `Movie`, 10,2M arestas `WATCHED`/`FAVORITE`, 120.109 users isolados (15,01%), zero nós multi-label. Confere com `gen_userprofiles_neo4j.py --size larger`, então não foi preciso regerar.
- [x] Cadeia **real** rodada: `extract_database_archetype_counts` (banco de verdade, bolt) → `build_uschema_from_archetypes` → `compare()` contra `up_larger.xmi`. **Resultado: `equivalent=True`, ZERO divergências**, `soma User = 800.000` exata (leitura integral confirmada).
- [x] **Isto é o que a 2.2 não fez** — lá os arquétipos vieram do próprio XMI. Aqui vieram do banco: primeiro confronto da camada de **extração** do grafo com o oráculo, e passou limpo.
- [x] Tempos: **extração 414,07s, inferência 0,00s**, 9 arquétipos. A redução acontece dentro da extração (10,2M arestas → 9 arquétipos), então a construção é instantânea — no grafo, "tempo de inferência" é essencialmente tempo de extração.
- [x] **`N1` não disparou** e não podia: o dataset não tem nó multi-label (verificado, `size(labels(n)) > 1` = 0). Segue sem confirmação empírica — se um dataset multi-label aparecer, é ali que testa.
- [x] **Repetido nas escalas `small`/`medium`/`large`** contra `movies_min`/`up_medium`/`up_large.xmi`: `equivalent=True` nas três, `User` e `Movie` a **100%**, **9 arquétipos** em todas as quatro escalas (a estrutura não muda com o volume). Cada uma com **7 divergências não-fatais**, todas de `count` — ver o achado abaixo.
- [x] **Achado (confirmado por experimento em 01/08/2026, ver §3.1): as 7 divergências são ruído de amostragem, não defeito — o gerador não tinha semente.** `gen_userprofiles_neo4j.py:196,207` usa `random.random() < EMPTY_FRACTION` para sortear usuários isolados e favoritos, e **não há `random.seed` no arquivo**. Regerar o dataset produz um sorteio **novo**, então as contagens por variação divergem do XMI-oráculo, que foi construído sobre uma instância específica. Três evidências de que é isso:
  1. os **totais** batem exatos (`User` 100%, `Movie` 100%) — o gerador cria exatamente N nós, isso é determinístico; só a **divisão entre as 5 variações** varia, e é ela que depende do sorteio;
  2. as diferenças são pequenas e do tamanho certo — na escala `large`, σ ≈ √(400000 × 0,15 × 0,85) ≈ **226**, e a maior diferença observada foi **322** (~1,4σ);
  3. o `larger`, que **não** foi regerado (o grafo já estava no banco), fechou com **zero** divergências — é a instância original que gerou o `up_larger.xmi`.
- [x] **`--seed` adicionado aos dois geradores** (31/07/2026). `gen_userprofiles.py` (documento) foi trazido do `teste_uschema` para `scripts/`, tipado e com docstrings NumPy. **Os XMIs-oráculo em `resources/` continuam de semente desconhecida** — foram gerados antes disso, então a instância original não é reconstruível. A partir daqui, é.
- [x] **A instância original do `larger` foi destruída** ao regerar as escalas menores (Community = um banco só). O resultado está preservado em `out/neo4j_up_larger.xmi` e no CSV, mas regerar `larger` agora daria um sorteio novo, com o mesmo tipo de divergência das outras três. Foi por isso que a ordem decrescente importava.

### Oráculo semeado — fechar as 7 divergências do grafo (01/08/2026, em andamento)

As 7 não-fatais persistem porque os XMIs de `resources/neo4j/` vieram de uma
instância de **semente desconhecida**. Agora que o gerador tem `--seed` e o
Docker está operante, dá para rodar o **oráculo Java sobre o nosso grafo
semeado** e obter um XMI que casa exatamente — mesma entrada, duas
implementações, que é o que a afirmação de equivalência quer dizer.

- [x] **Achado que destrava o Community** (lido no `Neo4j2USchema.java` do SHA pinado): o `databaseName` passado por `--db` **não é usado para conectar**. O `SparkProcess` recebe só `(samplingRatio, bolt, user, password)`; o nome vai apenas para `Json2USchemaModel(databaseName)`, ou seja, é o **nome do schema** no modelo (e o nome do arquivo de saída). O conector sempre lê o banco padrão. Um único banco de usuário, portanto, **não** é obstáculo.
- [x] **O `--db` tem de casar com o nome que o porte usa** (`ORACULO[escala]`: `movies_min`, `up_medium`, …). Divergência de `SCHEMA_NAME` é **fatal** no harness (ver a memória da 0.3), então errar isso reprova a corrida por um motivo que não é o que se quer medir.
- [x] `DATABASE_BOLT` é constante (`bolt://localhost:7687`), daí o `--network=host` já documentado no `oracle/README.md`.
- [x] Grafo `small` regerado com `--seed 23`: `WATCHED=169796 FAVORITE=72361`, **idênticos** aos da semente 23 na bateria — a reprodutibilidade da semente está demonstrada, não só prometida.
- [x] XMI do porte gerado (`out/porte/neo4j_movies_min_seed23.xmi`): 9 arquétipos, `User` 5 variações somando 100.000, `Movie` 1 somando 50.000.
- [x] **FECHADO em 01/08/2026, escala `small`: `equivalent=True`, ZERO divergências.** Imagem `extrator-uschema` buildada, container rodado com `--network=host --memory=6g -v "$PWD/out/oraculo:/output" --db movies_min --kind neo4j` sobre o grafo semeado (seed 23). Oráculo e porte produzem `User` com 5 variações somando 100.000 e `Movie` com 1 somando 50.000 — idênticos.
- [x] **Isto prova que as 7 divergências nunca foram defeito do porte.** Contra `resources/` sobravam 7 não-fatais; contra o oráculo rodado sobre **a mesma instância**, zero. A variável isolada é o dataset, não a implementação:

| Comparação | Entrada | Resultado |
|---|---|---|
| porte × `resources/neo4j/` | dados diferentes (semente nossa × instância dos autores) | `equivalent=True`, 7 não-fatais |
| **porte × oráculo semeado** | **mesma instância** | **`equivalent=True`, 0 divergências** |

- [x] **Três coisas inéditas que a corrida também estabeleceu:** o `--kind neo4j` do container funcionou contra **150k nós** (a 0.5 só o tinha exercitado em grafo mínimo); o `--network=host` alcançou o Neo4j do host; e o `--db movies_min` como nome de schema bateu com o do porte, evitando o `SCHEMA_NAME` fatal.
- [x] **Primeiro ponto de desempenho sobre entrada idêntica:** oráculo **6,0s** contra **13,66s** do porte na mesma extração — sem o confundidor de datasets diferentes que a bateria tinha.
- [ ] Repetir nas escalas `medium`/`large`/`larger`. O `larger` custa ~200s de geração mais o Spark sobre 10,2M arestas.
- [ ] **Confirmar que o container aguenta o `larger`.** A corrida que fechou foi o `small` — 150k nós e 242k arestas, 6s de Spark. O `larger` tem **10,2M arestas**, ~42x mais, e o `--memory=6g` do `oracle/README.md` nunca foi exercitado nessa faixa. Se estourar, subir o limite antes de concluir qualquer coisa sobre o oráculo.
- [ ] Decidir se algum XMI-oráculo semeado é **promovido** para `resources/` (com proveniência: semente, escala, SHA da imagem). Ver `resources/README.md`, "Onde cada XMI mora".
- [ ] O XMI sai com dono `root` (o container escreve como root no volume montado). Inócuo para leitura; `sudo chown` se atrapalhar.
- [ ] **O que é inédito aqui é o volume, não o caminho.** A Fase 0.5 já rodou `--kind neo4j` ponta a ponta (`oracle/README.md`, checklist), mas contra um grafo mínimo criado por `cypher-shell`. Rodar contra 100k–800k nós é que nunca aconteceu — fricção de memória/tempo é o risco, não a integração.
- [ ] Se fechar, repetir nas outras três escalas e decidir se algum XMI-oráculo semeado é **promovido** para `resources/` (com proveniência: semente, escala, SHA da imagem). Ver `resources/README.md`, "Onde cada XMI mora".

### Sakila — segundo ponto de corretude, nada existe

- [ ] Obter o dataset (documento e/ou grafo). **É o único bloqueio externo da fase.**
- [ ] Gerar o XMI-oráculo pelo Docker: `oracle/entrypoint.sh --db <nome> --kind mongodb|neo4j`, com `MONGO_URL`/`MONGO_COLLECTIONS` no ambiente. O caminho está provado (Fase 0.5 regenera os XMIs de forma reproduzível).
- [ ] Rodar o porte e comparar. Objetivo declarado: reduzir *overfitting* ao Northwind — uma divergência **nova** aqui vale mais que a confirmação do que já se sabe.

**Saída:** CSV de equivalência cobrindo Northwind, User Profiles (4 escalas, grafo) e Sakila, com toda divergência fatal explicada por bug catalogado.

---

## 3.2 — Escala (datasets sintéticos)

- [ ] **Trazer `scripts/gen_userprofiles.py`** (MongoDB, Rotas A/B). **Localizado em 31/07/2026**: está em `~/Documents/teste_uschema/gen_userprofiles.py` (repo próprio, autoria do Davi), não no clone Java — a busca anterior falhou porque procurou no lugar errado. Custo de trazer: type hints + docstrings NumPy (o `mypy --strict`/`ruff` cobre `scripts/`), trocar a instrução `pip3` por `uv` e apagar a linha que manda cronometrar pelo log do Spark. **Não bloqueia mais a bateria** (ver abaixo), mas o capítulo precisa dele para que outra pessoa consiga regerar.
- [x] Gerar os 4 tamanhos: **100k/200k/400k/800k `User`** (50k/100k/200k/400k `Movie`). **Já materializados** no MongoDB local — 8 bancos `up_{a,b}_{small,medium,large,larger}`, contagens conferidas.
  - **Rota A**: `_id` ObjectId nativo.
  - **Rota B**: `_id` **inteiro** + ~15% arrays vazios (cenário relacional→NoSQL; é o que exercita #6 e #7).
- [ ] Rodar Mongo (A e B) e grafo nos 4 tamanhos, coletando o CSV da 3.0. **Parcial:** `up_a_larger` e o grafo `larger` feitos (abaixo); faltam as 7 corridas restantes do Mongo e as 3 do grafo.
- [ ] **Leitura integral**: soma dos `count` == volume gerado. No paradigma **documento** isso **não vai fechar, e não deve** — é exatamente o #8, replicado (ver 3.3). No **grafo** fecha (núcleo próprio; verificado nos 4 XMIs-oráculo).
- [ ] Comparar a **tendência** de crescimento com a do oráculo, não o tempo absoluto. Referência i9 (ferramenta original): Mongo Rota A ~0,47→4,09 s; Rota B ~0,43→3,48 s; Neo4j inferência ~3,83→34,86 s.
- [ ] Registrar que a **geração** do grafo (~180 s no maior) custa mais que a inferência — assimetria do paradigma, é resultado, não problema.
- [ ] Sem `OutOfMemoryError` / `MemoryError`. **Risco novo do porte:** sendo pura-Python, os 800k passam por estruturas em memória do processo, não por executores Spark — o perfil de memória é **diferente** do oráculo. Se estourar, `mapPartitions` entra sem reescrever a lógica (o `reduce_pairs` é comutativo e associativo, provado na 2.0) — e aí os testes novos levam `@pytest.mark.spark`, fechando o item pendente da 2.0.

### Bateria do MongoDB medida (31/07/2026) — `resultados/escala_mongo.csv`

As 8 corridas (2 rotas × 4 tamanhos). `t_inferência` ficou ≤ 0,05s em todas —
**o custo é todo de extração**.

| Rota | Escala | `t_extração` | Linhas de tripla | `User` capturado |
|---|---|---|---|---|
| **A** | small | 1,60s | 13 | 22.168 — 22,17% |
| | medium | 3,73s | 31 | 24.074 — 12,04% |
| | large | 10,08s | 111 | 21.789 — 5,45% |
| | larger | 30,91s | 421 | 21.013 — **2,63%** |
| **B** | small | 0,98s | 21 | 31.280 — **31,28%** |
| | medium | 2,13s | 43 | 42.220 — 21,11% |
| | large | 5,33s | 133 | 58.317 — 14,58% |
| | larger | 14,70s | 463 | 91.468 — 11,43% |

`Movie` capturou **100%** nas oito. Ver a análise do #8 em 3.3.

### Bateria de 3 sementes (23, 69, 207) — 31/07/2026, ~58 min

Rodada por `scripts/run_scale_suite.sh`, sequencial, 24 corridas
(3 sementes × [8 do Mongo + 4 do grafo]).

**O resultado que mais importa: os percentuais do #8 são reprodutíveis.**
Amplitude máxima entre sementes de **1,7%**, e `linhas_tripla` **idêntico**
(13/31/111/421 na Rota A). Ver a análise em `bugs_originais.md` §#8 — o que
decide o resultado é a **ordem de leitura**, não o sorteio do dado.

| Rota | Escala | seed 23 | seed 69 | seed 207 |
|---|---|---|---|---|
| A | small | 22,4% | 22,0% | 22,4% |
| A | larger | 2,6% | 2,6% | 2,6% |
| B | small | 31,2% | 31,0% | 31,1% |
| B | larger | 11,5% | 11,5% | 11,5% |

- [x] **A superlinearidade se confirma nas três sementes, mas com precisão bem diferente por paradigma.** Fator de crescimento da extração, `small` → `larger`:

| Paradigma | seed 23 | seed 69 | seed 207 | Oráculo |
|---|---|---|---|---|
| Mongo (Rota A) | 19,1x | 19,4x | 19,5x | 8,7x |
| Neo4j | 24,8x | 29,7x | 33,6x | 9,1x |

  No **documento** a medida é firme (dispersão < 2%) e a conclusão é sólida. No
  **grafo** a dispersão é de **35%** — provável trabalho de fundo do servidor
  logo após as deleções massivas. **O capítulo tem de citar o grafo como faixa
  (25x–34x), não como ponto**, e declarar essa diferença de precisão.

- [x] **Defeito de medição encontrado e corrigido:** o `t_geracao` da
  primeira escala de cada semente vinha inflado (`small` em **7,60s** na semente
  23 contra **127,43s** na 69 e **126,64s** na 207). O gerador rodava com
  `--drop`, então o cronômetro incluía **apagar o grafo `larger` da semente
  anterior** — ~120s para 10,2M arestas, não geração. Corrigido em
  `run_scale_neo4j.py`: a limpeza virou etapa separada, com coluna `t_limpeza`
  própria (o custo de deleção é dado sobre o paradigma, não ruído). **As duas
  linhas afetadas do CSV atual** (`small` das sementes 69 e 207) devem ser
  descartadas na análise; as outras 22 são válidas.

### Primeira corrida do Neo4j, sem semente (31/07/2026) — superada pela bateria acima

Mantida como registro do que ela estabeleceu **antes** de haver semente. As 4
escalas, **9 arquétipos em todas** (a estrutura não muda com o volume) e
`User`/`Movie` a **100%** nas quatro — o grafo tem núcleo próprio, o #8 não
passa por lá. Esses achados estruturais seguem válidos; os **tempos** foram
substituídos pelos das 3 sementes.

| Escala | `t_geração` | `t_extração` | Divergências | `User` |
|---|---|---|---|---|
| small (100k) | 13,47s | 16,29s | 7 não-fatais | 100.000 — 100% |
| medium (200k) | 44,73s | 43,71s | 7 não-fatais | 200.000 — 100% |
| large (400k) | 176,95s | 123,05s | 7 não-fatais | 400.000 — 100% |
| larger (800k) | — (já carregado) | 414,07s | **0** | 800.000 — 100% |

- [x] **`equivalent=True` nas quatro**, e nas 12 corridas com semente também.
- [x] **As 7 não-fatais persistem mesmo com semente**, como previsto: os XMIs-oráculo vieram de uma instância de **semente desconhecida**, então nenhuma semente nossa alinha com eles. A semente tornou o resultado determinístico por corrida, não idêntico ao oráculo. O único zero foi o `larger` desta corrida — a instância original, hoje destruída. **Resolvido em 01/08/2026 pelo oráculo semeado** (§3.1): com a mesma instância nos dois lados, dá zero.
- [x] **Corridas com as 7 divergências apagadas** (01/08/2026, a pedido): `resultados/escala_neo4j.csv` e os quatro `out/porte/neo4j_up_*.xmi`/`neo4j_movies_min.xmi`. O CSV precisava sair de qualquer forma — tinha o **cabeçalho antigo** (sem `t_limpeza`) e as duas linhas contaminadas do `small`, então a bateria corrigida se recusaria a anexar nele. **Consequência a fechar: os tempos do grafo citados abaixo e em §3.2 não têm mais CSV de respaldo** até a bateria ser re-executada; as sementes (23, 69, 207) estão registradas, então é reprodutível.
- [x] **"A geração custa mais que a inferência" é dependente de escala.** No `large` a geração domina (176,95 vs 123,05s), mas no `small` a **extração** custa mais (16,29 vs 13,47s). O guia afirmava o primeiro como se fosse geral — corrigido.

- [x] **Comparação de mesma escala, `larger` nos dois paradigmas** (800k `User` / 400k `Movie`): grafo **414,07s** de extração contra **30,91s** do documento (Rota A) — o grafo custa **13,6×**. No i9 original a razão foi 34,86 / 4,09 = **8,5×**: mesma direção, mesma ordem de grandeza. Overhead Python×JVM coerente entre os dois: **7,6×** no Mongo (30,91 vs 4,09) e **11,9×** no Neo4j (414,07 vs 34,86).
- [x] **Onde o tempo mora difere por paradigma.** No grafo a redução acontece dentro da extração (10,2M arestas → 9 arquétipos), então a inferência é ~0. Rotular os dois como "tempo de inferência", como o artigo faz, esconde isso — daí os dois cronômetros separados.
- [x] **A Rota B é ~2× mais rápida que a A** (14,70 vs 30,91 no larger). O artigo também tem B mais rápida, mas por ~15% (3,48 vs 4,09). Direção igual, magnitude maior — suspeita: o `_id` ObjectId da Rota A exige extrair `generation_time` e montar o agregado `{"$oid": …}` por documento.
- [ ] **A tendência se preserva em direção, mas NÃO em fator de crescimento.** Rota A: 1,60 → 30,91s = **19,3×** para 8× de dado (superlinear). O oráculo foi 0,47 → 4,09 = **8,7×**, quase linear. Rota B: **15,0×** contra 8,1× do oráculo. **Isto é uma divergência medida e tem de entrar no capítulo como tal**, não ser diluída em "a curva se preserva". Hipótese a investigar: o número de esquemas distintos cresce 13 → 421 (**32×**) na Rota A, então o agrupamento por chave canônica faz mais trabalho por documento conforme a escala sobe — o custo não é linear no número de documentos, é linear no produto documentos × variedade estrutural.
- [ ] **Não comparar escalas diferentes.** Esta sessão chegou a contrastar o grafo `larger` (800k) com o Northwind (397 documentos) e produziu conclusão sem sentido. Todo par de números do capítulo declara dataset **e** tamanho.

- [ ] **Re-executar a bateria do grafo para restaurar o respaldo em CSV.** O `resultados/escala_neo4j.csv` foi apagado em 01/08/2026 (cabeçalho antigo, sem `t_limpeza`, e as duas linhas contaminadas do `small`). Até isso rodar, **os tempos do grafo citados neste documento não têm CSV por trás** — só a prosa. As sementes (23, 69, 207) estão registradas, então é reprodutível; são ~45 min.

**Saída:** CSV de escala completo (3 baterias × 4 tamanhos) + a curva tempo × volume, porte vs. oráculo.

---

## 3.3 — Bugs: #6/#7 por construção, #8 replicado

| Bug | No oráculo | No porte | O que a fase mede |
|---|---|---|---|
| **#6** `_id` inteiro | corrigido por **patch** (`0006`) | corrigido **por construção** | roda os 800k da Rota B sem `ClassCastException`/`TypeError` |
| **#7** array vazio | corrigido por **patch** (`0007`) | corrigido **por construção** | roda os ~15% de `[]` sem `IndexError` |
| **#8** subcontagem | **não corrigido** (não há patch `0008`) | **replicado fielmente** | a subcontagem do porte casa com a do oráculo |

- [x] **#6/#7 — demonstrados em escala (31/07/2026).** A **Rota B** (`_id` **inteiro** + ~15% de arrays vazios) rodou os **quatro** tamanhos, até 800.000 `User`, **sem nenhuma exceção e sem nenhum patch**. No Java esses dois casos exigiram os patches `0006`/`0007`; aqui não existe patch a aplicar. **A afirmação do TCC é sobre o mecanismo, não o resultado** — os dois lados chegam ao mesmo modelo; o que muda é como se chega.
- [ ] Testes de regressão com dataset mínimo dedicado para #6, #7 e #8. Os três já têm cobertura unitária (`test_objectid.py` para #6, `test_builder.py` para #7, `test_schema_inference.py` para #8) e agora confirmação em escala — o que falta é o **dataset mínimo versionado** que trave isso em CI.
- [x] **#8 — subcontagem medida nos 4 tamanhos × 2 rotas** (`resultados/escala_mongo.csv`; tabela completa em 3.2 e análise em `bugs_originais.md` §#8).
  - [x] **A faixa do experimento original foi reproduzida nas duas pontas:** **2,63%** (A/larger) e **31,28%** (B/small), contra os "~2,6%–31%" registrados. Intervalo inteiro, não aproximação.
  - [x] **O achado que vale mais que o percentual:** na Rota A a massa capturada é praticamente **constante** — 22.168 → 24.074 → 21.789 → 21.013 — enquanto o volume real cresce **8×**. O #8 não subconta proporcionalmente: ele **trava num teto quase fixo**, e o percentual só despenca porque o denominador cresce. Citar "captura 2,6%" sem dizer o tamanho é citar um artefato.
  - [x] **Controle interno em todas as 8 corridas:** `Movie` capturou **100%**. A única diferença para `User` é o array de tamanho variável — isolando o gatilho no `ArraySC.__eq__` que ignora tamanho, sem ambiguidade.
  - [x] **A estrutura sai correta, só a contagem é comida:** `User` tem as 2 variações certas (o gerador liga `postcode` e `surname`+`favoritos` no mesmo `i % 2`). No `up_a_larger`, 420 linhas de tripla colapsam nelas e sobrevive só o `count` da primeira de cada grupo (954 e 20.059).
  - [x] **Corrigido: estes percentuais NÃO são uma amostra — são reprodutíveis.** A versão anterior deste item advertia o contrário. A bateria de 3 sementes reproduziu cada valor dentro de **1,7% no pior caso**, com `linhas_tripla` idêntico. O enunciado certo: o #8 depende da **ordem de leitura**, não do sorteio do dado — por isso o Northwind muda (15 vs 12, ordem diferente) e o User Profiles não muda (3 sementes, mesma ordem de inserção). Os percentuais são citáveis; o que precisa vir declarado junto é o **caminho de extração**.
- [ ] **Não "consertar" o #8 no meio da bateria.** Se algum número do paradigma documento fechar com o volume real, isso é sinal de que o porte **divergiu** do oráculo — investigar como regressão, não comemorar.

**Saída:** tabela de contagens por bug, com #6/#7 rodando sem patch em escala e a subcontagem do #8 medida e casada com a do oráculo.

---

## 3.4 — Coleta e análise

- [ ] Consolidar os CSVs (equivalência + escala) no formato fixado na 3.0.
- [ ] Visualizações: tabela de equivalência por dataset/paradigma; curva tempo × volume (porte vs. oráculo); tabela de contagens por bug (o que o porte corrige por construção × o que replica).
- [ ] Redigir o capítulo de avaliação: **corretude** (equivalência estrutural), **escala** (tendência preservada), **correções por construção** (#6/#7 sem patch; #8 medido dos dois lados).
- [ ] Declarar as **limitações** com a mesma honestidade das fases anteriores: o Northwind não está travado em CI se não for vendorizado; o `$numberLong` não tem fixture-oráculo (nenhum dataset de referência tem campo `long`); a comparação é estrutural, não byte a byte.

**Saída:** material do capítulo de avaliação experimental, com todo número rastreável a uma corrida registrada.

---

## Housekeeping (dívidas que a fase encosta)

- [ ] `resources/README.md` — descreve `movies_min.xmi` como "modelo mínimo Neo4j" (é o User Profiles **Small**, 100.000 `User`) e não lista `up_medium`/`up_large`/`up_larger.xmi`.
- [x] `.gitignore` cobre `out/` e `resultados/` (feito pelo Davi). Consequência a decidir na 3.4: os **CSVs** são a evidência do capítulo e hoje não estão versionados — os XMIs não precisam estar (são grandes e regeneráveis), mas 1 KB de CSV é caso diferente.
- [x] **Saída separada por produtor:** `out/porte/` (nosso), `out/oraculo/` (Java em Docker), `resources/` (autores originais, versionado). Convenção em `resources/README.md`, "Onde cada XMI mora"; as duas baterias já escrevem no lugar certo.
- [ ] `cli.py` + `[project.scripts]` — previstos na 1.7, que fechou sem eles. Registrado no `CLAUDE.md`; a 3.0 recomenda **não** criar agora.
- [ ] Documentos referenciados pelos quatro guias de fase e ausentes do repo: `roteiro_experimental.md`, `resultado_mongodb.md`, `resultado_neo4j.md`, `resultado_bug8_subcontagem_user.md`, `analise_ferramenta_uschema.md`. Recuperar ou remover as referências penduradas.

---

## Gate de aceite da Fase 3

- [~] **Corretude:** Northwind fecha (`equivalent=True`, só não-fatais do #8) e o User Profiles/grafo fecha na escala `small` **contra o oráculo semeado, com zero divergências** — o padrão-ouro, mesma entrada nos dois lados. Faltam as outras três escalas do grafo e o **Sakila**.
- [x] **Escala: 36 corridas feitas** — 3 sementes × (8 do Mongo + 4 do grafo). Leitura integral confirmada no grafo (100% nas 12) e subcontagem do documento reprodutível dentro de 1,7%. **Sem estouro de memória em nenhuma**, apesar de pura-Python nos 800k. O CSV do grafo foi apagado em 01/08/2026 (cabeçalho antigo + linhas contaminadas); re-executar com a bateria corrigida para restaurar o respaldo.
- [ ] **A tendência se preserva em direção, mas não em fator de crescimento — nos dois paradigmas.** Documento 19,3× e grafo **25,4×** para 8× de dado, contra 8,7× e 9,1× do oráculo. E o overhead contra a JVM **cresce com a escala** no grafo (4,3× no `small`, 11,9× no `larger`), o que descarta "Python é N vezes mais lento" como explicação. O gate só fecha se isso for **declarado e investigado**, não arredondado para "curva preservada".
- [x] **Bugs #6/#7:** Rota B (`_id` inteiro + ~15% arrays vazios) rodou os 4 tamanhos até 800k **sem patch e sem exceção**.
- [ ] **Bug #8:** medido nas 8 corridas, casando com a subcontagem do oráculo (faixa 2,63%–31,28%, com `Movie` a 100% como controle). Um número que "acertasse" o volume real no paradigma documento estaria **fora** do gate. Falta o Northwind entrar na mesma planilha.
- [ ] **Rastreabilidade:** todo número do capítulo sai de uma corrida registrada em CSV.

## Entregáveis

`scripts/` (geradores + baterias de corretude e escala), `resultados/` (CSVs), os gráficos, e o material do capítulo de avaliação experimental.

## Riscos da fase

- **Afirmar número não medido** — o risco dominante; os `.md` anteriores citam valores do experimento original, não do porte.
- **Citar número ordem-dependente como se fosse invariante** — foi o que aconteceu com as "15 divergências" do Northwind, corrigido em 31/07/2026. Todo `count` publicado tem de vir com o caminho de extração que o produziu.
- **Comparar escalas diferentes sob o mesmo rótulo** — a sessão de 31/07/2026 chegou a contrastar grafo `larger` (800k) com Northwind (397 documentos). Dataset **e** tamanho, sempre explícitos.
- **Ambiente: MongoDB não sobe em kernel ≥6.19.** O `mongod` 8.0.28 recusa iniciar (`SERVER-125742` só remove o guard para kernel **≥7.0.14**; a máquina do Davi está no 7.0.0-28, e o apt não oferece nada ≥7.0.14). Contorno em uso: bootar o **6.17.0-40-generic** via `grub-reboot` (boot único). Docker **não** resolve — o container compartilha o kernel do host. Registrar no capítulo de reprodutibilidade: a bateria exige kernel <6.19 **ou** MongoDB ≥8.0.30 com kernel ≥7.0.14.
- **Alvo do #8 conflitante com a fidelidade** (achado do topo) — se passar batido, ou o gate de equivalência quebra ou o capítulo publica um número que o porte não produz.
- **Memória em pura-Python** nos 800k — perfil diferente do Spark; `mapPartitions` é a saída, não a reescrita.
- **Sakila indisponível** — único bloqueio externo; sem ele a corretude fica com um único dataset de documento e o *overfitting* ao Northwind não é descartado.
- **`N1` aparecendo pela primeira vez** na extração real do grafo (nós multi-label) — diagnosticar pelo `.java`, não pelo sintoma.
- **Custo de geração do grafo** dominando a bateria (~180 s no maior) — planejar a janela; é da materialização, não da inferência.
