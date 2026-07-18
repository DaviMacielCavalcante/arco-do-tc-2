# TO-DO — Fase 1: Núcleo de inferência (`doc2uschema`)

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi Cavalcante · João — CESUPA
**Base:** `fase1_nucleo_inferencia.md` · **Inventário:** `tests/regression/INVENTARIO.md` · **Bugs:** `bugs_originais.md`
**Pré-requisito:** Fase 0 ✅ (metamodelo + round-trip + harness + Inflector + oráculo)

> **Organização por entrega.** Tarefas agrupadas por **entregável** (1.0–1.7), não por
> autor — o trabalho é compartilhado, sem dono fixo. Cada bloco define uma **Saída**
> que serve de critério de "pronto".
>
> **Ideia central.** Esta fase é *bottom-up* e *test-alongside*: cada módulo nasce
> junto do teste de regressão JUnit que o valida (`INVENTARIO.md`, bloco A/B). O
> teste **localiza** o erro no módulo; o harness da 0.3 só diz que existe.
>
> ⚠️ **Toda afirmação sobre o Java abaixo foi verificada abrindo o `.java`** nos
> commits pinados (`6dfd6b4a`/`0f8f58c3`, `oracle/Dockerfile`), com citação de
> arquivo:linha. Três delas **contradizem** `fase1_nucleo_inferencia.md` — estão
> marcadas com ⚠️ e reconciliadas no bloco correspondente.

---

## Cadeia de desbloqueio (o que libera o quê)

Ordem derivada das dependências **reais** do código, não da numeração do roadmap:

```text
0.1/0.2 (PyEcore) ─┐
0.3 (compare_feature) ─┼─→ 1.3b (estratégias EMF) ─┐
0.6 (Inflector) ───┘                                ├─→ 1.4 (build/fillEV) ─→ 1.7 (costura + golden-master)
                                                    │
1.0 (tripla) ─→ 1.1 (raw/meta) ─→ 1.2 (infer) ──────┘
                       └────────→ 1.3a (joiner/merger) ─→ 1.2 (passos 4 e 6)
```

| Etapa | Depende de | Libera | Verificado |
|---|---|---|---|
| **1.0** tripla | — | 1.1, 1.2, fixtures do bloco B | `SchemaInference:86-89` lê `schema`/`count`/`firstTimestamp`/`lastTimestamp` |
| **1.1** raw + meta | 1.0 | 1.2, 1.3a | `infer` constrói `ObjectSC`/`ArraySC`; `combineMetadata` é a correção do #8 |
| **1.3a** joiner/merger | 1.1 | passos 4 e 6 de 1.2 | operam sobre `Map<String,List<SchemaComponent>>` — nível **raw**, sem EMF |
| **1.2** infer | 1.0, 1.1, 1.3a, 0.6 | 1.4 | `SchemaInference:183,188,233` chamam o Inflector |
| **1.3b** estratégias EMF | 0.1, 0.3, 0.6 | 1.4 | `DefaultFeatureAnalyzer:17` instancia `CompareFeature` (**código da 0.3**) |
| **1.4** build/fillEV | 1.1, 1.2, 1.3b, 0.1/0.2 | 1.7 | `USchemaModelBuilder:89-148` |
| **1.7** costura | tudo acima | Fase 3 | golden-master do Northwind pelo harness da 0.3 |

> ⚠️ **A 0.3 não é só validação — é dependência de código da 1.3b.** O
> `DefaultFeatureAnalyzer` usa `CompareFeature` (`DefaultFeatureAnalyzer:8,17`), a
> mesma árvore de comparadores que portamos em `validation/equivalence.py`
> (`compare_feature`, linha 550). A 1.3b **reusa** essa função; não reimplemente.

---

## 1.0 — Contrato da tripla (`extractors/triple.py`) · a costura com a Fase 2

- [x] Definir a `dataclass` `SchemaTriple`: `schema` (dict), `count` (int), `first_timestamp` (int), `last_timestamp` (int). É o contrato compartilhado com a Fase 2 — **combinar antes de codar**, é a costura entre as duas frentes.
- [x] **Decidir como o `ObjectId` viaja na tripla.** **Resolvido — e a resposta não era nenhuma das hipóteses.** Ver o achado abaixo.
- [x] Portar `validateRows` (`SchemaInference:78-90`): **só valida o primeiro elemento** ("suppose the rest are correct") e devolve `True` para lista vazia. Fiel — não "melhorar" validando todos.
- [x] `raise ValueError` no lugar do `IllegalArgumentException` (`SchemaInference:128`), mensagem equivalente.
- [x] `CLAUDE.md` alinhado com a realidade do repo (a seção *Project layout* agora lista o estado real e não afirma stubs/`cli.py`).

### ⚠️ Achado: a tripla não carrega valores, e o `ObjectId` não viaja como tipo

Verificado no fonte e confirmado no XMI de referência. Três fatos encadeados:

1. **O `schema` da tripla é um esqueleto de tipos, não o documento.** Os dois
   extratores apagam todo valor antes de emitir: o Spark via `Helpers.simplify`
   (`mongodb2uschema/utils/Helpers.java:29-56`, sentinelas em
   `Constants.java:18-23`), o map-reduce via `flatten_schema`
   (`mapreduce/mongodb/v2/map.js`). Só o **tipo** da folha sobrevive.
2. **`isObjectId()` é "o valor é a string literal `oid`"** — `JacksonElement.java:93`
   e `GsonElement.java:120`, ambas `isTextual() && asText().equals("oid")`; e
   `isTextual()` exclui esse caso (`JacksonElement.java:87`). É a sentinela do
   `map.js`, e só ela.
3. **No caminho do oráculo (Spark) o `ObjectId` nunca chega como string.**
   `Document.toJson()` serializa a sentinela em extended JSON — `{"$oid": "0000…"}`
   —, que é **objeto**: `isObject()` casa primeiro e o `_id` vira **entidade
   agregada** com atributo `$oid` do tipo `String`. Está em
   `resources/mongodb/model_mintest.xmi:69-72` e em `model_northwind.xmi`.

**Consequências.** (a) A tripla carrega `dict` nativo puro — nenhum wrapper,
nenhum `bson.ObjectId`; a distinção é um **predicado sobre o valor**
(`classify`), e replicá-lo reproduz os dois caminhos, divergência inclusa.
(b) **`ObjectIdSC` é código morto no caminho Spark** — só o map-reduce o alcança;
não gastar teste de equivalência nele. (c) **Corrige o plano da 1.6:** a fixture
do `ObjectIdTest` tem de ser gerada pelo caminho **map-reduce v1**
(`ObjectIdTest.java:56`), não pelo Spark — gerada pelo Spark, o teste afirmaria
`PrimitiveType` de nome `ObjectId` sobre um dado que produz um agregado, e
falharia por motivo errado.

**Saída:** ✅ `extractors/triple.py` (`SchemaTriple`, `JsonKind`, `classify`,
`validate_rows`, `triples_from_rows`) + `tests/unit/test_triple.py` (39 casos);
`CLAUDE.md` alinhado.

---

## 1.1 — Modelos intermediários (`intermediate/raw` + metadata) ✅

> Igualdade estrutural é **load-bearing**: se divergir do Java, variações que
> deveriam colapsar não colapsam (ou vice-versa) e o XMI não bate. Cobrir com teste
> de `__eq__`/`__hash__` **desde já**.

- [x] `SchemaComponent` (base) + `ObjectSC`, `ArraySC`, `StringSC`, `NumberSC`, `BooleanSC`, `NullSC`, `ObjectIdSC` como `dataclasses`.
- [x] **`SchemaComponent.__eq__` compara o nome da classe** (`SchemaComponent.java:8`: `getClass().getName().equals(...)`). As folhas (`StringSC`/`NumberSC`/…) **não sobrescrevem** — dois `StringSC` quaisquer são iguais. O Java estoura `NullPointerException` se `other` for `null`; decidir e **registrar** se replicamos (recomendo não replicar — é linha faltando, não semântica, como o `I2` do Inflector).
- [x] **`ObjectSC.__eq__` = `entityName` + `isRoot` + `inners`** (`ObjectSC.java:33-34`), onde `inners` é **lista ordenada** de pares `(nome, SchemaComponent)` → **a ordem dos campos importa**. `__hash__` = `entityName ^ isRoot ^ inners` (`ObjectSC.java:24`) — estoura se `entityName` for `None`.
- [x] **`ArraySC.__eq__` ignora o tamanho** (`ArraySC.java:82-101`, com a checagem de `homogeneous_size` **comentada** na `:97` no original). Compara `homogeneous` + `inners`. `__hash__` = `inners` apenas. **É deliberado e é a origem do #8** — replicar junto com a correção em 1.2.
- [x] **`ArraySC.add`** (`ArraySC.java:38-67`), e é mais sutil que parece: enquanto homogêneo, `inners` guarda **um só** elemento e `homogeneous_size` conta; ao aparecer um diferente, vira heterogêneo e `inners` é **reconstruído** com `nCopies(homogeneous_size, firstSc) + sc`. `upperBounds` incrementa sempre; `lowerBounds` fica 0.
- [x] **`ArraySC.size()`** devolve `homogeneous_size` se homogêneo, senão `len(inners)` (`ArraySC.java:106-112`) — é o que faz o guarda do #7 funcionar (array vazio ⇒ `size()==0` **e** `inners` vazio).
- [x] `ObjectMetadata` (count/firstTimestamp/lastTimestamp) + **`combine_metadata`** (`ObjectMetadata.java:50-60`): `count += orig.count`; `firstTimestamp = min` e `lastTimestamp = max`, **ambos com `0` como sentinela** (`if firstTimestamp == 0 or orig.firstTimestamp < firstTimestamp`). O construtor default deixa tudo em 0. ⚠️ A sentinela só vale de **um lado** — defeito novo, catalogado como **M1** em `bugs_originais.md`, replicado e travado por teste.
- [x] ~~`firsto`: `MultiValued`, `NumberWithRangeSC`, `Ranged`, `StringMultiValuedSC`.~~ **Não portado — código morto confirmado.** `grep` das quatro classes em todo o repo Java não retorna **nenhuma** referência fora do próprio pacote `intermediate/firsto/`: não são importadas pelo `SchemaInference`, pelo `USchemaModelBuilder`, por nenhuma estratégia nem por nenhum JUnit. Mesma decisão que a 0.6 tomou para o `camelCase`/`underscore` do Inflector, com uma diferença a favor: lá havia teste cobrindo, aqui não há. **Não há `firsto.py`** — reintroduzir só se algum consumidor aparecer.
- [x] ~~`SchemaPrinter` (`intermediate/raw/util`)~~ → **movido para a 1.6.** A dúvida do todolist ("confirmar se o `J2SchemaSimpleTests` depende dele") está resolvida: **depende** (`schemaString`, três asserções sobre a string). Mas ele só faz sentido junto do teste que o exercita, e arrasta uma dependência a mais — ver o item correspondente na 1.6.
- [x] Testes de `__eq__`/`__hash__`: contrato hash/eq, ordem de campos, `ArraySC` de tamanhos diferentes **iguais**, homogêneo × heterogêneo.

**Saída:** ✅ `intermediate/raw.py` + `metadata.py` (**sem** `firsto.py`), com
igualdade estrutural coberta por `tests/unit/test_raw.py` e
`tests/unit/test_metadata.py` (50 casos). `SchemaPrinter` e `RawSchemaGen`
saíram do escopo desta entrega e estão na 1.6, junto do teste que os exercita.

---

## 1.2 — `SchemaInference.infer`

> Ordem dos passos verificada em `SchemaInference.java:125-146`. **Não reordenar.**

- [ ] `infer(rows)`: `validateRows` → `forEach` das triplas → `joiner.joinAggregatedEntities` → `innerCountAndTimestampsAdjust` → `merger.mergeEquivalentEVs`.
- [ ] **`infer` recursivo de objeto** (`SchemaInference:176-225`):
  - [ ] nome da entidade: se raiz, `capitalize(n["_type"])`; senão `capitalize(elementName)` (`:183,188`).
  - [ ] campos **ordenados** e filtrados por `config.ignored_attributes` (`:193-194`, via `TreeSet` na `:194`). Ordenação natural de string do Java = ordem de **code unit UTF-16**; o `sorted()` do Python é code point — divergem só fora do BMP (irrelevante aqui, mas registrar).
  - [ ] objeto aninhado → entidade interna (`innerSchemaNames`), e é assim que agregado vira `EntityType`. **Sutileza:** `innerSchemaNames.add` só ocorre no ramo em que a entidade é **nova** (`:220-221`) — se o nome já existia, não entra.
- [ ] **`infer` de array** (`SchemaInference:227-245`): `singularize(elementName)` no nome do inner (`:233`) e **`LinkedHashSet` para deduplicar** os inners (`:237-242`).
- [ ] **Correção do #8 por construção** (`SchemaInference:204-212`): ao reencontrar uma variação igual, o Java faz `retSchema = foundSchema.get()` e **descarta o `meta` do novo** — a contagem daquela tripla some. Corrigir combinando: `ret_schema.meta.combine_metadata(schema.meta)`. Dispara quando `ArraySC.__eq__` colapsa duas triplas de **tamanho de array diferente** (a única forma de duas triplas distintas do map-reduce virarem "iguais").
- [ ] `innerCountAndTimestampsAdjust` (`:92-123`) — propaga meta das ocorrências-raiz para as internas (que nascem em 0), via `containsSchemaComponent`. O original traz um `FIXME: I'm not sure this will work for n levels of aggregation` (`:94`) — **é do autor, não nosso**; portar como está e catalogar em `bugs_originais.md` se virar divergência.
- [ ] `SchemaInferenceConfig` + `Default*`: `ignored = {"_type"}` e `type_marker = "_type"` (`DefaultSchemaInferenceConfig.java:9,20`) — o `_type` é **marcador e ignorado**, e é por isso que não aparece no modelo final (é o que o `TypesTest` fixa).
- [ ] Testes: `CountTimestampTest`, `ObjectIdTest`, `TypesTest` (bloco B — cortar na tripla, ver 1.6) + **teste novo de array de tamanho variável** afirmando a contagem correta (soma = volume real).

**Saída:** `inference/schema_inference.py` com os 6 passos na ordem do Java e o #8 corrigido.

---

## 1.3 — As estratégias (Guice → wiring por construtor)

> ⚠️ **Contradiz `fase1_nucleo_inferencia.md` §1.3**, que trata as 6 como uma camada
> só. **Elas se dividem em dois grupos por dependência**, e o grupo decide *quando*
> cada uma pode ser escrita: duas operam no nível **raw** (antes do EMF existir), quatro
> operam sobre objetos **PyEcore** (só depois de 1.4 começar). Em Python o Guice
> desaparece: instanciar e passar por construtor (o Java já tem construtor além do `@Inject` —
> `SchemaInference:70`, `USchemaModelBuilder:74`).

### 1.3a — Nível raw (pré-requisito de 1.2)

- [ ] `AliasedAggregatedEntityJoiner` + `Default*` — une entidades-alias via as 10 `AggregateHintWords` (`has`, `with`, `set`, `list`, …), testando `hint+entity` e `entity+hint` com `equalsIgnoreCase` (`DefaultAliasedAggregatedEntityJoiner.java:13-14,21-24`). O `findFirst` (`:26`) tem comentário do autor (`:24`) admitindo que ignorar os demais casamentos "could lead us to some bad-named entities" — **manter**.
- [ ] `EVariationMerger` + `Default*` — laço `do/while` até estabilizar; ao fundir, `updateReferences` + `combineMetadata` + remoção (`DefaultEVariationMerger.java:36-42`). O `walkAndMerge` é uma noção **mais frouxa** que `__eq__` (casa por nome de campo e desce recursivo), e `homogeneousArraysMerge` reconcilia array vazio com não-vazio e concilia lower/upper bounds (`:120-140`).

### 1.3b — Nível EMF/PyEcore (pré-requisito de 1.4)

- [ ] `FeatureAnalyzer` + `Default*` — **é quem realmente marca `optional`**. Reusa `compare_feature` da 0.3 (`DefaultFeatureAnalyzer.java:8,13,17`): calcula os comuns a **todas** as variações e marca opcional o resto (`:21-40`, o `setOptional` na `:39`).
- [ ] `ReferenceMatcherCreator` + `ReferenceMatcher` + `Default*` — só entidades **root** são referenciáveis; cada uma indexada por `{name, pluralize(name), singularize(name)}` (`DefaultReferenceMatcherCreator.java:22,26-27`). É o único uso de `pluralize` no pipeline (confirmado na 0.6).
- [ ] `StructuralVariationSorter` + `Default*` + `Null*` — cascata: se algum `firstTimestamp != 0` → ordena por ele; senão `lastTimestamp`; senão `count`; senão nº de propriedades (`DefaultStructuralVariationSorter.java:16-24`). **Dois defeitos verificados, a catalogar em `bugs_originais.md`:**
  - [ ] **`sortByCount` não ordena** — o `ECollections.sort` está **comentado** (`:40`); só renumera `variationId`. Ou seja, com contagem e sem timestamp, a ordem é a de inserção.
  - [ ] **Comparadores devolvem `-1`/`1`, nunca `0`** (`:28,34,46`) — não são ordem total; para elementos iguais afirmam `>`. Determinismo é load-bearing: replicar com `functools.cmp_to_key` e **fixar a ordem resultante em teste**.
- [ ] `OptionalTagger` + `Default*` + `Null*` — ⚠️ **é código morto no pipeline.** Só `put()` é chamado (`USchemaModelBuilder:127`); `calcOptionality()` (`:134`) e `isOptional()` (`:187`) estão **comentados** no original ("TODO: Remove until recode"). Portar pelo "fiel e completo" (como o `camelCase`/`underscore` do Inflector na 0.6), mas **registrar que não produz saída** — e não gastar teste de equivalência nele.
  - [ ] ⚠️ **Corrigir o mapa de `fase1_nucleo_inferencia.md` §1.6:** o `OptionalTest` valida o **`FeatureAnalyzer`**, não o `OptionalTagger`.

**Saída:** `inference/strategies.py` com as 6 + os `Null*`, cada uma com ≥1 teste isolando seu efeito; `OptionalTest` e `SimplifyAggrTest` portados.

---

## 1.4 — `USchemaModelBuilder.build` + `fillEV`

> Ordem verificada em `USchemaModelBuilder.java:89-148`.

- [ ] `build(factory, name, rawEntities)`: cria `USchema` → por entidade cria `EntityType` com `root = any(variação.isRoot)` (`:105`) → por variação cria `StructuralVariation` com `variationId` a partir de **1**, `count`, timestamps (`:117-121`) → `optTagger.put` → `rmCreator.createReferenceMatcher(entities)` (`:137`) → `fillEV` por variação (`:140-141`) → por entidade `varSorter.sort` + `analyzer.setOptionalProperties` (`:144-148`).
- [ ] `fillEV` (`:176-213`): escalar → `Attribute`; objeto → `Aggregate`; array de objeto → `Aggregate`; campo que casa id → `Reference` via `maybeReference(singularize(key), attr)` (`:194`). Campo chamado **`_id` ganha um `Key`** (`:201-207`).
- [ ] **Bug #7 por construção** (`:255-256`): o Java materializa `inner = sc.getInners().get(0)` **antes** do `if (sc.size() == 0 || ...)` — estoura em array vazio. Em Python, **não indexar `inners[0]` antes do guarda**. (É o patch `0007` do oráculo; aqui é por construção.) O comentário do próprio autor no `:256` já suspeitava: *"si sc.size() == 0 entonces el inner de antes excepciona"*.
- [ ] **`mStructuralVariations` é dict com chave de hash estrutural** (`:124,245,273`) — `ObjectSC`/`ArraySC` como chave. Duas variações estruturalmente iguais colidiriam e o `Aggregate` apontaria para a errada. Confirmar que o merge de 1.2/1.3a garante unicidade **antes** de 1.4 rodar, e cobrir com teste.
- [ ] ⚠️ **`opposite` nunca é setado** — o cálculo inteiro está **comentado** (`:150-172`, "no easy way to infer these"). Então `Reference.opposite` é sempre nulo no oráculo. Não "consertar": o harness da 0.3 compara `opposite` e um porte que o preenchesse divergiria de propósito.
- [ ] Testes: `RelationshipTypeToEntityTypeTest`, `RemovePMapTest` + **teste novo de array vazio** (#7 — nenhum JUnit cobre; é o `privileges` do northwind, o mesmo dado que originou o falso C8).

**Saída:** `inference/builder.py` produzindo `USchema` PyEcore válido, com #7 tratado por construção.

---

## 1.5 — `abstractjson` → JSON nativo (camada que **desaparece**)

> Não é tarefa de porte: é uma **remoção**. O Bridge Jackson/Gson (`IAJAdapter` e as
> ~25 classes de `util/abstractjson/`) existe para abstrair duas libs de JSON; em
> Python a entrada já é `dict` nativo. Elimina uma família inteira de classes.

- [ ] Confirmar que a única perda semântica real é a distinção de `ObjectId` — e que ela está resolvida em **1.0** (senão o #6/`ObjectIdTest` fica sem chão).
- [ ] Registrar a remoção em `bugs_originais.md`/`CLAUDE.md` como desvio **estrutural** deliberado (não altera comportamento observável).

---

## 1.6 — Testes de regressão portados (critério de aceite por módulo)

> Mapa em `INVENTARIO.md`. Bloco A = puro; bloco B = **cortar na tripla** (fixture
> congelada em vez de Mongo + map-reduce).

- [ ] **Gerar as fixtures do bloco B pelo oráculo** (`CountTimestamp.json`, `ObjectIds.json`, `Types.json`, `SimplifyAggr.json` → tripla). A 0.5 está pronta e testada → **desbloqueado**. Gerar pelo oráculo é mais fiel que reconstruir à mão.
  - [ ] ⚠️ **Escolher o caminho de extração por fixture, não um só para todas** (achado da 1.0). Os dois caminhos produzem triplas **diferentes** para o mesmo dado: o Spark emite `ObjectId` como `{"$oid": …}` (vira agregado) e não colapsa array homogêneo; o map-reduce emite `"oid"` (vira `ObjectIdSC`) e colapsa. O `ObjectIdTest` **exige** o map-reduce `v1` (`ObjectIdTest.java:56`) — com fixture do Spark ele falha por motivo errado. O `SimplifyAggrTest`, que afirma sobre o colapso `Aggr{V1,V2,V2…}` → `Aggr{V1,V2}`, idem. Registrar em cada fixture qual caminho a gerou.
- [ ] `J2SchemaSimpleTests` → 1.1 · `OptionalTest` → 1.3b · `RemovePMapTest` → 1.1/1.4 · `RelationshipTypeToEntityTypeTest` → 1.4.
  - [ ] ⚠️ **O `J2SchemaSimpleTests` arrasta dois módulos que a 1.1 não portou** (verificado no fonte, decisão movida da 1.1 para cá):
    - [ ] **`SchemaPrinter`** (`intermediate/raw/util/SchemaPrinter.java`) — no pipeline é código morto (só roda sob `DEBUG_TYPE.DEBUG`, constante em `NO_DEBUG`, `SchemaInference:61,142`), mas o teste afirma sobre a saída de `schemaString` em três casos. Portar **junto com o teste**, não antes: é o único consumidor.
    - [ ] **`RawSchemaGen`** (`main/util/RawSchemaGen.java`) — o teste **não** usa `SchemaInference.infer`; monta a árvore por este construtor separado, que não atribui `entityName`, `meta` nem lê *type marker*, e cujo ramo de array não deduplica. Portar como módulo próprio, sem tentar reaproveitar o `infer`.
    - [ ] ⚠️ Decidir o `<null>` da saída esperada (`"<null>{\"a\": Number } "`): vem de `entityName` nulo impresso pelo Java como `null`; o Python imprimiria `None`. Ou o `schema_string` traduz o nulo, ou o teste portado afirma `<None>` — **registrar a escolha**, é divergência de string literal num teste de regressão.
- [ ] `CountTimestampTest`, `ObjectIdTest`, `TypesTest`, `SimplifyAggrTest` → 1.2/1.3 (bloco B).
- [ ] **Testes que codificam bug** (`INVENTARIO.md`): `ObjectIdTest` → **acrescentar** caso com `_id` não-`ObjectId` afirmando que infere sem estourar (#6); `CountTimestampTest` → **acrescentar** caso com array de tamanho variável afirmando contagem correta (#8); **teste novo** de array vazio (#7).
- [ ] ⚠️ **`OptionalTest` está vermelho no baseline do oráculo** (é 1 dos 11 de `oracle/docker_explain.md`) — o `OptionalTestConfig` do teste não liga `FeatureAnalyzer` (é o bug do patch `#1`, nunca corrigido no original). **Sem Guice, o bug some por construção** → no porte ele deve **passar**. Não tomar o vermelho do oráculo como valor esperado.
- [ ] ⚠️ **`SimplifyAggrTest` não valida o `EVariationMerger`.** `fase1_nucleo_inferencia.md` §1.6 diz "1.2 EVariationMerger" e o `INVENTARIO.md` diz "strategies (1.3)"; **os dois erram**. A simplificação `Aggr{V1,V2,V2,…}` → `Aggr{V1,V2}` é feita pelo **`LinkedHashSet` em `SchemaInference.infer(IAJArray)`** (`:237-242`) — módulo **1.2**. O `SimplifyAggr.json` tem `other_names` de tamanho 1/2/4/6 (array de tamanho variável) → é também dado útil para o **#8**.
- [ ] Marcar tudo como `@pytest.mark.unit` (bloco B deixa de ser integração ao cortar na tripla).

**Saída:** suíte de regressão portada e verde, com os valores **corrigidos** onde houve bug.

---

## 1.7 — Costura + golden-master

- [ ] `BuildUSchema`/`DefaultBuildUSchema` → fachada Python: instanciar as 6 estratégias e injetar por construtor (o wiring que o Guice fazia).
- [ ] Rodar o pipeline completo sobre a tripla do **Northwind** e comparar com `resources/mongodb/model_northwind.xmi` pelo `compare()` da 0.3.
- [ ] **Divergência esperada e desejada:** o oráculo tem o **#8** (deliberadamente sem patch — `oracle/docker_explain.md`), o porte não. As 8 não-fatais em `Orders`/`Purchase_orders` que a 0.5 já registrou são exatamente essa assinatura. **Documentar a diferença como resultado**, não "consertar" para bater.
- [ ] Repetir com `model.xmi` (mínimo MongoDB) e `model_mintest.xmi`.

**Saída:** pipeline ponta a ponta reproduzindo estruturalmente o oráculo, com as divergências de #6/#7/#8 explicadas uma a uma.

---

## ✅ Gate de aceite da Fase 1

- [ ] **Por módulo:** os testes de regressão portados (1.6) passam, com valores corrigidos onde houve bug.
- [ ] **Integração:** o pipeline reproduz **estruturalmente** o XMI-oráculo do Northwind (harness da 0.3), com toda divergência fatal explicada por um bug catalogado.
- [ ] Determinismo coberto por teste: ordem de campos, `__eq__`/`__hash__`, ordem das variações.
- [ ] `ruff` + `mypy --strict` limpos. ⚠️ Lembrar do aviso do `CLAUDE.md`: **o `mypy` não protege nada que atravesse a fronteira do PyEcore** — em 1.4 todo acesso a campo `EObject` precisa ser exercitado por teste ao menos uma vez, inclusive nos caminhos de erro.

**Entregáveis:** `extractors/triple.py` · `intermediate/raw.py` + `metadata.py` · `inference/strategies.py` + `schema_inference.py` + `builder.py` · suíte de regressão portada (`J2SchemaSimple`/`Optional`/`RemovePMap`/`RelationshipTypeToEntityType`/`CountTimestamp`/`ObjectId`/`Types`/`SimplifyAggr` + testes novos de #7/#8 + `__eq__` + por estratégia).

## Riscos da fase

- **Determinismo** (ordem de campos, igualdade estrutural, ordem das variações) é *load-bearing* — divergir num quebra a equivalência. O comparador `-1`/`1` do sorter (1.3b) é o ponto mais escorregadio.
- **`ArraySC.__eq__` ignorando tamanho precisa ser replicado *junto* com a correção do #8** — são duas faces do mesmo ponto: sem a igualdade frouxa o #8 nem dispara.
- **A representação do `ObjectId` na tripla (1.0)** é decisão de contrato entre Fase 1 e Fase 2; errar bloqueia o #6.
- **Ler o `.java` antes de diagnosticar.** O falso `C8` da 0.3 nasceu de diagnosticar o original lendo o nosso porte. As fontes estão em `~/Documents/GitHub/uschema{,-inference}`, nos commits pinados do `oracle/Dockerfile`.
