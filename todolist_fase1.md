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
| **1.1** raw + meta | 1.0 | 1.2, 1.3a | `infer` constrói `ObjectSC`/`ArraySC`; `combineMetadata` NÃO roda no colapso de variações (`:207-211`) — essa ausência é o #8 |
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
- [x] **`ObjectSC.__eq__` = `entityName` + `isRoot` + `inners`** (`ObjectSC.java:33-34`), onde `inners` é **lista ordenada** de pares `(nome, SchemaComponent)` → **a ordem dos campos importa**. `__hash__` = `entityName ^ isRoot ^ inners` (`ObjectSC.java:24`). ⚠️ **Divergência registrada:** no Java esse `hashCode` estoura `NullPointerException` com `entityName` nulo — caso que o `RawSchemaGen` produz; no porte `hash(None)` é válido e não estoura. Guarda faltando, não semântica (mesma família do `I2`), travado por `test_hash_com_entity_name_nulo_nao_estoura`. **A checagem de tipo é `isinstance`, não classe exata** — `ObjectSC.java:31` e `ArraySC.java:86` usam `instanceof`, ao contrário da base (`SchemaComponent.java:8`, `getClass().getName()`); a assimetria é do original e está replicada.
- [x] **`ArraySC.__eq__` ignora o tamanho** (`ArraySC.java:82-101`, com a checagem de `homogeneous_size` **comentada** na `:97` no original). Compara `homogeneous` + `inners`. `__hash__` = `inners` apenas. **É deliberado e é a origem do #8** — replicar junto com o #8 (colapso de variações sem `combine_metadata`, 1.2): são duas faces do mesmo ponto, sem a igualdade frouxa o #8 nem dispara.
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

## 1.2 — `SchemaInference.infer` ✅

> Ordem dos passos verificada em `SchemaInference.java:125-146`. **Não reordenar.**

- [x] `infer(rows)`: `validateRows` (já em 1.0) → `forEach` das triplas → `joiner.joinAggregatedEntities` → `innerCountAndTimestampsAdjust` → `merger.mergeEquivalentEVs`.
- [x] **`infer` recursivo de objeto** (`SchemaInference:176-225`):
  - [x] nome da entidade: se raiz, `capitalize(n["_type"])`; senão `capitalize(elementName)` (`:183,188`).
  - [x] campos **ordenados** e filtrados por `config.ignored_attributes` (`:193-194`, via `TreeSet` na `:194`). Ordenação natural de string do Java = ordem de **code unit UTF-16**; o `sorted()` do Python é code point — divergem só fora do BMP (irrelevante aqui, mas registrado).
  - [x] objeto aninhado → entidade interna (`innerSchemaNames`), e é assim que agregado vira `EntityType`. **Sutileza:** `innerSchemaNames.add` só ocorre no ramo em que a entidade é **nova** (`:220-221`) — se o nome já existia, não entra.
- [x] **`infer` de array** (`SchemaInference:227-245`): `singularize(elementName)` no nome do inner (`:233`) e **`LinkedHashSet` para deduplicar** os inners (`:237-242`, via `dict.fromkeys` no porte).
- [x] **`#8`** — ao reencontrar uma variação igual (`SchemaInference:207-211`), o Java só faz `retSchema = foundSchema.get();`, sem combinar nada. O `meta` inteiro da ocorrência nova (count **e** timestamps) é descartado, não só bounds de array aninhado. Replicado fielmente, sem `combine_metadata` nesse ponto. Travado por teste (`test_bug_8_colapso_descarta_o_meta_inteiro_da_segunda_ocorrencia`, `test_bug_8_tambem_descarta_upper_bounds_do_array_aninhado`).
- [x] `innerCountAndTimestampsAdjust` (`:92-123`) — propaga meta das ocorrências-raiz para as internas (que nascem em 0), via `containsSchemaComponent`. O `FIXME` do autor (`:94`) permanece **não investigado**, catalogado em `bugs_originais.md`. ⚠️ **Achado novo (M2), confirmado por teste:** quando o Joiner funde uma entidade interna com outra existente, ele remove a chave de `rawEntities`, mas `innerSchemaNames` não é atualizado — o passo seguinte estoura (`NullPointerException` no Java, `KeyError` no porte) **toda vez** que o Joiner não é no-op. Replicado fielmente, sem guarda, por decisão explícita. Ver `bugs_originais.md` M2. Em aberto: se Northwind/mintest disparam isso.
- [x] `SchemaInferenceConfig` + `Default*`: `ignored = {"_type"}` e `type_marker = "_type"` (`DefaultSchemaInferenceConfig.java:9,20`) — o `_type` é **marcador e ignorado**, e é por isso que não aparece no modelo final. Portado como constantes de módulo (sem classe — não há `Default*` alternativo, mesmo raciocínio da 1.3a).
- [ ] Testes: `CountTimestampTest`, `ObjectIdTest`, `TypesTest` — **adiado pra 1.6** de propósito (bloco B, precisa cortar na tripla via fixture do oráculo). O **teste novo de array de tamanho variável** afirmando a contagem correta (soma = volume real) já está feito (`test_bug_8_...`).

**Saída:** ✅ `inference/schema_inference.py` (classe `SchemaInference`) com os 6 passos na ordem do Java e o `#8` replicado fielmente: **nenhum** `combine_metadata` roda no colapso de variações — o `meta` inteiro (count+timestamps) da segunda ocorrência é descartado; `tests/unit/test_schema_inference.py` (17 casos). Achados novos catalogados: `#8`, `M2`. `mypy --strict` verificado na máquina do usuário (Python 3.12, `uv run`): limpo.

---

## 1.3 — As estratégias (Guice → wiring por construtor) ✅

> ⚠️ **Contradiz `fase1_nucleo_inferencia.md` §1.3**, que trata as 6 como uma camada
> só. **Elas se dividem em dois grupos por dependência**, e o grupo decide *quando*
> cada uma pode ser escrita: duas operam no nível **raw** (antes do EMF existir), quatro
> operam sobre objetos **PyEcore** (só depois de 1.4 começar). Em Python o Guice
> desaparece: instanciar e passar por construtor (o Java já tem construtor além do `@Inject` —
> `SchemaInference:70`, `USchemaModelBuilder:74`).

### 1.3a — Nível raw (pré-requisito de 1.2) ✅

- [x] `AliasedAggregatedEntityJoiner` + `Default*` — une entidades-alias via as 10 `AggregateHintWords` (`has`, `with`, `set`, `list`, …), testando `hint+entity` e `entity+hint` com `equalsIgnoreCase` (`DefaultAliasedAggregatedEntityJoiner.java:13-14,21-24`). O `findFirst` (`:26`) tem comentário do autor (`:24`) admitindo que ignorar os demais casamentos "could lead us to some bad-named entities" — **manter**. Portado como `join_aggregated_entities`; testes em `test_strategies.py` (prefixo/sufixo de hint, case-insensitive, renomeio, `findFirst` pega a 1ª do dict).
- [x] `EVariationMerger` + `Default*` — laço `do/while` até estabilizar; ao fundir, `updateReferences` + `combineMetadata` + remoção (`DefaultEVariationMerger.java:36-42`). O `walkAndMerge` é uma noção **mais frouxa** que `__eq__` (casa por nome de campo e desce recursivo), e `homogeneousArraysMerge` reconcilia array vazio com não-vazio e concilia lower/upper bounds (`:120-140`). Portado como `merge_equivalent_evs`; testes em `test_strategies.py` (funde por forma ignorando `entity_name`, combina metadata no sobrevivente).
  - [x] ⚠️ **M5 — `homogeneousArraysMerge` indexa array vazio quando os dois lados colapsam vazios** (`:132`). O comentário do autor assume que isso não ocorre; falso quando outro campo do mesmo par reconcilia primeiro (cheio x vazio) e o walk alcança um segundo campo vazio nos dois lados. Confirmado por execução real do Java (JDK 11, fontes do commit pinado). Replicado fielmente (`IndexError`), travado por teste (`test_merge_ambos_vazios_estoura_index_error`). Ver `bugs_originais.md` M5.

### 1.3b — Nível EMF/PyEcore (pré-requisito de 1.4) ✅

- [x] `FeatureAnalyzer` + `Default*` — **é quem realmente marca `optional`**. Reusa `compare_feature` da 0.3 (`DefaultFeatureAnalyzer.java:8,13,17`): calcula os comuns a **todas** as variações e marca opcional o resto (`:21-40`, o `setOptional` na `:39`). Portado como `set_optional_properties` (função, sem estado real).
- [x] `ReferenceMatcherCreator` + `ReferenceMatcher` + `Default*` — só entidades **root** são referenciáveis; cada uma indexada por `{name, pluralize(name), singularize(name)}` (`DefaultReferenceMatcherCreator.java:22,26-27`). É o único uso de `pluralize` no pipeline (confirmado na 0.6). Portado como `ReferenceMatcher` (classe — regex compilados são estado real) + `create_reference_matcher`; `dict.fromkeys` no lugar do `HashSet<String>` das 3 variantes (mesmo raciocínio do `findFirst` do Joiner, 1.3a — determinismo entre processos > fidelidade literal a um `HashSet`).
  - [x] ⚠️ **M6 — chave concatenada crua no regex, sem escape** (`DefaultReferenceMatcher.java:34-50`). Metacaractere de regex no nome da entidade (`.`, `+`, `(`, …) é interpretado como regex, não literal. Confirmado por execução real do Java (JDK 11, fontes do commit pinado): `"a.b"` casa `"aXb_id"`. Replicado fielmente (sem `re.escape`), travado por teste (`test_reference_matcher_m6_chave_com_metacaractere_regex_vira_wildcard`). Ver `bugs_originais.md` M6.
- [x] `StructuralVariationSorter` + `Default*` + `Null*` — cascata: se algum `firstTimestamp != 0` → ordena por ele; senão `lastTimestamp`; senão `count`; senão nº de propriedades (`DefaultStructuralVariationSorter.java:16-24`). **Dois defeitos verificados, catalogados em `bugs_originais.md`:**
  - [x] **M3 — `sortByCount` não ordena** — o `ECollections.sort` está **comentado** (`:40`); só renumera `variationId`. Ou seja, com contagem e sem timestamp, a ordem é a de inserção. Replicado (não corrigido) e travado por teste (`test_sort_m3_ramo_de_count_nao_ordena_so_renumera`).
  - [x] **M4 — comparadores devolvem `-1`/`1`, nunca `0`** (`:28,34,46`) — não são ordem total; para elementos iguais afirmam `>`. Replicado com `functools.cmp_to_key`; a ordem resultante entre "iguais" é fixada em teste (não a mesma coisa que dizer que é estável/previsível).
- [x] `OptionalTagger` + `Default*` + `Null*` — ⚠️ **é código morto no pipeline.** Só `put()` é chamado (`USchemaModelBuilder:127`); `calcOptionality()` (`:134`) e `isOptional()` (`:187`) estão **comentados** no original ("TODO: Remove until recode"). Portado pelo "fiel e completo" (como o `camelCase`/`underscore` do Inflector na 0.6) como classe `OptionalTagger` (+ `NullOptionalTagger`), com nota explícita de código morto na docstring — **sem** teste de equivalência com o oráculo, só testes unitários isolando o efeito.
  - [x] ⚠️ **Corrigir o mapa de `fase1_nucleo_inferencia.md` §1.6:** o `OptionalTest` valida o **`FeatureAnalyzer`**, não o `OptionalTagger`. **Feito** (junto da 1.6) — corrigido também o `SimplifyAggrTest` (é o `LinkedHashSet` da 1.2, não o `EVariationMerger`).

**Saída:** ✅ `inference/strategies.py` ganhou `set_optional_properties`, `ReferenceMatcher`/`create_reference_matcher`, `sort_structural_variations`/`null_sort_structural_variations`, `OptionalTagger`/`NullOptionalTagger`; `tests/unit/test_strategies_emf.py` (18 casos, `EObject` montados via API reflexiva do PyEcore, mesmo estilo de `test_equivalence.py`). Achados novos catalogados: **M3**, **M4**, **M6**. `OptionalTest`/`SimplifyAggrTest` (JUnit) continuam **adiados pra 1.6** de propósito (cortar na tripla via fixture do oráculo), mesmo padrão da 1.2/1.3a.

> ⚠️ **Achado de ambiente (não é bug do porte):** a partir desta fase, `strategies.py` importa `compare_feature` de `validation/equivalence.py`, que importa `enum.StrEnum` (Python 3.11+). No sandbox de IA usado pra desenvolver (Python 3.10) isso quebra a **coleção** de qualquer teste que toque em `strategies.py` — inclusive os da 1.2/1.3a, que antes rodavam ali. Contornado *só pra rodar a suíte naquele ambiente* com um shim local que injeta `enum.StrEnum` no processo do `pytest` (não é código do repo).
>
> **Verificado na máquina do usuário (2026-07-21, Python 3.12, `uv run`):**
> `mypy .` → `Success: no issues found in 26 source files`; `pytest -q` → `467 passed`
> (os 100 a mais que no sandbox de IA são `test_equivalence.py`, que só roda
> com Python 3.11+). Os 23 erros que o `mypy --strict` acusou na primeira
> rodada eram só falta de `assert isinstance(...)`/anotação explícita nos
> pontos onde `ObjectSC.entity_name`/`.meta` (`str | None`/`ObjectMetadata |
> None` na classe) ou o tipo base `SchemaComponent` não davam pro mypy provar
> o que já era verdade em runtime — sem nenhuma mudança de comportamento
> (mesmos 367/467 testes, mesmos resultados, antes e depois do ajuste). Não é
> nem fidelidade nem infidelidade ao Java: o Java não tem esse problema porque
> `Optional.orElse(...)` já devolve tipo não-nulo garantido — não entra em
> `bugs_originais.md`.

---

## 1.4 — `USchemaModelBuilder.build` + `fillEV` ✅

> Ordem verificada em `USchemaModelBuilder.java:89-148`.

- [x] `build(factory, name, rawEntities)`: cria `USchema` → por entidade cria `EntityType` com `root = any(variação.isRoot)` (`:105`) → por variação cria `StructuralVariation` com `variationId` a partir de **1**, `count`, timestamps (`:117-121`) → `optTagger.put` → `rmCreator.createReferenceMatcher(entities)` (`:137`) → `fillEV` por variação (`:140-141`) → por entidade `varSorter.sort` + `analyzer.setOptionalProperties` (`:144-148`). O `factory` do EMF **sai da assinatura**: na API reflexiva do PyEcore a factory é o próprio `EPackage` (`pkg.getEClassifier(...)()`), passado ao construtor.
- [x] `fillEV` (`:176-213`): escalar → `Attribute`; objeto → `Aggregate`; array de objeto → `Aggregate`; campo que casa id → `Reference` via `maybeReference(singularize(key), attr)` (`:194`). Campo chamado **`_id` ganha um `Key`** (`:201-207`). O `evName` do Java **fica na assinatura** por fidelidade, sem uso vivo — o único consumidor (`optTagger.isOptional`, `:187`) é código morto, como o resto do `OptionalTagger`.
- [x] **Bug #7 por construção** (`:255-256`): o Java materializa `inner = sc.getInners().get(0)` **antes** do `if (sc.size() == 0 || ...)` — estoura em array vazio. Em Python, **não indexar `inners[0]` antes do guarda**. (É o patch `0007` do oráculo; aqui é por construção.) O comentário do próprio autor no `:256` já suspeitava: *"si sc.size() == 0 entonces el inner de antes excepciona"*. Travado por `test_feature_from_array_vazio_nao_estoura_bug_7` e `test_build_array_vazio_ponta_a_ponta_nao_estoura`.
- [x] **`mStructuralVariations` é dict com chave de hash estrutural** (`:124,245,273`) — `ObjectSC`/`ArraySC` como chave, portado assim no builder. **A verificação de que o merge de 1.2/1.3a garante unicidade antes de 1.4 rodar foi movida pra 1.7** — é propriedade da 1.2→1.4 costuradas, não do builder isolado.
- [x] ⚠️ **`opposite` nunca é setado** — o cálculo inteiro está **comentado** (`:150-172`, "no easy way to infer these"). Então `Reference.opposite` é sempre nulo no oráculo. Não "consertar": o harness da 0.3 compara `opposite` e um porte que o preenchesse divergiria de propósito.
- [x] ⚠️ **P1 — `EOrderedSet` do PyEcore não tem `.sort()` (achado de plataforma, não bug do Java).** `entity.getVariations()` é uma `EList` no Java, e o `DefaultStructuralVariationSorter` chama `ECollections.sort(...)`, que ordena a **coleção EMF** no lugar. No PyEcore a coleção equivalente é um `EOrderedSet`, que **não expõe `.sort()`** — e o `sort_structural_variations` (1.3b) opera sobre `list`. Ordenar só uma cópia deixaria o `variationId` renumerado certo mas a **ordem da coleção** (o que sai no XMI e o que o harness da 0.3 compara) na de inserção. O builder faz a ponte: `list(...)` → `var_sorter` → `clear()` + `extend(...)` reescrevendo a ordem de volta. Não é fidelidade nem infidelidade ao Java — é diferença de API entre EMF e PyEcore, do mesmo tipo do aviso de `mypy` da 1.3. Travado por `test_build_reordena_a_colecao_emf_nao_so_o_id`.
- [x] Testes: **`test_builder.py` (31 casos)** — cada método isolado + `build` ponta a ponta, com todo acesso a campo `EObject` exercitado (a rede da fronteira PyEcore: pegou em execução os typos `entitties`/`Attribue`/`upperBouund` e o `referenced.eClass` no lugar de `referenced.type.eClass`, nenhum visível ao `mypy`). Inclui o **teste novo de array vazio** (#7 — nenhum JUnit cobre; é o `privileges` do northwind, o mesmo dado que originou o falso C8). `RelationshipTypeToEntityTypeTest`/`RemovePMapTest` (JUnit) seguem **adiados pra 1.6** (bloco B, cortar na tripla via fixture do oráculo), mesmo padrão da 1.2/1.3.

**Saída:** ✅ `inference/builder.py` produzindo `USchema` PyEcore válido, com #7 tratado por construção; `tests/unit/test_builder.py` (31 casos). Achado novo catalogado: **P1** (`EOrderedSet` sem `.sort()`). `ruff`/`mypy --strict` limpos; suíte inteira verde (501 casos).

---

## 1.4b — `m2m/USchemaToDocumentDb` (achado da 1.6, **não estava no roadmap**)

> ⚠️ **Sub-fase nova, descoberta ao portar os testes da 1.6.** O `INVENTARIO.md`
> mapeava `RemovePMapTest → 1.1/1.4` e `RelationshipTypeToEntityTypeTest → 1.4`;
> **os dois estão errados** (inferência pelo nome do teste, sem abrir o `.java` — o
> mesmo erro circular do falso C8). Ambos testam
> `es.um.uschema.doc2uschema.m2m.USchemaToDocumentDb.adaptToDocumentDb`, uma
> transformação **model-to-model** que roda **depois** do `USchemaModelBuilder`, e
> que o roadmap da Fase 1 **não lista em lugar nenhum**. Corrigido no `INVENTARIO.md`.

- [x] Portar `USchemaToDocumentDb.adaptToDocumentDb` (`m2m/USchemaToDocumentDb.java`) — `inference/m2m.py`, os quatro métodos:
  - [x] **`adapt_to_document_db`** (`:49-69`) — coleta todos os `RelationshipType` e `Attribute` de `PMap` (as duas coleções via `itertools.chain`), depois aplica relTypes **antes** dos maps. Coleta-antes-de-transformar é load-bearing.
  - [x] **`_rel_type_to_entity_type`** (`:78-155`) — `RelationshipType` → `EntityType` com prefixo `Ref_`. Monta `l_references` (as `Reference` decoradas por este rel via `isFeaturedBy`, casadas por **identidade**), embute os atributos da aresta na variação de origem (com `_deep_copy` + `_id` sintético `ObjectId`), reaponta as refs e move as variações — CASO A (entidade nova, leva tudo) vs CASO B (colisão de nome: dedup por `compare_variation` + renumeração contínua).
  - [x] **`_remove_pmap`** (`:166-220`) — `_remove_pmap`. Find-or-create em dois níveis (entidade `Map_<Attr>` por **nome**, variação `{key,value}` por **estrutura** via `compare_variation`), troca do `PMap` por `Aggregate` no container (`eContainer()`), e recursão em `PMap` de `PMap`.
  - [x] **`_deep_copy`** — substitui o `EcoreUtil.copy` (`:104`), inexistente no PyEcore (`EcoreUtils.copy` não existe; `copy.deepcopy` estoura `BadValueError`). **Cópia genérica**, percorrendo as `eAllStructuralFeatures()` do metamodelo — sem ramo por tipo, igual ao que o `EcoreUtil.copy` faz por dentro. Três regras: `EAttribute` → copia o valor; `EReference` de containment → copia recursivo; `EReference` **não**-containment → pula.
    - [x] ⚠️ **Por que pular não-containment:** essas features têm `eOpposite`, então atribuí-las na cópia **muta o original** — `copia.key = orig.key` insere a cópia em `Key.attributes` do `Key` original (verificado: lista vai de 1 para 2). O Java evita o mesmo com o `Copier`, que remapeia refs internas à árvore copiada e deixa as externas de fora.
    - [x] ~~**DÉBITO TÉCNICO** — cobria só `PrimitiveType`, composto estourava `AttributeError`~~ **PAGO.** A primeira versão hardcodava o tipo; a versão genérica cobre `PrimitiveType`, `PList`/`PSet`, `PMap` (inclusive aninhado) e `PTuple`, validado caso a caso. O porte deixou de estar menos completo que o original neste ponto.
- [x] Portar `RemovePMapTest` (3 casos) e `RelationshipTypeToEntityTypeTest` (4 casos) — versionados em `tests/regression/test_remove_pmap.py` e `test_relationship_type_to_entity_type.py`, todos verdes. Os `USchema` de entrada são montados na própria classe de teste (como o JUnit), sem Mongo nem inferência.
- [x] **Escopo/prioridade decidido:** a 1.4b foi portada **agora**, junto da 1.6, em vez de adiada. O módulo roda ponta a ponta (`adapt_to_document_db` sobre schema com `RelationshipType` + `PMap` juntos → `Ref_`/`Map_` + `relationships` vazio), mesmo que no fluxo Mongo→U-Schema atual ele seja quase no-op — fica pronto pro paradigma-grafo (Fase 2/3) sem retrabalho.

**Saída:** ✅ `inference/m2m.py` completo (4 métodos), `tests/regression/` com os 2 JUnit portados (7 casos). `ruff`/`mypy --strict` limpos; suíte inteira verde (515). Achado que originou a sub-fase (`INVENTARIO` mapeava os 2 testes no builder) registrado em `INVENTARIO.md`/`README.md`.

---

## 1.5 — `abstractjson` → JSON nativo (camada que **desaparece**) ✅

> Não é tarefa de porte: é uma **remoção**. O Bridge Jackson/Gson (`IAJAdapter` e as
> ~25 classes de `util/abstractjson/`) existe para abstrair duas libs de JSON; em
> Python a entrada já é `dict` nativo. Elimina uma família inteira de classes.

- [x] Confirmar que a única perda semântica real é a distinção de `ObjectId` — e que ela está resolvida em **1.0** (senão o #6/`ObjectIdTest` fica sem chão). **Verificado no fonte** (commit pinado): a decisão de tipo do Bridge é o `IAJIdentify` com 7 predicados (`isObject`/`isArray`/`isBoolean`/`isNumber`/`isNull`/`isTextual`/`isObjectId`), consumidos em `SchemaInference.infer:150-168`. Seis são triviais sobre `dict`/`list` nativo e estão em `triple.py::classify` (mesma ordem, `BOOLEAN` antes de `NUMBER`); só `isObjectId` não sai de graça, e é o `value == "oid"` resolvido na 1.0.
- [x] Registrar a remoção em `bugs_originais.md`/`CLAUDE.md` como desvio **estrutural** deliberado (não altera comportamento observável). Feito: bullet em `bugs_originais.md` ("O que não é defeito") com a verificação dos 7 predicados, e nota em `CLAUDE.md` ("Project-specific notes") no padrão da nota do Inflector ("não reintroduzir por completude").

**Saída:** ✅ camada `abstractjson` confirmada como removível sem perda semântica (só o `ObjectId`, coberto na 1.0) e a remoção registrada nos dois docs de fidelidade. Nenhum código novo — é desvio estrutural, não porte.

---

## 1.6 — Testes de regressão portados (critério de aceite por módulo)

> Mapa em `INVENTARIO.md`. Bloco A = puro; bloco B = **cortar na tripla** (fixture
> congelada em vez de Mongo + map-reduce).

- [ ] **Gerar as fixtures do bloco B pelo oráculo** (`CountTimestamp.json`, `ObjectIds.json`, `Types.json`, `SimplifyAggr.json` → tripla). A 0.5 está pronta e testada → **desbloqueado**. Gerar pelo oráculo é mais fiel que reconstruir à mão.
  - [ ] ⚠️ **Escolher o caminho de extração por fixture, não um só para todas** (achado da 1.0). Os dois caminhos produzem triplas **diferentes** para o mesmo dado: o Spark emite `ObjectId` como `{"$oid": …}` (vira agregado) e não colapsa array homogêneo; o map-reduce emite `"oid"` (vira `ObjectIdSC`) e colapsa. O `ObjectIdTest` **exige** o map-reduce `v1` (`ObjectIdTest.java:56`) — com fixture do Spark ele falha por motivo errado. O `SimplifyAggrTest`, que afirma sobre o colapso `Aggr{V1,V2,V2…}` → `Aggr{V1,V2}`, idem. Registrar em cada fixture qual caminho a gerou.
- [x] `OptionalTest` → 1.3b **(portado, `tests/regression/test_optional.py`)** · ⚠️ `RemovePMapTest`/`RelationshipTypeToEntityTypeTest` → **movidos pra 1.4b** (testam `m2m.USchemaToDocumentDb`, não o builder — ver INVENTARIO) · `J2SchemaSimpleTests` → 1.1 (pendente, precisa de `SchemaPrinter`+`RawSchemaGen`).
  - [ ] ⚠️ **O `J2SchemaSimpleTests` arrasta dois módulos que a 1.1 não portou** (verificado no fonte, decisão movida da 1.1 para cá):
    - [ ] **`SchemaPrinter`** (`intermediate/raw/util/SchemaPrinter.java`) — no pipeline é código morto (só roda sob `DEBUG_TYPE.DEBUG`, constante em `NO_DEBUG`, `SchemaInference:61,142`), mas o teste afirma sobre a saída de `schemaString` em três casos. Portar **junto com o teste**, não antes: é o único consumidor.
    - [ ] **`RawSchemaGen`** (`main/util/RawSchemaGen.java`) — o teste **não** usa `SchemaInference.infer`; monta a árvore por este construtor separado, que não atribui `entityName`, `meta` nem lê *type marker*, e cujo ramo de array não deduplica. Portar como módulo próprio, sem tentar reaproveitar o `infer`.
    - [ ] ⚠️ Decidir o `<null>` da saída esperada (`"<null>{\"a\": Number } "`): vem de `entityName` nulo impresso pelo Java como `null`; o Python imprimiria `None`. Ou o `schema_string` traduz o nulo, ou o teste portado afirma `<None>` — **registrar a escolha**, é divergência de string literal num teste de regressão.
- [ ] `CountTimestampTest`, `ObjectIdTest`, `TypesTest`, `SimplifyAggrTest` → 1.2/1.3 (bloco B).
  - [x] **`TypesTest`** (`tests/regression/test_types.py`) — asserção é count-independente (nenhum `_type` vaza), fixture reconstruída à mão do `Types.json` + `_type` do map-reduce v1 (raiz **e** aninhado). Seguro sem oráculo.
  - [x] **`ObjectIdTest`** (`tests/regression/test_objectid.py`) — asserção é de **tipo** (`_id` → `PrimitiveType "ObjectId"`), count-independente, fixture com a sentinela v1 `"oid"`. Inclui o caso #6 (abaixo).
  - [ ] **`CountTimestampTest`, `SimplifyAggrTest`** — asserção **é a contagem** (variações/counts), depende da agregação exata do map-reduce → **exigem fixture gerada pelo oráculo** (Docker). Não reconstruir à mão: passaria por motivo errado.
- [ ] **Testes que codificam bug** (`INVENTARIO.md`): ~~`ObjectIdTest` → acrescentar caso com `_id` não-`ObjectId` (#6)~~ **feito** (`test_id_nao_objectid_infere_sem_estourar`); ~~array vazio (#7)~~ **feito na 1.4** (`test_feature_from_array_vazio_...`); `CountTimestampTest` → **acrescentar** caso do #8 (count da 2ª ocorrência some no colapso) — pendente, junto da fixture do oráculo. (O #8 já tem cobertura em `test_schema_inference.py`.)
- [x] ⚠️ **`OptionalTest` está vermelho no baseline do oráculo** — o `OptionalTestConfig` não liga `FeatureAnalyzer` (bug do patch `#1`). **Sem Guice, o bug some por construção** → no porte **passa**. Afirmado o valor corrigido em `test_optional.py` (docstring registra a divergência).
- [ ] ⚠️ **`SimplifyAggrTest` não valida o `EVariationMerger`.** `fase1_nucleo_inferencia.md` §1.6 diz "1.2 EVariationMerger" e o `INVENTARIO.md` diz "strategies (1.3)"; **os dois erram**. A simplificação `Aggr{V1,V2,V2,…}` → `Aggr{V1,V2}` é feita pelo **`LinkedHashSet` em `SchemaInference.infer(IAJArray)`** (`:237-242`) — módulo **1.2**. O `SimplifyAggr.json` tem `other_names` de tamanho 1/2/4/6 (array de tamanho variável) → é também dado útil para o **#8**.
- [x] Marcar tudo como `@pytest.mark.unit` (bloco B deixa de ser integração ao cortar na tripla) — feito nos três portados.

**Saída (parcial):** ✅ portados e verdes: `OptionalTest` (3 casos), `TypesTest` (2), `ObjectIdTest` (2, inclui #6) — `tests/regression/`. **Pendentes, com pré-requisito:** `CountTimestamp`/`SimplifyAggr` (fixture do oráculo Docker); `J2SchemaSimpleTests` (portar `SchemaPrinter`+`RawSchemaGen`); `RemovePMap`/`RelationshipType` (1.4b — `USchemaToDocumentDb`).

---

## 1.7 — Costura + golden-master

- [ ] `BuildUSchema`/`DefaultBuildUSchema` → fachada Python: instanciar as 6 estratégias e injetar por construtor (o wiring que o Guice fazia).
- [ ] Rodar o pipeline completo sobre a tripla do **Northwind** e comparar com `resources/mongodb/model_northwind.xmi` pelo `compare()` da 0.3.
- [ ] **Divergência esperada e desejada:** o oráculo tem o **#8** (deliberadamente sem patch — `oracle/docker_explain.md`), o porte não. As 8 não-fatais em `Orders`/`Purchase_orders` que a 0.5 já registrou são exatamente essa assinatura. **Documentar a diferença como resultado**, não "consertar" para bater.
- [ ] Repetir com `model.xmi` (mínimo MongoDB) e `model_mintest.xmi`.
- [ ] **Unicidade das chaves de `mStructuralVariations`** (movido da 1.4). O builder indexa variações por hash estrutural (`ObjectSC`/`ArraySC` como chave, `builder.py`); duas variações estruturalmente iguais colidiriam e o `Aggregate` apontaria pra errada. A garantia de que isso não ocorre é do merge de 1.2/1.3a rodado **antes** do `build` — propriedade da costura, não do builder isolado. Cobrir com teste de integração aqui (a colisão só é observável no pipeline completo, com entidades reais do Northwind/mintest).

---

## ✅ Gate de aceite da Fase 1

- [ ] **Por módulo:** os testes de regressão portados (1.6) passam, com valores corrigidos onde houve bug.
- [ ] **Integração:** o pipeline reproduz **estruturalmente** o XMI-oráculo do Northwind (harness da 0.3), com toda divergência fatal explicada por um bug catalogado.
- [ ] Determinismo coberto por teste: ordem de campos, `__eq__`/`__hash__`, ordem das variações.
- [ ] `ruff` + `mypy --strict` limpos. ⚠️ Lembrar do aviso do `CLAUDE.md`: **o `mypy` não protege nada que atravesse a fronteira do PyEcore** — em 1.4 todo acesso a campo `EObject` precisa ser exercitado por teste ao menos uma vez, inclusive nos caminhos de erro.

**Entregáveis:** `extractors/triple.py` · `intermediate/raw.py` + `metadata.py` · `inference/strategies.py` + `schema_inference.py` + `builder.py` · suíte de regressão portada (`J2SchemaSimple`/`Optional`/`RemovePMap`/`RelationshipTypeToEntityType`/`CountTimestamp`/`ObjectId`/`Types`/`SimplifyAggr` + testes novos de #7/#8 + `__eq__` + por estratégia).

## Riscos da fase

- **Determinismo** (ordem de campos, igualdade estrutural, ordem das variações) é *load-bearing* — divergir num quebra a equivalência. O comparador `-1`/`1` do sorter (1.3b) é o ponto mais escorregadio.
- **`ArraySC.__eq__` ignorando tamanho precisa ser replicado *junto* com o #8** (colapso de variações sem `combine_metadata`) — são duas faces do mesmo ponto: sem a igualdade frouxa o #8 nem dispara.
- **A representação do `ObjectId` na tripla (1.0)** é decisão de contrato entre Fase 1 e Fase 2; errar bloqueia o #6.
- **Ler o `.java` antes de diagnosticar.** O falso `C8` da 0.3 nasceu de diagnosticar o original lendo o nosso porte. As fontes estão em `~/Documents/GitHub/uschema{,-inference}`, nos commits pinados do `oracle/Dockerfile`.
