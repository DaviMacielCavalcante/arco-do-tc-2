# tests/fixtures/ — triplas congeladas do bloco B (Fase 1.6)

Fixtures da camada de regressão que **não é pura**: os JUnit
`CountTimestampTest`/`SimplifyAggrTest` sobem um Mongo, injetam
`testSources/*.json`, rodam o map-reduce e só então inferem. Aqui o pipeline é
**cortado na tripla** — a saída do map-reduce é congelada como fixture e
alimenta a inferência direto, sem banco (ver `tests/regression/INVENTARIO.md`,
achado 2).

## Proveniência (qual caminho gerou cada uma)

Os dois caminhos de extração produzem triplas **diferentes** para o mesmo dado
(achado da 1.0). Estas fixtures foram geradas pelo **map-reduce `v1`**
(`modelum/uschema-inference@0f8f58c`,
`es.um.uschema.documents/resources/mapreduce/mongodb/v1/`), rodado num MongoDB
7.0 descartável via `mongosh` — não pelo Spark:

| Fixture | Origem | Caminho | Coleções |
|---|---|---|---|
| `count_timestamp.json` | `CountTimestamp.json` (map-reduce real) | map-reduce v1 | `areas`, `container` |
| `simplify_aggr.json` | `SimplifyAggr.json` (map-reduce real) | map-reduce v1 | `persons` |
| `mintest_spark.json` | **reconstruída** de `model_mintest.xmi` | Spark (à mão) | `products`, `customers` |

**`mintest_spark.json` é diferente das outras duas.** Não veio de um extrator
rodando: foi **reconstruída à mão** a partir da estrutura de
`resources/mongodb/model_mintest.xmi`, seguindo as regras do `Helpers.simplify`
do caminho **Spark** (`_id` como `{"$oid": …}`, folhas como sentinelas de tipo,
`_type` = coleção). Como todos os `count` do mintest são 1, a reconstrução é
exata e o golden-master fecha com **0 divergências**
(`tests/datasets/test_mintest_golden_master.py`). Para datasets com contagens
reais (Northwind), a reconstrução à mão erra os `count` — aí é preciso a tripla
do extrator (Fase 2) ou um dump do oráculo. Ver `todolist_fase1.md` §1.7.

**Por que v1 e não Spark.** O `CountTimestampTest`/`SimplifyAggrTest` rodam
`mapRed2Array(Path.of("mapreduce/mongodb/v1/"))` (`ObjectIdTest.java:56` e irmãos).
No v1 o `ObjectId` vira a sentinela `"oid"` e o array homogêneo colapsa — o Spark
faria diferente (`{"$oid": …}` vira agregado, sem colapso), e o teste afirmaria
sobre algo que esse caminho nunca produz.

## Formato

Lista de triplas `{schema, count, firstTimestamp, lastTimestamp}` — o contrato de
`extractors/triple.py`. O `schema._type` é o **nome da coleção capitalizado**
(`MongoDBStreamAdapter.java:29`: `collName[0].toUpperCase() + resto` — capitalização
simples, **não** o Inflector). As folhas são as sentinelas do v1 (`"string"`,
`"oid"`, `0`, `true`).

## Como foram geradas (reprodutível)

Reprodução fiel do `MongoDBImport.mapRed2Array` + `MongoDBStreamAdapter.adaptStream`
(o wrapper Java é fino: roda `collection.mapReduce(map, reduce)` por coleção e
coleta o `value`, anexando `_type`):

1. `docker run -d --name m -p 27017:27017 mongo:7.0`
2. por coleção (chave de topo do `testSources`), `insertMany` dos documentos;
3. `db.<coll>.mapReduce(<v1/map.js>, <v1/reduce.js>, {out:{inline:1}})`;
4. para cada resultado: `schema = JSON.parse(value.schema)`,
   `schema._type = capitalize(coll)`, montar a tripla.

**Validação (o que garante a fidelidade sem depender de detalhe de serialização):**
alimentar estas fixtures no pipeline `infer`+`build` reproduz **exatamente** as
asserções dos JUnit — `count_timestamp` dá 3 entidades com counts `{8,3}`/`{1,1}`
e a interna `Aggr` com count `2` (propagação pra entidade interna); `simplify_aggr`
dá 2 entidades com 2 variações cada (colapso do agregado). Ver
`tests/regression/test_count_timestamp.py` e `test_simplify_aggr.py`.
