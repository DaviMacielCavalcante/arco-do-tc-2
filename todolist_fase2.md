# TO-DO — Fase 2: Extratores PySpark (MongoDB + Neo4j)

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi Cavalcante · João — CESUPA
**Base:** `fase2_extratores_pyspark.md` · **Contrato de costura:** `extractors/triple.py` (Fase 1.0) · **Bugs:** `bugs_originais.md`
**Pré-requisito:** Fase 1 ✅ (núcleo de inferência completo; golden-master do mintest com 0 divergências)

> **Organização por entrega.** Tarefas agrupadas por **entregável** (2.0–2.3), não por
> autor — trabalho compartilhado, sem dono fixo. Cada bloco define uma **Saída**
> que serve de critério de "pronto".
>
> **Ideia central.** *Bottom-up*, *test-alongside*, e — a diferença desta fase —
> **os extratores só produzem triplas.** Não têm inferência nem construção de
> modelo próprios: entregam `{schema, count, firstTimestamp, lastTimestamp}` ao
> **núcleo único** da Fase 1 (`BuildUSchema`). Isso é mais limpo que o original,
> onde cada extrator `.spark` trazia um `ModelDirector` (ver o achado ⚠️ abaixo).
>
> ⚠️ **Abrir o `.java` antes de afirmar.** As fontes estão nos commits pinados
> (`6dfd6b4a`/`0f8f58c3`, `oracle/Dockerfile`). O falso C8 e o mapeamento errado
> do `m2m` (1.4b) nasceram de diagnosticar pelo nome, sem abrir o fonte.

---

## ⚠️ Achado que corrige a spec: há DOIS extratores MongoDB, e o certo não é o que a spec cita

`fase2_extratores_pyspark.md` §2.1 aponta `ArchetypeMapping`/`JSONMapping`/
`ModelDirector` (pacote `mongodb2uschema.spark`) como referência. **Verificado no
fonte que esse é o extrator errado para a nossa arquitetura.** Existem dois:

| Extrator | Produz | Alimenta | Gera os XMIs de referência? |
|---|---|---|---|
| `mongodb2uschema` (**Helpers**) | tripla `{schema, count, ts}` | `SchemaInference`+`USchemaModelBuilder` (nosso núcleo) | **SIM** — mintest/northwind |
| `mongodb2uschema.spark` (ArchetypeMapping) | `{entity, properties}` | `ModelDirector` (construtor próprio, **não** o nosso núcleo) | não (escala/`up_b_larger`) |

**Prova:** o oráculo roda `mongodb2uschema.main.MongoDB2USchemaMain`
(`oracle/entrypoint.sh:79`), cujo `MongoDB2USchema.process` usa
`Helpers.generateDocumentPair`/`reducePairs` (`MongoDB2USchema.java:76-77`),
anexa `_type` = nome da coleção (`:82`) e importa `SchemaInference`/
`USchemaModelBuilder` (`:20-21`). Além disso, o golden-master do mintest (Fase 1.7)
fechou com **0 divergências** reproduzindo à mão exatamente o `Helpers.simplify`.

**Consequência:** a 2.1 porta o caminho **`Helpers`**, não o `ArchetypeMapping`.
Portar o `ArchetypeMapping`+`ModelDirector` **duplicaria** a inferência que a
Fase 1 já tem — contra a decisão de arquitetura de "um núcleo só".

---

## Cadeia de desbloqueio

```text
Fase 1 ✅ (BuildUSchema) ─┐
extractors/triple.py ─────┼─→ 2.0 (infra Spark + conectores) ─→ 2.1 (Mongo/Helpers) ─→ 2.3 (golden-master Northwind, herdado da 1.7)
                          └─→ 2.2 (Neo4j) ────────────────────────────────────────────┘
```

| Etapa | Depende de | Libera | Verificado |
|---|---|---|---|
| **2.0** infra Spark | Fase 1 | 2.1, 2.2 | pyspark já é dep; teto Python 3.12 por causa dele |
| **2.1** Mongo | 2.0, tripla | 2.3 | `MongoDB2USchema.java:60-82` (Helpers) |
| **2.2** Neo4j | 2.0, tripla | grafo | `SparkProcess`/`IdArchetypeMapping` |
| **2.3** golden-master Northwind | 2.1 | gate integração da Fase 1 **e** 2 | `model_northwind.xmi`; as 8 não-fatais do #8 |

---

## 2.0 — Infra PySpark + conectores

- [ ] Confirmar o `SparkSession` mínimo (RDD de baixo nível — `map`/`reduceByKey`/`flatMap`/`collect`; **sem** DataFrame SQL, MLlib, streaming). Marcar os testes com `@pytest.mark.spark` (rodam no pre-push/CI, não no pre-commit).
- [ ] **MongoDB:** `mongo-spark-connector_2.12:3.0.1` (ou compatível com o Spark do porte) via `spark.jars.packages`. Documentar a versão exata (reprodutibilidade).
- [ ] **Neo4j:** decidir entre o legado `neo4j-contrib:neo4j-spark-connector:2.4.5-M2` e o oficial `org.neo4j:neo4j-connector-apache-spark` 5.x, **validando cedo** contra o Neo4j-alvo (risco da fase). Conector legado lê o banco padrão `neo4j` e espera **auth desligada**.
- [ ] `uv add` das deps que faltarem; citar no PR (para quê/por quê).

**Saída:** `SparkSession` de teste reproduzível + conectores pinados e documentados.

---

## 2.1 — Extrator MongoDB (caminho `Helpers`, o que alimenta o núcleo)

> Referência **corrigida**: `mongodb2uschema/MongoDB2USchema.java` + `utils/Helpers.java`
> (**não** o `.spark`/`ArchetypeMapping`). Pipeline (`:60-82`):
> `mapToPair(generateDocumentPair) → reduceByKey(reducePairs) → put(_type, coll) → documentPairToJSONNode`.

- [ ] Portar **`Helpers.simplify`** (`Helpers.java:14-52`) como função pura recursiva sobre `dict`/`bson`:
  - escalares → sentinela de tipo (`str`/`Date`→`""`, `bool`→`false`, `int`→`0`, `float`→`0.0`, `long`→`0`);
  - **`ObjectId` → sentinela `ObjectId("000…0")`**, que no `.toJson()` vira `{"$oid": …}` (objeto) → vira **entidade agregada** (é a origem do `_id` interno no XMI). Ver `extractors/triple.py`;
  - `Document`/objeto → recursivo; `list` → recursivo **sem colapsar** (o Spark mantém todos os elementos; o colapso é só do map-reduce);
  - tipo não suportado → `UnsupportedOperationException` (replicar? decidir; provavelmente `raise`).
- [ ] Portar **`generateDocumentPair`** (`:53-59`) + **`reducePairs`** (`:60-67`): `map` produz `(simplify(doc), (ts, ts, 1))`; `reduceByKey` faz `(min firstTs, max lastTs, sum count)`.
- [ ] **`_type` = nome da coleção cru** (`MongoDB2USchema.java:82`, `put(typeField, collectionName)`) — **não** capitalizado aqui; quem capitaliza é o `infer` (`capitalize(_type)`, Fase 1.2). Anexado ao `schema` **depois** da agregação.
- [ ] **Bug #6 por construção** (o oráculo corrige por patch `0006`): o `generateDocumentPair` faz `doc.getObjectId("_id").getTimestamp()`, que **estoura** em `_id` não-`ObjectId`. Ler o `_id` **genericamente**: timestamp só se for `ObjectId`, senão `0` (cenário relacional→NoSQL). **Isto é pré-requisito do Northwind**, cujo `_id` é **inteiro** (achado da 1.7: `"_id":1`) — sem o #6, o extrator quebra no Northwind.
- [ ] **Bug #7 por construção:** a assinatura de array vazio (`[]`) não indexa elemento inexistente (o `simplify` de `[]` devolve `[]`, sem tocar `get(0)`). Já tratado no núcleo (1.4); confirmar que a assinatura também não estoura na origem.
- [ ] Conectar via `spark.read.format("mongodb")` por coleção; `.rdd` → pipeline acima → `collect()` → entregar ao `BuildUSchema.build_from_rows`.
- [ ] **Testes** (`@pytest.mark.spark` para os que sobem Spark; puros para as funções de assinatura): doc simples, aninhado, array vazio (#7), array de documentos, `_id` inteiro (#6), `_id` ObjectId (→ `{$oid}`). **Reusar as fixtures que já temos como oráculo de tripla:** `tests/fixtures/count_timestamp.json`/`simplify_aggr.json` (map-reduce v1) e `mintest_spark.json` (Spark) — mas ⚠️ estas duas primeiras são do **caminho map-reduce**, então servem de oráculo só para um extrator map-reduce; para o extrator **Spark** o oráculo é o `mintest_spark.json` e o `model_mintest.xmi`.

**Gate 2.1:** a contagem de assinaturas por coleção é **idêntica** à do Java; a tripla, alimentada no núcleo da Fase 1, reproduz o `model_mintest.xmi` (0 divergências, já validado à mão na 1.7 — agora com a tripla **extraída**, não reconstruída).

---

## 2.2 — Extrator Neo4j (paradigma grafo)

> Referência: `neo4j2uschema` — `SparkProcess` (pipeline), `IdArchetypeMapping`,
> `ReduceByIdArchetype`, `SplitMapping`. Pipeline estruturalmente idêntico ao Mongo:
> `mapToPair(IdArchetypeMapping) → reduceByKey(ReduceByIdArchetype) → flatMap(SplitMapping)`.

- [ ] Portar `IdArchetypeMapping`, `ReduceByIdArchetype`, `SplitMapping` como funções puras (testes: nó isolado, aresta com/sem propriedade, nó-sumidouro).
- [ ] Montar as triplas do grafo no **mesmo contrato** do MongoDB e entregar ao núcleo da Fase 1.
- [ ] **Especificidades do grafo a preservar** (o núcleo já tem o `RelationshipType`→`EntityType` na 1.4b, mas a extração é quem os cria):
  - `RelationshipType` de **primeira classe** (arestas viram `<relationships>`, não agregados);
  - **propriedades em arestas** inferidas (`roles`, `rating`);
  - **`count` de `RelationshipType`** = nº de entidades de **origem** que exercem a aresta (não o total bruto de arestas) — replicar a semântica de `ReduceByIdArchetype`/`SplitMapping`. É o ponto sutil da fase.
- [ ] Conector Neo4j: validar a versão funcional (o legado 2.4.5-M2 conectou no 2026.05.0, mas confirmar; pode exigir o 5.x para Neo4j 5+). Banco padrão `neo4j`, auth desligada.
- [ ] **Testes** com grafo mínimo (User/Movie, `WATCHED`/`FAVORITE`) — o oráculo `resources/neo4j/movies_min.xmi` já existe.

**Gate 2.2:** contagens (incl. a de `RelationshipType` por entidade de origem) idênticas ao Java; XMI ≡ oráculo (grafo mínimo + User Profiles em grafo, `resources/neo4j/up_*.xmi`).

---

## 2.3 — Golden-master do Northwind (herdado da Fase 1.7)

> **Adiado da 1.7 por decisão** (`todolist_fase1.md` §1.7): o Northwind exige a
> tripla **real** do extrator, não reconstruível à mão (os `count` reais não saem
> do esquema, e o objetivo é exibir a divergência do #8). Desbloqueia quando a 2.1
> existir.

- [ ] Rodar a 2.1 sobre o Northwind (Mongo populado — dados em `~/Documents/GitHub/mongodb-northwind`, `mongo-import.sh`) → tripla → `BuildUSchema` → comparar com `resources/mongodb/model_northwind.xmi` pelo `compare()` da 0.3.
- [ ] **Divergência esperada e desejada — o #8:** o oráculo tem o #8 (colapso de variações sem `combine_metadata`, deliberadamente sem patch — `oracle/docker_explain.md`); o porte **não**. As **8 não-fatais** em `Orders`/`Purchase_orders` que a 0.5 já registrou são exatamente essa assinatura. **Documentar a diferença como resultado**, não "consertar" para bater. É o fecho do gate de integração da Fase 1 **e** da Fase 2.
- [ ] Resolver o mistério do `_id`/`$oid` do Northwind (achado da 1.7): o `_id` é inteiro, mas `model_northwind.xmi` tem uma entidade `_id`/`$oid`. Ao extrair de verdade (com o #6), confirmar de onde vem — se persiste, é dado a catalogar.

**Saída:** golden-master do Northwind fechando estruturalmente contra o oráculo, com as divergências de #6/#7/#8 explicadas uma a uma — o que a 1.7 deixou em aberto.

---

## Costura com a Fase 1

Os dois extratores produzem o **mesmo formato de tripla** (`extractors/triple.py`),
já congelado e validado desde a Fase 1. A saída de 2.1 e 2.2 é intercambiável da
perspectiva do `BuildUSchema`. Nada de `ModelDirector`: um núcleo de inferência só.

## Gate de aceite da Fase 2

Para os dois paradigmas: **contagem de assinaturas idêntica ao Java** *e* **XMI
final estruturalmente equivalente ao oráculo** pelo harness da 0.3 (Northwind para
documento; grafo mínimo + User Profiles para grafo), com toda divergência fatal
explicada por um bug catalogado (o #8 no Northwind é esperado e documentado).

## Entregáveis

`extractors/mongo.py` (porte de `Helpers` + pipeline PySpark + montagem de tripla),
`extractors/neo4j.py` (`IdArchetypeMapping`/`ReduceByIdArchetype`/`SplitMapping` +
pipeline), testes das funções de assinatura + de extração (`@pytest.mark.spark`),
conectores pinados, e o golden-master do Northwind (2.3).

## Riscos da fase

- **Versão do conector Neo4j** incompatível com o servidor-alvo — validar cedo (2.0).
- **`count` de `RelationshipType`** (contar fontes distintas, não arestas brutas) — semântica sutil de `ReduceByIdArchetype`/`SplitMapping`.
- **`_id` genérico (#6) e array vazio (#7)** tratados **na origem da assinatura**, aqui — sem o #6, o Northwind (`_id` inteiro) nem extrai.
- **Não portar o `ArchetypeMapping`/`ModelDirector`** por engano (ver o achado no topo) — duplicaria o núcleo da Fase 1.
- **Spark no pre-commit:** os testes de extração são `@pytest.mark.spark` (lentos); só rodam no pre-push/CI. Não deixar nenhum extrator no gate rápido.
