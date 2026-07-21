# Fase 1 — Núcleo de inferência (`doc2uschema`) · a espinha (guia detalhado)

**Parte de:** `roadmap_portabilidade.md` · **Validação:** `roteiro_experimental.md` · **Base técnica:** `analise_ferramenta_uschema.md` (§3.5, pipeline)
**Entregável:** núcleo de inferência `doc2uschema` · **Pré-requisito:** Fase 0 (PyEcore + harness)

## Objetivo

Reimplementar em Python, fielmente, o núcleo de inferência do U-Schema — a parte que **não depende de Spark** e que transforma assinaturas estruturais agregadas no modelo U-Schema. É o maior bloco do porte e o que carrega a fidelidade.

## Contrato de entrada (a costura com a Fase 2)

O núcleo **não recebe documentos crus**. Recebe uma lista de triplas `{schema, count, firstTimestamp, lastTimestamp}`, onde `schema` é a assinatura estrutural já agregada e `count` é quantos documentos têm aquela forma. É exatamente o que o extrator (Fase 2) produz. Por isso as duas fases podem ser desenvolvidas **em paralelo**, encontrando-se neste formato. No cenário relacional→NoSQL, os timestamps entram com valor padrão.

---

## 1.1 Modelos intermediários → `dataclasses`

**`intermediate/raw` (Composite):** `SchemaComponent` (base), `ObjectSC`, `ArraySC`, `StringSC`, `NumberSC`, `BooleanSC`, `NullSC`, `ObjectIdSC`. **`intermediate/firsto`:** `MultiValued`, `NumberWithRangeSC`, `Ranged`, `StringMultiValuedSC`.

**Tarefas:**
- [ ] Portar a hierarquia `raw` como `dataclasses` (árvore recursiva; `ObjectSC` contém features nomeadas; `ArraySC` contém `inners`).
- [ ] Replicar **fielmente a semântica de igualdade**: o `SchemaComponent.equals` base compara por nome de classe; as subclasses refinam. **Ponto crítico:** `ArraySC.equals` **ignora o tamanho do array** (decisão deliberada do autor) — isto é *load-bearing* e está na origem do bug #8. Replicar via `__eq__`/`__hash__` que reproduzam a mesma noção de igualdade estrutural.
- [ ] Portar `ObjectSC.meta` (count/timestamps) e o método `combineMetadata` — usado em `innerCountAndTimestampsAdjust` (`SchemaInference.java:100-104`). **Não** é chamado ao reencontrar uma variação igual em `infer` (`:207-211`): ali o original só faz `retSchema = foundSchema.get();`, sem combinar nada — o `meta` inteiro (count+timestamps) da ocorrência nova é descartado. Ver `bugs_originais.md` #8.

> **Atenção:** se a igualdade estrutural do Python divergir da do Java (ordem de campos, tratamento de tipos), variações que deveriam colapsar não colapsam (ou vice-versa) e o XMI não bate com o oráculo. Cobrir com testes unitários de `__eq__` desde já.

## 1.2 `SchemaInference.infer` (Fase 1 do pipeline interno)

Produz `Map<entidade, List<SchemaComponent>>`. Passos:

1. **`validateRows`** — checar o formato das triplas.
2. **`infer` recursivo** — percorrer cada assinatura JSON construindo a árvore `SchemaComponent`. Comportamentos a replicar: **campos em ordem** (canonização via conjunto ordenado); **atributos ignorados** filtrados (`config.getIgnoredAttributes`); **objetos aninhados** registrados como entidades internas (`innerSchemaNames`) → é assim que um agregado vira `EntityType`; nome-raiz capitalizado pelo Inflector.
3. **Colapso de variações** — ao reconhecer uma forma igual a uma variação existente, reutilizá-la. **Replicar fielmente:** o original **não** combina `meta` nenhum aqui (`SchemaInference.java:207-211` — só `retSchema = foundSchema.get();`). O `meta` inteiro (count+timestamps, e por consequência qualquer array aninhado com seu `upper_bounds`) da ocorrência nova é descartado — bug **#8**, ver `bugs_originais.md`. **Não** chamar `combine_metadata` neste ponto do porte.
4. **`joiner.joinAggregatedEntities(rawEntities, innerSchemaNames)`** — unir entidades-alias do mesmo agregado.
5. **`innerCountAndTimestampsAdjust`** — propagar count/timestamps das ocorrências-raiz para as entidades internas (que nascem com 0).
6. **`merger.mergeEquivalentEVs(rawEntities)`** — fundir variações estruturalmente equivalentes que ficaram separadas.

**Tarefas:** portar 1→6 mantendo a **ordem** das etapas; cobrir o caso de array de tamanho variável com teste (bug #8); cobrir o caso de objeto aninhado → entidade interna.

## 1.3 As estratégias (Strategy + Null Object; Guice → wiring)

Cada uma é peça obrigatória do "fiel e completo". Em Python, o **Guice desaparece**: instancia-se cada estratégia e passa-se por construtor (as classes já têm construtor além do `@Inject`).

| Estratégia (interface / `Default*`) | Método público | Papel |
|---|---|---|
| `AliasedAggregatedEntityJoiner` | `joinAggregatedEntities(...)` | une entidades-alias do mesmo agregado |
| `EVariationMerger` | `mergeEquivalentEVs(...)` | funde variações equivalentes |
| `OptionalTagger` (+`Null...`) | `put(...)`, `calcOptionality(...)`, `isOptional(...)` | bookkeeping de presença de features para opcionalidade |
| `FeatureAnalyzer` | `setOptionalProperties(...)` | marca opcional toda feature ausente de ≥1 variação |
| `ReferenceMatcher` | `maybeMatch(id) → Optional<T>` | decide se um campo é `Reference` (casamento de id) |
| `ReferenceMatcherCreator` | `createReferenceMatcher(entities) → ReferenceMatcher<EntityType>` | constrói o matcher sobre entidades referenciáveis |
| `StructuralVariationSorter` (+`Null...`) | `sort(...)` | ordem determinística das variações |

**Tarefas:** portar cada estratégia como classe/`Protocol` Python; reproduzir o `Default*`; manter os `Null*` (no-op) como opção configurável; cada uma com ≥1 teste isolando seu efeito.

## 1.4 `USchemaModelBuilder.build` + `fillEV` (Fase 2 do pipeline interno)

Converte as árvores `raw` no modelo EMF (via PyEcore). Passos:

1. Criar `USchema`; por entidade criar `EntityType` (flag `root` se alguma variação for raiz) e, por variação, `StructuralVariation` com `variationId`, `count`, timestamps; registrar no `optTagger`.
2. `refMatcher = rmCreator.createReferenceMatcher(entities)` — apenas entidades com pelo menos uma variação raiz são referenciáveis.
3. **`fillEV`** por variação: campo escalar → `Attribute`; objeto/array de objetos → `Aggregate`; campo cujo valor casa com id de outra entidade → `Reference` (via `refMatcher`). **Atenção (origem do bug #7):** ao tratar `ArraySC`, **checar `size()==0` antes de acessar o primeiro inner** — em Python, idem (não indexar `inners[0]` num array vazio).
4. Por entidade: `varSorter.sort(...)` e `analyzer.setOptionalProperties(...)`.

**Tarefas:** portar `build` e `fillEV` usando os objetos PyEcore da Fase 0; tratar array vazio por construção (bug #7); validar que `Aggregate` aninhado (ex.: `Detail` em `Orders`) sai correto.

## 1.5 `abstractjson` → JSON nativo

O `abstractjson` (Bridge Jackson/Gson, `IAJAdapter`) **desaparece** no Python: a assinatura de entrada já é `dict`/estrutura nativa, então não há biblioteca de JSON a abstrair. Remover essa camada simplifica o porte e elimina uma família inteira de classes.

---

## 1.6 Validação módulo a módulo: portar os testes de regressão Java

O critério de aceite **por módulo** não é só o oráculo do Northwind no fim — é a **suíte de regressão JUnit que já existe** no repositório, portada para Python. Cada teste fixa o comportamento esperado de um caso minúsculo e **localiza** o erro no módulo certo, antes de qualquer rodada ponta a ponta. Mapeamento test → módulo:

| Teste JUnit (Java) | Módulo do porte | O que fixa |
|---|---|---|
| `CountTimestampTest` | 1.2 `infer` / propagação de meta | count/timestamp por variação; em não-raiz, copiados do pai (**área do #8**) |
| `ObjectIdTest` | 1.2 `infer` / tipos | distinguir ObjectId de String (não inferir como aggregate) (**área do #6**) |
| `TypesTest` | 1.2 / 1.4 | inferência de tipos primitivos |
| `OptionalTest` | 1.3 `OptionalTagger`/`FeatureAnalyzer` | opcionalidade entre variações |
| `SimplifyAggrTest` | 1.2 `EVariationMerger` | simplificação/merge de agregados equivalentes |
| `RelationshipTypeToEntityTypeTest` | 1.4 `build`/`fillEV` | distinção referência × relacionamento |
| `RemovePMapTest` | 1.1 / 1.4 | remoção de PMap |
| (`InflectorTest`) | Fase 0 (Inflector) | capitalização/pluralização |
| (`SimplificationTest`, `PairOperationsTest` — Mongo) | Fase 2 (extrator) | simplificação e operações de par |

Os dados de teste (`testSources/*.json`) vêm junto — reaproveitar.

> **Onde você corrigiu um bug, ajuste a asserção.** Porte a *estrutura* do teste, mas afirme o valor **corrigido** (#6/#7). O #8 dispara em qualquer entidade cujas variações colapsem (não precisa de array): vale **acrescentar** um teste novo confirmando que `count`/`timestamps` da segunda ocorrência somem por completo (não sejam somados) — fiel ao original, não um valor a "corrigir".

**Tarefas:** para cada módulo abaixo, portar seu teste de regressão correspondente **antes ou junto** com o módulo (estilo test-alongside); rodar a suíte JUnit original no Docker (Fase 0) para confirmar os valores esperados; acrescentar o teste novo de contagem para o #8.

## Ordem de porte sugerida (bottom-up, test-alongside)

1. `raw`/`firsto` (`dataclasses` + igualdade estrutural) → testes de `__eq__` (+ `RemovePMapTest`).
2. `infer` recursivo (replicando o colapso de variações **sem** `combineMetadata` — bug #8) → portar `CountTimestampTest`, `ObjectIdTest`, `TypesTest` + teste novo confirmando que `meta` da segunda ocorrência é descartado no colapso.
3. Estratégias (uma a uma, com testes isolados) → portar `OptionalTest`, `SimplifyAggrTest`.
4. `USchemaModelBuilder.build` + `fillEV` → portar `RelationshipTypeToEntityTypeTest`; produzir o XMI via PyEcore.
5. Costurar tudo em `SchemaInference` (wiring das estratégias) → golden-master de dataset (Northwind) pelo harness.

## Gate de aceite da Fase 1

Dois níveis: (a) **por módulo** — os testes de regressão portados (§1.6) passam, com os valores corrigidos onde houve bug; (b) **integração** — o pipeline completo reproduz **estruturalmente** o XMI-oráculo do Northwind (e dos casos mínimos), conferido pelo harness da Fase 0. Quando divergir, o teste de regressão localiza o módulo e o harness aponta a categoria (entidade / variação / feature / contagem).

## Entregáveis

`raw.py` + `firsto.py` (modelos intermediários), `strategies.py` (as 6 estratégias + `Null*`), `inference.py` (`SchemaInference`), `builder.py` (`USchemaModelBuilder`/`fillEV`), e a **suíte de testes portada** (regressão JUnit do repo: `CountTimestamp`/`ObjectId`/`Types`/`Optional`/`SimplifyAggr`/`RelationshipTypeToEntityType`/`RemovePMap` + teste novo confirmando o #8 — `meta` inteiro da segunda ocorrência descartado no colapso, fiel ao original — + testes de `__eq__` e por estratégia).

## Riscos da fase

Determinismo (ordenação de campos, igualdade estrutural, ordem de variações) é *load-bearing* — divergência num desses quebra a equivalência; o Inflector tem de casar (resolvido na Fase 0); a igualdade do `ArraySC` que ignora tamanho e o colapso de variações sem `combineMetadata` (#8) são duas faces do mesmo ponto e as duas devem ser replicadas fielmente, sem correção — inclusive o `meta.count`/timestamps do objeto, que **também** se perdem no colapso (não só bounds de array).
