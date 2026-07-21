# Inventário da suíte JUnit do original (Fase 0.4)

Levantamento completo dos testes do repositório Java, para decidir **o que
portar, para onde, e em que ordem**. Fontes lidas:
[`modelum/uschema`](https://github.com/modelum/uschema) e
[`modelum/uschema-inference`](https://github.com/modelum/uschema-inference).

**Números:** 37 arquivos `*Test.java`, ~2.500 linhas. Dados em
`es.um.uschema.documents/testSources/`.

---

## Os dois achados que mudam o plano

### 1. Metade dos testes "de regressão" **exige um MongoDB de pé**

O roadmap parte do princípio de que a camada de regressão portada é a mais barata
porque **não depende de Docker**. Isso vale para **metade** dela.

Os quatro testes em `es.um.uschema.documents/test/regression/`
(`CountTimestampTest`, `ObjectIdTest`, `TypesTest`, `SimplifyAggrTest`) fazem, no
`@Before`/`@Test`:

```java
controller = new EveryPolitician2Db(DbType.MONGODB, "localhost");  // sobe conexão
controller.run(new File("testSources/CountTimestamp.json"), dbName); // injeta no Mongo
MongoDBImport inferrer = new MongoDBImport("localhost", dbName);
JsonArray jArray = inferrer.mapRed2Array(Path.of("mapreduce/mongodb/v1/")); // map-reduce NO Mongo
builder.buildFromGsonArray(dbName, jArray);                          // só aqui infere
```

Ou seja: **JSON → Mongo → map-reduce → JsonArray → inferência**. Sem banco, não
rodam. São testes de *integração* disfarçados de regressão.

Já os quatro de `es.um.uschema.doc2uschema/test/regression/` (`OptionalTest`,
`RemovePMapTest`, `RelationshipTypeToEntityTypeTest`, `J2SchemaSimpleTests`) são
**puros**: montam o JSON **na própria classe de teste** e o entregam direto ao
`BuildUSchema`. Nenhum banco.

### 2. O JSON literal desses testes puros **é o contrato da tripla**

Este é o `jsonContent` do `OptionalTest`, escrito à mão dentro do teste:

```json
[{ "schema": { "_id": "s", "optionalAttr": "s", "requiredAttr": "s", "_type": "MyEntity" },
   "count": 1, "firstTimestamp": 0, "lastTimestamp": 0 },
 { "schema": { "_id": "s", "requiredAttr": "s", "_type": "MyEntity" },
   "count": 10, "firstTimestamp": 0, "lastTimestamp": 0 }]
```

`{schema, count, firstTimestamp, lastTimestamp}` **é a saída do map-reduce** — e é
exatamente a **tripla** que a Fase 2 produz e a Fase 1 consome
(`extractors/triple.py`, a costura entre as duas frentes).

**Consequência prática, e é a decisão central da 0.4:** os quatro testes que
dependem de Mongo podem ser portados **sem Mongo**, cortando o pipeline na
tripla. Em vez de *injetar JSON no banco e rodar o map-reduce*, congela-se a saída
do map-reduce como **fixture** e alimenta-se a inferência com ela. O teste deixa
de ser integração e vira unidade — rápido, determinístico, e localizando o erro no
módulo, que é o que o roadmap prometia.

O custo: a fixture precisa ser **gerada uma vez** pelo oráculo (é para isso que a
0.5/Docker existe), ou reconstruída à mão a partir do `testSources/*.json`
correspondente. Gerar pelo oráculo é mais fiel e mais barato.

> ⚠️ Isso **não** dispensa um teste ponta a ponta com banco — ele só sai da camada
> de regressão e vai para a Fase 3 (`@pytest.mark.integration`), onde já mora o
> golden-master de dataset.

---

## Inventário completo

### A. Regressão pura — portar **primeiro**, sem dependência externa

Alimentam o inferidor diretamente. São o critério de aceite módulo a módulo da
Fase 1.

| JUnit | Linhas | Módulo do porte | O que fixa |
|---|---|---|---|
| `doc2uschema/…/regression/InflectorTest` | 394 | `naming.inflector` (**0.6**) | pluralize/singularize/camelCase — **desbloqueado hoje** |
| `doc2uschema/…/regression/OptionalTest` | 72 | `inference.strategies` (1.3) | `optional` de atributo entre variações |
| `doc2uschema/…/regression/RemovePMapTest` | 141 | `intermediate.raw` / builder (1.1/1.4) | remoção de `PMap` |
| `doc2uschema/…/regression/RelationshipTypeToEntityTypeTest` | 158 | `inference.builder` (1.4) | `Reference` × `RelationshipType` |
| `doc2uschema/…/regression/J2SchemaSimpleTests` | — | `intermediate.raw` (1.1) | JSON → schema cru; asserções sobre a **string** do schema |
| `mongodb2uschema/…/SimplificationTest` | 187 | `extractors.mongo` (2.1) | `Helpers.simplify` — normalização do documento |
| `mongodb2uschema/…/PairOperationsTest` | 68 | `extractors.mongo` (2.1) | `generateDocumentPair` / `reducePairs` (o `map`/`reduceByKey`) |
| `utils/…/compare/CompareDataTypeTest` | 134 | `validation.equivalence` (0.3) | ✅ **coberto** — ver nota abaixo |
| `utils/…/compare/ComparePropertyTest` | 151 | `validation.equivalence` (0.3) | ✅ **coberto** |
| `utils/…/compare/CompareUSchemaTest` | 225 | `validation.equivalence` (0.3) | ✅ **coberto** — é a fonte do `assertFalse(compare(null,null))` (ver C8) |
| `utils/…/ModelIOTest` | 52 | `metamodel.xmi` (0.2) | ✅ **coberto** — round-trip de XMI |

> **Os quatro de `utils/` já estão cobertos** pelas Fases 0.2/0.3 — não por porte
> linha a linha, mas por reconstrução. Portar por cima seria redundante. A
> **conferência de asserções** foi feita e **achou quatro lacunas reais**: ver a
> seção abaixo.

---

## Conferência das asserções (feita) — o que ela achou

A nossa suíte da Fase 0.3 foi escrita **a partir do código-fonte** dos
comparadores. Isso tem um ponto cego estrutural: um teste derivado da
implementação não detecta que a implementação foi **lida errado** — o porte
carrega o engano, o teste afirma o engano, e os dois concordam. Os JUnit do
original são a única fonte **independente** sobre esses comparadores: exprimem a
intenção do autor, não a nossa leitura.

A conferência (ler as asserções deles, checar se cada uma tem equivalente na nossa
suíte) achou **quatro lacunas**, todas do mesmo esquecimento — e três delas
causavam **`AttributeError`** onde o Java devolve um veredito.

**A causa raiz.** O original guarda o caso "tipo ausente **dos dois lados**" em
**cada contêiner**, com um `(x == null && y == null) ||` **antes** de delegar ao
`CompareDataType`:

```java
// ComparePList (idêntico em ComparePSet)
return (l1.getElementType() == null && l2.getElementType() == null)
    || new CompareDataType().compare(l1.getElementType(), l2.getElementType());

// ComparePMap — guarda independente para chave e valor
return ((m1.getKeyType() == null && m2.getKeyType() == null) || new ComparePrimitiveType()...)
    && ((m1.getValueType() == null && m2.getValueType() == null) || new CompareDataType()...);

// ComparePrimitiveType — XOR no nome, e checkNulls no objeto
if (p1.getName() == null ^ p2.getName() == null) return false;
return (p1.getName() == null && p2.getName() == null) || mapType(p1).equals(mapType(p2));
```

Portamos essa guarda em **um** lugar só (`compare_attribute`) e a esquecemos nos
outros quatro. O `checkNulls` com `or` do `CompareDataType` é real, mas **nunca é
alcançado** com dois nulos em modelo válido — todo contêiner o protege.

| Lacuna | Sintoma no nosso porte | O que o JUnit deles afirma |
|---|---|---|
| `compare_plist` / `compare_pset` sem a guarda | dois `PList` de array vazio dão `False` → **o northwind não era equivalente a si mesmo** | (o `PList(null)` vs `PList(null)` não é testado lá — a guarda está no código) |
| `compare_pmap` sem as duas guardas | `AttributeError` se `keyType` é nulo | `assertTrue(cPMap.compare(f.createPMap(bool, null), f.createPMap(bool, null)))` |
| `compare_primitive_type` sem `checkNulls` | `AttributeError` | `assertFalse(cPrimitiveType.compare(null, null))` |
| `compare_primitive_type` sem tratamento de `name` nulo | `AttributeError` | `assertFalse(cPrimitiveType.compare(f.createPrimitiveType(null), f.createPrimitiveType("string")))` |

**Lição, e ela é o motivo desta seção existir:** a primeira leitura desse sintoma
(o A==A do northwind reprovando) concluiu que o **oráculo** era não-reflexivo, e
chegou a virar uma seção de `bugs_originais.md` ("C8") e um "desvio deliberado" no
código. Estava errado — o defeito era nosso, e só apareceu ao **abrir o `.java`**.
Diagnosticar o original lendo o nosso porte é circular. As fontes estão clonadas
em `~/Documents/GitHub/uschema{,-inference}`; não há desculpa para não abri-las.

Correção aplicada: guardas nos quatro lugares, `compare_datatype` de volta ao `or`
fiel, e **6 casos de teste novos** cobrindo cada asserção do `CompareDataTypeTest`
que faltava. **O porte não tem nenhum desvio em relação ao original.**

### B. Regressão presa a MongoDB — portar **cortando na tripla** (ver achado 2)

| JUnit | Linhas | Dado | Módulo | O que fixa |
|---|---|---|---|---|
| `documents/…/regression/CountTimestampTest` | 87 | `CountTimestamp.json` | `inference.schema_inference` (1.2) | `count`/`firstTimestamp`/`lastTimestamp` por variação — **área do #8** |
| `documents/…/regression/ObjectIdTest` | 72 | `ObjectIds.json` | tipos (1.2) | `_id` inferido como `ObjectId`, não `String` — **área do #6** |
| `documents/…/regression/TypesTest` | 67 | `Types.json` | 1.2 / 1.4 | o `_type` interno **não** aparece no modelo final |
| `documents/…/regression/SimplifyAggrTest` | 59 | `SimplifyAggr.json` | `inference.strategies` (1.3) | `Aggr{V1,V2,V2,…}` colapsa em `Aggr{V1,V2}` |

### C. Golden-master de dataset — **Fase 3**, exigem banco

`documents/test/test/` — rodam o pipeline inteiro contra um Mongo com dados reais.
Marcar `@pytest.mark.integration`.

| JUnit | Linhas | Dado |
|---|---|---|
| `UserProfileTest` | 64 | base `userprofile` (Mongo) |
| `FacebookTest` | 155 | `testSources/facebook/` |
| `CompaniesTest` | 61 | `Companies.json` |
| `TypeAndRefTest` | 62 | `TypeAndRef.json` |
| `MapReduceTimestampTest` | 54 | `MapReduceTimestamp.json` |

### D. **Não portar** — código morto no original

| Arquivo | Por quê |
|---|---|
| `documents/src/…/examples/tests/*.java` (17 arquivos) | **16 são stubs vazios** — corpo é `// TODO Auto-generated method stub`. O 17º (`UserProfileTest`, 38 linhas) tem corpo, mas é um *runner* de exemplo, não um teste: não tem `@Test` nem uma asserção. Não são JUnit. |
| `doc2uschema/test/automated/AutoTest1` | A única asserção é `assertEquals(true, true)`. |
| `doc2uschema/test/automated/{JSONGen, UBuilder}` | Gerador de JSON + construtor de USchema esperado: o esqueleto de um teste **generativo** que o autor nunca ligou a asserção nenhuma. Ideia boa, abandonada. Pode inspirar a Fase 3; não há o que portar. |
| `*/AllTests.java` | Suítes JUnit 4 (`@RunWith(Suite.class)`) — o `pytest` descobre sozinho. |

---

## Testes que codificam bug

Regra do `CLAUDE.md`: onde o original **erra**, porte a *estrutura* do teste mas
afirme o valor **corrigido**.

| Teste | Bug | O que fazer no porte |
|---|---|---|
| `ObjectIdTest` | **#6** (`_id` assumido `ObjectId`) | A asserção existente **continua válida** — um `_id` que *é* `ObjectId` deve continuar sendo inferido como `ObjectId`. O bug é o **crash** quando não é. → **acrescentar** um caso com `_id` de outro tipo (string, int), afirmando que infere sem estourar. |
| `CountTimestampTest` | **#8** (`meta` inteiro — count+timestamps — descartado no colapso de variações, ver `bugs_originais.md`) | Verificar, ao portar, se `CountTimestamp.json` tem alguma entidade cujas variações colapsem (não precisa de array: qualquer forma estruturalmente igual dispara). Se colapsar, a asserção de `count`/timestamp do JUnit original **já reflete** o bug (o teste do autor não corrigiu isso) — portar como está, sem "consertar". → **acrescentar** um caso novo confirmando que `count`/timestamps da segunda ocorrência somem por completo (não sejam somados) quando duas variações colapsam. |
| *(nenhum)* | **#7** (array vazio indexado) | Nenhum JUnit cobre array vazio. → **teste novo**. É o mesmo dado que originou o **C8** (o `privileges` do northwind). |

---

## Ordem sugerida

1. **`InflectorTest`** — é o único de regressão **desbloqueado hoje**: não depende
   da inferência (Fase 1) nem de banco. Fecha junto com a **0.6**, e o Inflector é
   pré-requisito de todo nome de entidade.
2. **`SimplificationTest` + `PairOperationsTest`** — puros, e independentes da
   Fase 1: validam o `Helpers` do extrator (Fase 2.1), que é a outra frente do
   trabalho paralelo.
3. **`J2SchemaSimpleTests` → `OptionalTest` → `RemovePMapTest` →
   `RelationshipTypeToEntityTypeTest`** — na ordem em que a Fase 1 constrói os
   módulos (1.1 → 1.3 → 1.4). Cada um é o critério de aceite do seu módulo.
4. **Os quatro do bloco B** — quando a tripla estiver congelada em fixture.
5. **Bloco C** — Fase 3.

O resto da Fase 0.4 (mapear golden-master → Fase 3) está no bloco C acima. Não há
mais nada a inventariar.
