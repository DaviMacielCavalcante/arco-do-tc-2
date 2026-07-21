"""As seis estratégias da inferência (Fases 1.3a e 1.3b).

**1.3a — nível raw** (antes do EMF existir): porte de
`AliasedAggregatedEntityJoiner`/`DefaultAliasedAggregatedEntityJoiner` e
`EVariationMerger`/`DefaultEVariationMerger`. Sem `Protocol`/classe: nenhuma
das duas tem implementação alternativa no original, então não há polimorfismo
a desenhar — CLAUDE.md pede função pura onde não há estado real.

**1.3b — nível EMF/PyEcore** (operam sobre o modelo já construído, EObject
reflexivo — mesma fronteira mypy do `validation/equivalence.py`, ver o aviso
em CLAUDE.md): porte de `FeatureAnalyzer`/`DefaultFeatureAnalyzer`,
`ReferenceMatcher(Creator)`/`Default*`, `StructuralVariationSorter`/`Default*`/
`Null*`, `OptionalTagger`/`Default*`/`Null*`. `ReferenceMatcher` vira classe
(estado real: a lista de regex compilados) e `OptionalTagger` também (estado
acumulado entre `put`/`calc_optionality`/`is_optional`) — as outras duas
continuam função, como a 1.3a.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable

from pyecore.ecore import EObject

from uschema.intermediate.raw import ArraySC, ObjectSC, SchemaComponent
from uschema.naming.inflector import get_instance as get_inflector
from uschema.validation.equivalence import compare_feature

__all__ = [
    "NullOptionalTagger",
    "OptionalTagger",
    "ReferenceMatcher",
    "create_reference_matcher",
    "join_aggregated_entities",
    "merge_equivalent_evs",
    "null_sort_structural_variations",
    "set_optional_properties",
    "sort_structural_variations",
]

# private static List<String> AggregateHintWords (DefaultAliasedAggregatedEntityJoiner.java:13-14)
_AGGREGATE_HINT_WORDS = (
    "has",
    "with",
    "set",
    "list",
    "setof",
    "listof",
    "array",
    "arrayof",
    "collection",
    "collectionof",
)


def join_aggregated_entities(
    raw_entities: dict[str, list[SchemaComponent]],
    inner_schema_names: set[str],
) -> None:
    """Unir entidades internas que são só um alias com "hint word" de outra.

    Porte de `DefaultAliasedAggregatedEntityJoiner.joinAggregatedEntities`
    (`:17-37`). Muta `raw_entities` **no lugar** — mesma assinatura `void` do
    original; é a mesma convenção que `ObjectSC.add`/`ArraySC.add` já usam em
    `raw.py`, não uma exceção ao "funções puras" do CLAUDE.md.

    Parameters
    ----------
    raw_entities : dict of str to list of SchemaComponent
        Mapa entidade → variações, construído (e mutado) pelo `infer`. As
        listas contêm sempre `ObjectSC` — nunca outra folha; o tipo da
        assinatura é `SchemaComponent` só porque é o tipo do original.
    inner_schema_names : set of str
        Nomes registrados como puramente de aninhamento (ver `infer`, 1.2).

    Notes
    -----
    ⚠️ **Determinismo em aberto.** `findFirst` no original depende da ordem de
    iteração de `rawEntities.keySet()` — não verificado ainda que tipo de
    `Map` o `SchemaInference` usa lá (`HashMap` seria não-determinístico já
    no Java). `dict` do Python preserva ordem de inserção; isso só bate com o
    original se a ordem de inserção replicar a ordem que o `Map` java
    enumera. Registrar/confirmar quando portarmos 1.2.
    """
    for inner_name in inner_schema_names:
        match = _find_aliased_entity(raw_entities, inner_name)
        if match is None:
            continue

        variations = raw_entities[inner_name]
        for sc in variations:
            assert isinstance(sc, ObjectSC), f"variação não-ObjectSC em {inner_name!r}"
            sc.entity_name = match

        raw_entities[match].extend(variations)
        del raw_entities[inner_name]


def _find_aliased_entity(
    raw_entities: dict[str, list[SchemaComponent]], inner_name: str
) -> str | None:
    """Achar a primeira entidade cujo nome + hint word bate com `inner_name`.

    Replica `findFirst` (`:21-26`) — **só o primeiro match**, mesmo que outras
    entidades também batessem. É a limitação que o autor original documentou
    no comentário (`:24-25`): pode deixar entidades "mal nomeadas" pra trás.
    Deliberado, não corrigir.
    """
    for entity in raw_entities:
        for hint in _AGGREGATE_HINT_WORDS:
            if (hint + entity).casefold() == inner_name.casefold():
                return entity
            if (entity + hint).casefold() == inner_name.casefold():
                return entity
    return None


def merge_equivalent_evs(raw_entities: dict[str, list[SchemaComponent]]) -> None:
    """Fundir, por entidade, variações estruturalmente equivalentes.

    Porte de `DefaultEVariationMerger.mergeEquivalentEVs` (`:14-49`). Mais
    frouxo que `ObjectSC.__eq__`: não compara `entity_name`/`is_root`, só a
    forma dos campos (ver `_walk_and_merge`). Muta `raw_entities` no lugar.

    Parameters
    ----------
    raw_entities : dict of str to list of SchemaComponent
        Mapa entidade → variações. Mutado: fusões removem elementos das
        listas e podem alterar `lower_bounds`/`upper_bounds` de `ArraySC`
        aninhados (via `_homogeneous_arrays_merge`).
    """
    for variations in raw_entities.values():
        _stabilize(raw_entities, variations)


def _stabilize(
    raw_entities: dict[str, list[SchemaComponent]], variations: list[SchemaComponent]
) -> None:
    """Repetir a varredura até nenhuma fusão ocorrer (`do/while` do original).

    Cada fusão reinicia a varredura do começo da lista — mesmo efeito do
    `Iterator` do Java sendo descartado e recriado a cada `listModified`.
    """
    modified = True
    while modified:
        modified = False
        for to_consider in variations:
            for sc in variations:
                if sc is not to_consider and _walk_and_merge(to_consider, sc):
                    _update_references(raw_entities, to_consider, sc)

                    assert isinstance(sc, ObjectSC) and isinstance(to_consider, ObjectSC)
                    assert sc.meta is not None and to_consider.meta is not None
                    sc.meta.combine_metadata(to_consider.meta)

                    variations.remove(to_consider)
                    modified = True
                    break
            if modified:
                break


def _walk_and_merge(to_consider: SchemaComponent, sc: SchemaComponent) -> bool:
    """Decidir se dois nós são "a mesma variação" pro merger (`:57-70`).

    Mais frouxo que `__eq__`: não olha `entity_name`. Compara classe, depois
    despacha por tipo — objeto desce campo a campo, array trata o caso
    homogêneo à parte, folha cai no `__eq__` normal (sempre `True` pra mesma
    classe, já que folhas não têm estado).
    """
    if type(to_consider) is not type(sc):
        return False

    if isinstance(to_consider, ObjectSC):
        assert isinstance(sc, ObjectSC)
        return _walk_and_merge_object(to_consider, sc)

    if isinstance(to_consider, ArraySC):
        assert isinstance(sc, ArraySC)
        return _walk_and_merge_array(to_consider, sc)

    return to_consider == sc


def _walk_and_merge_object(to_consider: ObjectSC, sc: ObjectSC) -> bool:
    """Comparar campo a campo, em ordem, só pelo **nome** do campo (`:72-91`)."""
    if to_consider.size() != sc.size():
        return False

    for (to_key, to_value), (sc_key, sc_value) in zip(to_consider.inners, sc.inners, strict=True):
        if to_key != sc_key or not _walk_and_merge(to_value, sc_value):
            return False

    return True


def _walk_and_merge_array(to_consider: ArraySC, sc: ArraySC) -> bool:
    """Caso homogêneo é especial; caso normal ignora nomes, só posição (`:93-118`)."""
    if to_consider.homogeneous != sc.homogeneous:
        return False

    if to_consider.homogeneous and sc.homogeneous:
        return _homogeneous_arrays_merge(to_consider, sc)

    if to_consider.size() != sc.size():
        return False

    for to_item, sc_item in zip(to_consider.inners, sc.inners, strict=True):
        if not _walk_and_merge(to_item, sc_item):
            return False

    return True


def _homogeneous_arrays_merge(to_consider: ArraySC, sc: ArraySC) -> bool:
    """Reconciliar dois arrays homogêneos — com efeito colateral em `sc` (`:120-143`).

    Não usa `_walk_and_merge` pro elemento representante — usa `==` direto
    (o `.equals()` do original), mais estrito que o resto do merger. Se um
    lado está vazio, o outro empresta seu elemento (`sc.add(...)`); os bounds
    sempre se reconciliam por `min`/`max`, é aqui que `lower_bounds` do
    `raw.py` deixa de ser sempre `0` (o setter que a docstring de `ArraySC`
    já menciona como só existindo pra isso).

    ⚠️ **M5** (`bugs_originais.md`): se os dois lados chegarem vazios ao
    mesmo tempo, `to_consider.inners[0]` estoura `IndexError` — o original
    (`:132`) tem o mesmo problema, `IndexOutOfBoundsException`, confirmado
    por execução real do Java. O comentário do autor assume que isso "não
    pode acontecer" (colapsariam antes), mas outro campo do mesmo par pode
    reconciliar com sucesso (ex.: cheio x vazio) e o walk alcança um segundo
    campo vazio nos dois lados. Replicado fielmente, sem guarda — não
    adicionar `if to_consider.size() == 0: return False` aqui.
    """
    if not (to_consider.size() == 0 or sc.size() == 0 or to_consider.inners[0] == sc.inners[0]):
        return False

    lower_bounds = min(to_consider.lower_bounds, sc.lower_bounds)

    if sc.size() == 0:
        sc.add(to_consider.inners[0])

    sc.lower_bounds = lower_bounds
    sc.upper_bounds = max(to_consider.upper_bounds, sc.upper_bounds)

    return True


def _update_references(
    raw_entities: dict[str, list[SchemaComponent]],
    old: SchemaComponent,
    new: SchemaComponent,
) -> None:
    """Trocar, por **identidade**, toda referência a `old` por `new` (`:145-177`).

    Necessário porque `old` está prestes a sair da lista de variações; se
    algum campo em qualquer outra árvore ainda apontar (pelo mesmo objeto
    Python, não por igualdade) para `old`, ele ficaria órfão.
    """
    for variations in raw_entities.values():
        for sc in variations:
            _update_references_in(old, new, sc)


def _update_references_in(old: SchemaComponent, new: SchemaComponent, sc: SchemaComponent) -> None:
    if isinstance(sc, ObjectSC):
        for i, (name, value) in enumerate(sc.inners):
            if value is old:
                sc.inners[i] = (name, new)
            else:
                _update_references_in(old, new, value)

    elif isinstance(sc, ArraySC):
        sc.inners = [new if item is old else item for item in sc.inners]
        for item in sc.inners:
            if item is not new:
                _update_references_in(old, new, item)


# ============================================================================
# 1.3b — nível EMF/PyEcore
# ============================================================================


def set_optional_properties(variations: list[EObject]) -> None:
    """Marcar `optional` toda `StructuralFeature` ausente de ≥1 variação.

    Porte de `DefaultFeatureAnalyzer.setOptionalProperties` (`:20-40`). Reusa
    `compare_feature` (Fase 0.3) — é o mesmo `CompareFeature` do original
    (`DefaultFeatureAnalyzer.java:8,13,17`), não reimplementado aqui.

    Parameters
    ----------
    variations : list of EObject
        As `StructuralVariation` de uma mesma entidade. Muta cada
        `StructuralFeature.optional` no lugar; não faz sentido para uma lista
        vazia (o original também assume `variations.get(0)` sem guarda).

    Notes
    -----
    `EObject` é `Any` na prática (PyEcore não distribui `py.typed`) — ver o
    aviso sobre mypy em CLAUDE.md. Cada acesso a campo aqui
    (`.structuralFeatures`, `.optional`) precisa ser exercitado por teste.
    """
    first_variation = variations[0]
    # `:24-25` — cópia, não a mesma lista (`ArrayList<>().addAll(...)`).
    common_props: list[EObject] = list(first_variation.structuralFeatures)
    optional_props: list[EObject] = []

    # `:30-32` — uma feature de `variations[0]` só é comum se TODAS as outras
    # variações têm alguma feature própria que `compare_feature` considera a
    # mesma.
    for prop in common_props:
        is_common = all(
            var is first_variation
            or any(compare_feature(prop, sf) for sf in var.structuralFeatures)
            for var in variations
        )
        if not is_common:
            optional_props.append(prop)

    for prop in optional_props:
        common_props.remove(prop)

    # `:38-39` — toda feature de toda variação: opcional se não bate com
    # nenhuma das comuns.
    for var in variations:
        for sf in var.structuralFeatures:
            sf.optional = not any(compare_feature(sf, common) for common in common_props)


# Affixes/StopChars/UnlikelyWords (DefaultReferenceMatcher.java:20-27).
_REFERENCE_AFFIXES = ("id", "ptr", "ref", "ids", "refs", "has", "")
_REFERENCE_STOP_CHARS = ("_", ".", "-", "")
_REFERENCE_UNLIKELY_WORDS = ("count",)


class ReferenceMatcher:
    """Decide se um nome de campo é referência a alguma entidade indexada.

    Porte de `DefaultReferenceMatcher` (`:17-64`). Sem `Default`/`Null*` no
    nome — só há uma implementação no original, mesma razão do Joiner/Merger
    da 1.3a. Vira classe (não função) porque carrega estado real: a lista de
    regex compilados, montada uma vez no construtor.

    Parameters
    ----------
    pairs : iterable of (str, EObject)
        Pares (nome candidato, entidade) — normalmente as três variantes
        (singular/plural/como está) de cada entidade raiz, ver
        :func:`create_reference_matcher`.

    Notes
    -----
    O autor original comentou a própria lentidão (`:29-32`, "By using a list
    this matcher is just too slow") e manteve assim. Replicado como está —
    não é escopo do porte otimizar o que o original também não otimizou.

    ⚠️ **M6** (`bugs_originais.md`): `key` entra crua na string do regex, sem
    `re.escape`. O original faz o mesmo (`entry.getKey()` concatenado direto
    em `DefaultReferenceMatcher.java:34-50`, confirmado por execução real) —
    um metacaractere de regex em `key` (`.`, `+`, `(`, `[`, …) é interpretado
    como regex, não como literal. Não escapar aqui: escapar divergiria do
    oráculo para nomes de entidade que contenham esses caracteres.
    """

    def __init__(self, pairs: Iterable[tuple[str, EObject]]) -> None:
        patterns: list[tuple[re.Pattern[str], EObject]] = []

        for key, value in pairs:
            for affix in _REFERENCE_AFFIXES:
                # `:42-43` — prefixo, chave antes do afixo.
                for c in _REFERENCE_STOP_CHARS:
                    patterns.append((re.compile(f"^{key}{c}{affix}.*$".lower()), value))
                # `:44-45` — prefixo, afixo antes da chave.
                for c in _REFERENCE_STOP_CHARS:
                    patterns.append((re.compile(f"^{affix}{c}{key}.*$".lower()), value))
                # `:47-48` — sufixo, chave antes do afixo. Filtra c="" e
                # afixo="" juntos (padrão `.*?key$` sem afixo nenhum já sai
                # coberto, de outra forma, pelo prefixo acima).
                for c in _REFERENCE_STOP_CHARS:
                    if c or affix:
                        patterns.append((re.compile(f"^.*?{key}{c}{affix}$".lower()), value))
                # `:49-50` — sufixo, afixo antes da chave.
                for c in _REFERENCE_STOP_CHARS:
                    if c or affix:
                        patterns.append((re.compile(f"^.*?{affix}{c}{key}$".lower()), value))

        self._patterns = patterns

    def maybe_match(self, field_id: str) -> EObject | None:
        """Achar a primeira entidade cujo padrão bate com `field_id`.

        Porte de `maybeMatch` (`:56-63`).

        Parameters
        ----------
        field_id : str
            Nome do campo a testar (ex.: ``"customerId"``).

        Returns
        -------
        EObject or None
            A entidade casada, ou `None` se `field_id` contém uma palavra de
            `_REFERENCE_UNLIKELY_WORDS` ou nenhum padrão bate.
        """
        lowered = field_id.lower()

        if any(word in lowered for word in _REFERENCE_UNLIKELY_WORDS):
            return None

        for pattern, value in self._patterns:
            if pattern.match(lowered):
                return value

        return None


def create_reference_matcher(entities: Iterable[EObject]) -> ReferenceMatcher:
    """Construir o `ReferenceMatcher` a partir das entidades **raiz**.

    Porte de `DefaultReferenceMatcherCreator.createReferenceMatcher`
    (`:20-30`). Só entidades com ao menos uma variação raiz são
    referenciáveis (`:22`, `EntityType::isRoot`).

    Parameters
    ----------
    entities : iterable of EObject
        Todas as `EntityType` do modelo (raiz e não-raiz).

    Returns
    -------
    ReferenceMatcher
        Indexado por `{nome, plural(nome), singular(nome)}` de cada entidade
        raiz.

    Notes
    -----
    ⚠️ O original usa `HashSet<String>` pras três variantes (`:24-27`) — a
    ordem de iteração de um `HashSet` real não é a de inserção, mas é
    determinística *dentro* de uma mesma execução (o hash de `String` no Java
    é uma função pura). Um `set()` do Python, em contraste, varia **entre**
    processos por causa do `PYTHONHASHSEED` (proteção de segurança) — seria
    *menos* determinístico que o original, não mais fiel a ele. Por isso o
    porte usa `dict.fromkeys(...)` (dedup preservando ordem de inserção,
    garantido pela linguagem): não é literal ao `HashSet`, mas é a única
    escolha que dá determinismo reproduzível — o mesmo raciocínio já aplicado
    ao `findFirst` do Joiner (1.3a, ver docstring de `join_aggregated_entities`).
    """
    inflector = get_inflector()
    pairs: list[tuple[str, EObject]] = []

    for entity in entities:
        if not entity.root:
            continue

        name = entity.name
        variants = dict.fromkeys([name, inflector.pluralize(name), inflector.singularize(name)])

        for variant in variants:
            assert variant is not None
            pairs.append((variant, entity))

    return ReferenceMatcher(pairs)


def sort_structural_variations(variations: list[EObject]) -> None:
    """Ordenar as variações de uma entidade — em cascata, deterministicamente.

    Porte de `DefaultStructuralVariationSorter.sort` (`:13-24`): por
    `firstTimestamp` se alguma variação tiver um não-zero; senão por
    `lastTimestamp`; senão por `count`; senão pelo número de propriedades.
    Muta `variations` no lugar e renumera `variationId` a partir de 1.

    Parameters
    ----------
    variations : list of EObject
        As `StructuralVariation` de uma entidade.

    Notes
    -----
    ⚠️ **M3** (`bugs_originais.md`): o ramo `sortByCount` **não ordena** — o
    `ECollections.sort` está comentado no original (`:40`); só renumera
    `variationId`, deixando a ordem de inserção. Replicado como está.

    ⚠️ **M4** (`bugs_originais.md`): os comparadores devolvem só `-1`/`1`,
    nunca `0` (`:28,34,46`) — não são uma ordem total; dois elementos "iguais"
    (mesmo timestamp/count/nº de propriedades) sempre se afirmam maiores um
    que o outro. `functools.cmp_to_key` replica esse comparador tal como é,
    inclusive esse defeito — a ordem resultante entre iguais fica a critério
    do algoritmo de ordenação (Timsort é estável, mas o comparador não é
    consistente, então "estável" não garante nada aqui). Fixar a ordem
    observada em teste.
    """
    if any(v.firstTimestamp != 0 for v in variations):
        variations.sort(key=functools.cmp_to_key(_compare_by_first_timestamp))
    elif any(v.lastTimestamp != 0 for v in variations):
        variations.sort(key=functools.cmp_to_key(_compare_by_last_timestamp))
    elif any(v.count != 0 for v in variations):
        pass  # M3 — sortByCount não ordena no original; só renumera abaixo.
    else:
        variations.sort(key=functools.cmp_to_key(_compare_by_property_number))

    _reorder_variation_ids(variations)


def _compare_by_first_timestamp(a: EObject, b: EObject) -> int:
    """`:28` — `-1`/`1`, nunca `0` (M4, ver `sort_structural_variations`)."""
    return -1 if a.firstTimestamp < b.firstTimestamp else 1


def _compare_by_last_timestamp(a: EObject, b: EObject) -> int:
    """`:34` — mesma forma do M4."""
    return -1 if a.lastTimestamp < b.lastTimestamp else 1


def _compare_by_property_number(a: EObject, b: EObject) -> int:
    """`:46` — mesma forma do M4; compara nº de `features`, não `structuralFeatures`."""
    return -1 if len(a.features) < len(b.features) else 1


def _reorder_variation_ids(variations: list[EObject]) -> None:
    """`:50-54` — renumerar `variationId` a partir de 1, na ordem atual."""
    for i, variation in enumerate(variations, start=1):
        variation.variationId = i


def null_sort_structural_variations(variations: list[EObject]) -> None:
    """Não fazer nada — porte de `NullStructuralVariationSorter.sort` (`:9-12`)."""


class OptionalTagger:
    """Acumula variações por entidade e calcula quais campos são opcionais.

    Porte de `DefaultOptionalTagger` (`:11-67`). Vira classe (diferente do
    Joiner/Merger da 1.3a): há estado real acumulado por várias chamadas de
    `put`, processado uma vez em `calc_optionality`, consultado depois por
    `is_optional`.

    Notes
    -----
    ⚠️ **Código morto no pipeline.** No `USchemaModelBuilder`, só `put()` é
    chamado de verdade; `calc_optionality()` e `is_optional()` nunca são
    invocados — estão comentados no original com `// TODO: Remove until
    recode` (quem realmente marca opcionalidade é `FeatureAnalyzer`, ver
    `set_optional_properties`). Portado por completo mesmo assim (fiel e
    completo, mesma decisão do `camelCase`/`underscore` do Inflector na 0.6),
    mas **não** cobrir com teste de equivalência contra o oráculo — não há
    saída observável que dependa disso.
    """

    def __init__(self) -> None:
        self._variations_by_entity: dict[str, list[SchemaComponent]] = {}
        self._optionals_by_entity: dict[str, dict[tuple[str, SchemaComponent], int]] = {}

    def put(self, entity_type_name: str, schema: SchemaComponent) -> None:
        """`:23-32` — anexar `schema` à lista da entidade, criando-a se nova."""
        self._variations_by_entity.setdefault(entity_type_name, []).append(schema)

    def calc_optionality(self) -> None:
        """`:35-59` — contar, por entidade, quantas variações têm cada campo.

        Um campo `(nome, componente)` que aparece em **todas** as variações
        da entidade é removido da contagem (não é opcional); o que sobra em
        `_optionals_by_entity[entidade]` são os campos vistos em algumas, não
        todas — os opcionais.
        """
        for entity_name, schemas in self._variations_by_entity.items():
            feat_count: dict[tuple[str, SchemaComponent], int] = {}
            self._optionals_by_entity[entity_name] = feat_count

            # `:44-46` — uma só variação: nada pode ser opcional.
            if len(schemas) == 1:
                continue

            for sc in schemas:
                assert isinstance(sc, ObjectSC)
                for pair in sc.inners:
                    feat_count[pair] = feat_count.get(pair, 0) + 1

            num_variations = len(schemas)
            for pair in list(feat_count):
                if feat_count[pair] == num_variations:
                    del feat_count[pair]

    def is_optional(self, entity_name: str, pair: tuple[str, SchemaComponent]) -> bool:
        """`:63-66` — `True` se `pair` sobreviveu à filtragem de `calc_optionality`."""
        return pair in self._optionals_by_entity[entity_name]


class NullOptionalTagger:
    """No-op — porte de `NullOptionalTagger` (`:14-34`)."""

    def put(self, entity_type_name: str, schema: SchemaComponent) -> None:
        """`:20` — não faz nada."""

    def calc_optionality(self) -> None:
        """`:24` — não faz nada."""

    def is_optional(self, entity_name: str, pair: tuple[str, SchemaComponent]) -> bool:
        """`:28-30` — sempre `False`."""
        return False
