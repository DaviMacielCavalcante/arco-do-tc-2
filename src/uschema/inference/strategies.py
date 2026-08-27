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
from typing import ClassVar

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
    """Unir entidades cujo nome é uma variação com "hint word" de agregação.

    Porte de ``DefaultAliasedAggregatedEntityJoiner.joinAggregatedEntities``
    (``:17-37``). Roda **antes** de ``inner_count_and_time_stamps_adjust`` —
    Fase 1.3a, nível raw.

    Parameters
    ----------
    raw_entities : dict[str, list[SchemaComponent]]
        Mapa entidade → variações, mutado no lugar.
    inner_schema_names : set of str
        Nomes de entidades não-raiz candidatas a "alias agregado" de outra
        entidade (ex.: ``"hasEmployees"`` de ``"Employee"``).

    Notes
    -----
    Para cada nome em ``inner_schema_names``, procura a **primeira** entidade
    existente tal que ``hint + entidade`` ou ``entidade + hint`` bate
    (case-insensitive) com o nome da entidade interna — mesmo
    ``.casefold()``/``equalsIgnoreCase`` (``:23``). O comentário do próprio
    autor original (``:24-26``) admite a limitação de propósito: *"why find
    first only? ... ignoring everything but the first match could lead us to
    some bad-named entities"* — replicado sem tentar consertar. Ao achar,
    renomeia todas as variações da entidade interna (``:30``) e as concatena
    na lista da entidade encontrada (``:33``), removendo a entrada antiga
    (``:34``).
    """
    for inner_name in inner_schema_names:
        match_key = None
        for entity in raw_entities:
            for hint in _AGGREGATE_HINT_WORDS:
                prefixed = (hint + entity).casefold() == inner_name.casefold()
                suffixed = (entity + hint).casefold() == inner_name.casefold()
                if prefixed or suffixed:
                    match_key = entity
                    break
            if match_key is not None:
                break
        if match_key is not None:
            for raw in raw_entities[inner_name]:
                assert isinstance(raw, ObjectSC)
                raw.entity_name = match_key
            raw_entities[match_key].extend(raw_entities[inner_name])
            raw_entities.pop(inner_name)
    return None


def merge_equivalent_evs(raw_entities: dict[str, list[SchemaComponent]]) -> None:
    """Fundir variações estruturalmente equivalentes dentro de cada entidade.

    Porte do método público ``mergeEquivalentEVs(Map<...>)``
    (``DefaultEVariationMerger.java:14-49``) — Fase 1.3a, nível raw. Roda
    **depois** de ``inner_count_and_time_stamps_adjust`` (mesma ordem do
    ``infer``, ver ``schema_inference.py``).

    Parameters
    ----------
    raw_entities : dict[str, list[SchemaComponent]]
        Mapa entidade → variações; cada lista é mutada no lugar.

    Notes
    -----
    O ``do-while`` externo (``:21-47``, repete enquanto ``listModified``) e
    o ``do-while`` interno com ``Iterator`` (``:26-46``) colapsam num único
    ``while(list_modified): ... for idx, to_consider in enumerate(entity):
    ...`` — como o Java sempre dá ``break`` logo depois de achar um par e
    nunca reusa o iterador depois, um ``for`` comum com ``break`` reproduz o
    mesmo comportamento sem precisar de ``Iterator.remove()`` (que não
    existe em Python); a remoção vira ``entity.pop(idx)``, por índice —
    nunca ``list.remove(x)``, que buscaria por ``==`` e poderia remover o
    objeto errado.

    O par candidato é comparado com ``sc is not to_consider`` (``:31``,
    ``sc != toConsider`` no Java é comparação de **referência**, não
    ``equals``) — por isso ``is not``, não ``!=``. Ao achar um par que
    funde (``walk_and_merge``, que aqui já embute o
    ``mergeEquivalentEVs(SchemaComponent,SchemaComponent)`` privado de
    ``:52-55``, sem o parâmetro ``id`` morto de ``walkAndMerge``), atualiza
    referências (``update_references``, ``:34``), combina o metadado **em
    ``sc``** — o sobrevivente — absorvendo o de ``to_consider`` (``:36``), e
    remove ``to_consider`` da lista (``:39``).
    """
    for entity in raw_entities.values():
        list_modified = True
        while list_modified:
            match = False
            list_modified = False
            for idx, to_consider in enumerate(entity):
                for sc in entity:
                    if sc is not to_consider and walk_and_merge(to_consider, sc):
                        assert isinstance(sc, ObjectSC)
                        assert isinstance(to_consider, ObjectSC)
                        update_references(raw_entities, to_consider, sc)
                        assert sc.meta is not None
                        assert to_consider.meta is not None
                        sc.meta.combine_metadata(to_consider.meta)
                        entity.pop(idx)
                        list_modified = True
                        match = True
                        break
                if match is True:
                    break


def walk_and_merge(to_consider: SchemaComponent, sc: SchemaComponent) -> bool:
    """Testar se duas variações são estruturalmente idênticas (fundíveis).

    Colapsa as três sobrecargas privadas ``walkAndMerge`` do original
    (``DefaultEVariationMerger.java:57-118``): a dispatcher genérica
    (``:57-70``), a de ``ObjectSC`` (``:72-91``) e a de ``ArraySC``
    (``:93-118``). O parâmetro ``id`` (threading por toda a recursão, nunca
    lido) é descartado — é morto no original.

    Parameters
    ----------
    to_consider : SchemaComponent
        A variação candidata a ser absorvida.
    sc : SchemaComponent
        A variação contra a qual comparar.

    Returns
    -------
    bool
        ``True`` se ``to_consider`` e ``sc`` têm exatamente a mesma
        estrutura (mesmos tipos, recursivamente).

    Notes
    -----
    Classes diferentes já cortam (``:60-61``, ``getClass().equals``). Para
    ``ObjectSC``, exige mesmo tamanho e os campos **na mesma ordem**, com o
    mesmo nome par a par (``:74-88``, ``zip`` substitui os dois
    ``Iterator`` paralelos do Java — mas ``zip`` não detecta tamanhos
    diferentes por si, daí a guarda de ``size()`` antes). Para ``ArraySC``,
    precisa da mesma homogeneidade (``:95-96``); se ambos homogêneos,
    delega a ``homogeneous_arrays_merge`` (``:99-100``); senão, mesma
    lógica do ``ObjectSC`` mas sem nomes de campo (``:101-117``). Folhas
    caem no ramo final e comparam por ``==`` (``:69``,
    ``toConsider.equals(sc)`` — igualdade estrutural das folhas sem estado,
    ver ``raw.py``).
    """
    if type(to_consider) is not type(sc):
        return False
    else:
        if isinstance(to_consider, ObjectSC):
            assert isinstance(sc, ObjectSC)
            if to_consider.size() != sc.size():
                return False
            pairs = zip(to_consider.inners, sc.inners, strict=True)
            for (to_key, to_value), (sc_key, sc_value) in pairs:
                if sc_key == to_key:
                    if walk_and_merge(to_value, sc_value) is False:
                        return False
                else:
                    return False
            return True

        elif isinstance(to_consider, ArraySC):
            assert isinstance(sc, ArraySC)
            if to_consider.homogeneous != sc.homogeneous:
                return False

            if to_consider.homogeneous and sc.homogeneous:
                return homogeneous_arrays_merge(to_consider, sc)
            else:
                if to_consider.size() != sc.size():
                    return False
                for to_elem, sc_elem in zip(to_consider.inners, sc.inners, strict=True):
                    if walk_and_merge(to_elem, sc_elem) is False:
                        return False

                return True

        elif isinstance(to_consider, SchemaComponent):
            return to_consider == sc


def homogeneous_arrays_merge(to_consider: ArraySC, sc: ArraySC) -> bool:
    """Fundir dois arrays homogêneos, ajustando os limites de ocorrência.

    Porte de ``homogeneousArraysMerge``
    (``DefaultEVariationMerger.java:120-143``).

    Parameters
    ----------
    to_consider : ArraySC
        O array candidato a ser absorvido.
    sc : ArraySC
        O array sobrevivente, mutado no lugar.

    Returns
    -------
    bool
        ``True`` se os arrays são compatíveis (algum vazio, ou o elemento
        representativo bate) e a fusão ocorreu.

    Notes
    -----
    A condição (``:125-126``) usa ``or`` em curto-circuito: só acessa
    ``inners[0]`` se **nenhum** dos dois arrays for vazio ali. Isso não
    evita o bug por completo — se **ambos** forem vazios, a primeira
    cláusula (``to_consider.size() == 0``) já é ``True`` e entra no bloco;
    dentro dele, ``if sc.size() == 0: sc.add(to_consider.inners[0])``
    (``:131-132``) executa mesmo quando ``to_consider`` também está vazio,
    e ``to_consider.inners[0]`` estoura ``IndexError``/
    ``IndexOutOfBoundsException`` — replicado de propósito (ver **M5** em
    ``bugs_originais.md``, não corrigido). Fora esse caso, ajusta
    ``lower_bounds``/``upper_bounds`` para o mín./máx. entre os dois
    (``:128,135-137``).
    """
    if to_consider.size() == 0 or sc.size() == 0 or to_consider.inners[0] == sc.inners[0]:
        lower_bounds = min(to_consider.lower_bounds, sc.lower_bounds)

        if sc.size() == 0:
            sc.add(to_consider.inners[0])

        sc.lower_bounds = lower_bounds

        upper_bounds = max(to_consider.upper_bounds, sc.upper_bounds)
        sc.upper_bounds = upper_bounds

        return True
    return False


def update_references(
    raw_entities: dict[str, list[SchemaComponent]],
    old: SchemaComponent,
    new: SchemaComponent,
) -> None:
    """Substituir toda referência a ``old`` por ``new``, em todas as entidades.

    Porte de ``updateReferences(Map<...>, SchemaComponent old,
    SchemaComponent neew)`` (``DefaultEVariationMerger.java:145-149``) — o
    ponto de entrada, chamado por ``merge_equivalent_evs`` sempre que uma
    variação é absorvida por outra.

    Parameters
    ----------
    raw_entities : dict[str, list[SchemaComponent]]
        Todas as entidades e variações; percorridas por inteiro.
    old : SchemaComponent
        A variação que está sendo removida (``to_consider``, no chamador).
    new : SchemaComponent
        A variação sobrevivente que deve substituí-la em todo lugar.
    """
    for items in raw_entities.values():
        for sc in items:
            update_references_decide(old, new, sc)


def update_references_decide(
    old: SchemaComponent, new: SchemaComponent, sc: SchemaComponent
) -> None:
    """Substituir ``old`` por ``new`` dentro de um componente, recursivamente.

    Colapsa três sobrecargas do original: o dispatcher genérico
    ``updateReferences(SchemaComponent,SchemaComponent,SchemaComponent)``
    (``:151-158``), e as versões específicas para ``ObjectSC`` (``:160-168``)
    e ``ArraySC`` (``:170-177``).

    Parameters
    ----------
    old : SchemaComponent
        A variação a substituir.
    new : SchemaComponent
        A substituta.
    sc : SchemaComponent
        O componente sendo varrido — só ``ObjectSC``/``ArraySC`` têm campos
        internos a percorrer; folhas não fazem nada (nenhum ``if`` bate).

    Notes
    -----
    ⚠️ Toda comparação aqui é por **identidade**, não igualdade estrutural
    — no Java, ``p.getValue() == old`` (``:163``) e ``_sc == old``/``_sc !=
    neew`` (``:172,174``) comparam **referências de objeto**, não
    ``equals()``. Por isso ``is``/``is not``, nunca ``==``/``!=``: como
    ``ObjectSC``/``ArraySC`` têm ``__eq__`` estrutural (ver ``raw.py``),
    usar ``==`` aqui trocaria a variação errada — uma *estruturalmente
    igual mas distinta* de ``old``.

    Ramo ``ObjectSC`` (``:160-168``): para cada par ``(key, value)``, se
    ``value`` **é** ``old``, substitui a tupla; senão desce recursivamente
    em ``value``. Ramo ``ArraySC`` (``:170-177``): primeiro troca todas as
    ocorrências de ``old`` por ``new`` em ``inners`` (equivalente ao
    ``replaceAll``), depois desce recursivamente só nos elementos que
    **não são** ``new`` (evita reprocessar o que acabou de ser trocado,
    mesma guarda ``_sc != neew`` do Java).
    """
    if isinstance(sc, ObjectSC):
        for idx, (key, value) in enumerate(sc.inners):
            if value is old:
                sc.inners[idx] = (key, new)
            else:
                update_references_decide(old, new, value)

    if isinstance(sc, ArraySC):
        sc.inners = [new if item is old else item for item in sc.inners]
        for item in sc.inners:
            if item is not new:
                update_references_decide(old, new, item)


class OptionalTagger:
    """Marca quais campos são opcionais, contando ocorrências entre variações.

    Porte de ``OptionalTagger``/``DefaultOptionalTagger``
    (``OptionalTagger.java:11-19``, ``DefaultOptionalTagger.java:11-67``) —
    nível **raw** (opera sobre ``SchemaComponent``, apesar de logicamente
    pertencer à mesma leva de estratégias EMF da 1.3b — ver nota no docstring
    do módulo). Tem estado real, acumulado entre chamadas de ``put``,
    processado por ``calc_optionality`` e consultado por ``is_optional`` —
    por isso é classe, diferente de ``set_optional_properties``/
    ``sort_structural_variations``, que não guardam nada entre chamadas.
    """

    def __init__(self) -> None:
        """Inicializar os dois dicts de estado vazios.

        Porte do construtor (``DefaultOptionalTagger.java:16-20``): substitui
        ``mSVByEntity``/``optionalsByEntity`` por dois dicts Python.
        """
        self.dict1: dict[str, list[SchemaComponent]] = {}
        self.dict2: dict[str, dict[tuple[str, SchemaComponent], int]] = {}

    def put(self, entity_type_name: str, schema: SchemaComponent) -> None:
        """Registrar uma variação (``schema``) na lista da sua entidade.

        Porte de ``put`` (``DefaultOptionalTagger.java:23-32``). Chamado uma
        vez por variação — quem chama (Fase 1.4) acumula todas as
        variações de uma entidade com chamadas repetidas antes de
        ``calc_optionality`` rodar.

        Parameters
        ----------
        entity_type_name : str
             Nome da entidade dona da variação.
        schema : SchemaComponent
             A variação (``ObjectSC``) a registrar.
        """
        if self.dict1.get(entity_type_name) is not None:
            self.dict1[entity_type_name].append(schema)
        else:
            new_list = []
            new_list.append(schema)
            self.dict1[entity_type_name] = new_list

    def calc_optionality(self) -> None:
        """Calcular, por entidade, quais pares campo/componente são opcionais.

        Porte de ``calcOptionality`` (``DefaultOptionalTagger.java:35-60``).

        Notes
        -----
        O ``return;`` do Java (``:46``) está dentro de uma lambda chamada uma
        vez por entidade (``forEach``) — ali ele só pula o processamento
        *daquela* entidade. Aqui, com um ``for`` de verdade, o equivalente é
        ``continue``, não ``return`` (que sairia da função inteira). O
        registro do dict vazio em ``self.dict2`` (``:40``) acontece **antes**
        da checagem de ``num_variations == 1`` — mesmo quando pulamos o
        resto, a entidade já tem uma entrada (vazia) em ``self.dict2``.

        A contagem (``:48-56``, ``flatMap`` + ``reduce``) vira o duplo
        ``for`` (variações → campos de cada variação) com o padrão
        get-ou-default-e-soma (``new_dict.get(field, 0) + 1``). O filtro
        final (``:58``, ``removeIf``) vira uma dict comprehension mantendo
        só os pares cuja contagem é **diferente** do total de variações —
        os que não apareceram em todas.
        """
        for entity in self.dict1:
            variations = self.dict1[entity]
            new_dict: dict[tuple[str, SchemaComponent], int] = {}
            self.dict2[entity] = new_dict
            num_variations = len(variations)

            if num_variations == 1:
                continue
            else:
                for var in variations:
                    assert isinstance(var, ObjectSC)
                    for field in var.inners:
                        new_dict[field] = new_dict.get(field, 0) + 1
                self.dict2[entity] = {
                    field: t for field, t in new_dict.items() if t != num_variations
                }

    def is_optional(self, entity_name: str, sc: tuple[str, SchemaComponent]) -> bool:
        """Dizer se um par campo/componente é opcional para uma entidade.

        Porte de ``isOptional`` (``DefaultOptionalTagger.java:62-66``);
        ``containsKey`` vira o operador ``in`` do Python.
        """
        return sc in self.dict2[entity_name]


class NullOptionalTagger:
    """Versão no-op de :class:`OptionalTagger` — não marca nada como opcional.

    Porte de ``NullOptionalTagger`` (``NullOptionalTagger.java:14-34``).
    """

    def put(self, entity_type_name: str, schema: SchemaComponent) -> None:
        """Não fazer nada (``NullOptionalTagger.java:20-22``)."""
        return None

    def calc_optionality(self) -> None:
        """Não fazer nada (``NullOptionalTagger.java:24-27``)."""
        return None

    def is_optional(self, entity_name: str, sc: tuple[str, SchemaComponent]) -> bool:
        """Sempre dizer que não é opcional (``NullOptionalTagger.java:29-33``)."""
        return False


def reorder_variation_ids(vars: list[EObject]) -> None:
    """Renumerar ``variation_id`` de 1 a N, na ordem atual da lista.

    Porte de ``reorderVariationIds``
    (``DefaultStructuralVariationSorter.java:50-54``). O iterador manual de
    inteiros do Java (``IntStream.range(1, n+1).iterator()`` + ``it.next()``
    a cada elemento) vira ``enumerate(vars, start=1)``, que já pareia índice
    e elemento de uma vez.
    """
    for num, var in enumerate(vars, start=1):
        var.variationId = num


def sorting_key(var1: EObject, var2: EObject) -> int:
    return -1 if var1.firstTimestamp < var2.firstTimestamp else 1


def sort_by_first_timestamp(vars: list[EObject]) -> None:
    """Ordenar por ``firstTimestamp`` crescente e renumerar.

    Porte de ``sortByFirstTimestamp``
    (``DefaultStructuralVariationSorter.java:26-30``). O comparador Java
    (``var1.getFirstTimestamp() < var2.getFirstTimestamp() ? -1 : 1``) nunca
    devolve "empate" — em caso de igualdade, cai no ``1`` (assimetria
    proposital do original, replicada aqui via ``functools.cmp_to_key`` em
    vez de um ``key=`` comum, que trataria empates de forma diferente).
    """
    vars.sort(key=functools.cmp_to_key(sorting_key))
    reorder_variation_ids(vars)


def sorting_key2(var1: EObject, var2: EObject) -> int:
    return -1 if var1.lastTimestamp < var2.lastTimestamp else 1


def sort_by_last_timestamp(vars: list[EObject]) -> None:
    """Ordenar por ``lastTimestamp`` crescente e renumerar.

    Porte de ``sortByLastTimestamp``
    (``DefaultStructuralVariationSorter.java:32-36``); mesma lógica de
    :func:`sort_by_first_timestamp`, trocando o campo comparado.
    """
    vars.sort(key=functools.cmp_to_key(sorting_key2))
    reorder_variation_ids(vars)


def sort_by_count(vars: list[EObject]) -> None:
    """Só renumerar — **não ordena de verdade**.

    Porte de ``sortByCount`` (``DefaultStructuralVariationSorter.java:38-42``).
    No original, a linha de ordenação está **comentada**
    (``//ECollections.sort(...)``) — só ``reorderVariationIds`` roda. É uma
    incompletude do original, replicada fielmente, não corrigida.
    """
    reorder_variation_ids(vars)


def sorting_key3(var1: EObject, var2: EObject) -> int:
    return -1 if len(var1.features) < len(var2.features) else 1


def sort_by_property_number(vars: list[EObject]) -> None:
    """Ordenar pelo número de features (``len(features)``) e renumerar.

    Porte de ``sortByPropertyNumber``
    (``DefaultStructuralVariationSorter.java:44-48``).
    """
    vars.sort(key=functools.cmp_to_key(sorting_key3))
    reorder_variation_ids(vars)


def sort_structural_variations(vars: list[EObject]) -> None:
    """Escolher o critério de ordenação e aplicá-lo, em cascata.

    Porte de ``sort`` (``DefaultStructuralVariationSorter.java:14-24``), o
    método público de ``DefaultStructuralVariationSorter``. Prioridade:
    ``firstTimestamp`` preenchido em alguma variação → ``lastTimestamp`` →
    ``count`` → número de propriedades (fallback, sempre disponível).
    """
    if any(var.firstTimestamp != 0 for var in vars):
        sort_by_first_timestamp(vars)

    elif any(var.lastTimestamp != 0 for var in vars):
        sort_by_last_timestamp(vars)

    elif any(var.count != 0 for var in vars):
        sort_by_count(vars)
    else:
        sort_by_property_number(vars)


def null_sort_structural_variations(vars: list[EObject]) -> None:
    """Não fazer nada (porte de ``NullStructuralVariationSorter.java:9-12``)."""
    return None


def set_optional_properties(variations: list[EObject]) -> None:
    """Marcar, em cada variação, quais features não são comuns a todas.

    Porte de ``setOptionalProperties``
    (``DefaultFeatureAnalyzer.java:21-40``). Sem estado próprio — o
    ``comparer`` do Java (``:13,17``) é só um ``CompareFeature()``, que aqui
    já existe pronto como a função importada ``compare_feature``.

    Parameters
    ----------
    variations : list of StructuralVariation
         As variações estruturais (EMF) de uma mesma entidade.

    Notes
    -----
    Três fases: (1) semeia candidatos a partir das features da variação 0
    (``:24-25``); (2) para cada candidato, checa se **todas** as variações
    têm alguma feature equivalente — a própria variação 0 passa
    automaticamente via ``var is variations[0]`` (``:31``, comparação de
    **referência**, mesmo cuidado ``is``/``==`` de sempre) — e separa os que
    não são comuns em ``optional_props``, removendo-os no final
    (``:27,30-32,35``); (3) para cada feature de cada variação, marca
    ``optional`` como "não bate com nenhuma das comuns" (``:38-39``,
    ``noneMatch`` vira ``not any(...)``).
    """
    common_props = list(variations[0].structuralFeatures)
    optional_props = []
    for prop in common_props:
        is_common = all(
            var is variations[0] or any(compare_feature(prop, sf) for sf in var.structuralFeatures)
            for var in variations
        )
        if not is_common:
            optional_props.append(prop)
    common_props = [prop for prop in common_props if prop not in optional_props]
    for var in variations:
        for feat in var.structuralFeatures:
            feat.optional = not any(compare_feature(feat, comm_prop) for comm_prop in common_props)


def create_reference_matcher(elements: list[EObject]) -> ReferenceMatcher:
    """Montar um :class:`ReferenceMatcher` a partir das entidades raiz.

    Porte de ``createReferenceMatcher``
    (``DefaultReferenceMatcherCreator.java:20-30``) — colapsa a interface de
    um método só (``ReferenceMatcherCreator``, ``ReferenceMatcherCreator.java:12-14``)
    numa função, sem estado.

    Parameters
    ----------
    elements : list of EntityType
         Todas as entidades do modelo (raiz e não-raiz).

    Returns
    -------
    ReferenceMatcher
         Pronto para checar nomes de campo via ``maybe_match``.

    Notes
    -----
    Filtra só as raízes (``:22``, ``EntityType::isRoot`` → ``entity.root``).
    Para cada uma, monta um conjunto (``:24-28``) com 3 variações do nome —
    original, plural, singular — que colapsam se coincidirem (é um ``set``,
    não lista). Achata (``:29``) em pares ``(nome_variante, entidade)``, um
    por variação de nome, e passa pro construtor de ``ReferenceMatcher``.
    """
    roots = [entity for entity in elements if entity.root]

    new_list = []
    for entity in roots:
        new_set = dict.fromkeys(
            [
                entity.name,
                get_inflector().pluralize(entity.name),
                get_inflector().singularize(entity.name),
            ]
        )
        for new_name in new_set:
            new_list.append((new_name, entity))
    return ReferenceMatcher(new_list)


class ReferenceMatcher:
    """Decide se um nome de campo provavelmente referencia uma entidade raiz.

    Porte de ``ReferenceMatcher<T>``/``DefaultReferenceMatcher<T>``
    (``ReferenceMatcher.java:5-7``, ``DefaultReferenceMatcher.java:17-64``).
    Guarda estado real (a lista de regex já montada) — por isso é classe,
    ao contrário de ``set_optional_properties``/``sort_structural_variations``.
    """

    #: Afixos que sugerem referência (``DefaultReferenceMatcher.java:20-21``).
    affixes: ClassVar[list[str]] = ["id", "ptr", "ref", "ids", "refs", "has", ""]
    #: Separadores possíveis entre nome e afixo (``:23-24``).
    stop_chars: ClassVar[list[str]] = ["_", ".", "-", ""]
    #: Palavras que tornam improvável ser referência (``:27``).
    unlikely_words: ClassVar[list[str]] = ["count"]

    def __init__(self, pairs: list[tuple[str, EObject]]) -> None:
        """Montar a lista de padrões regex → entidade.

        Porte do construtor (``DefaultReferenceMatcher.java:35-54``).

        Parameters
        ----------
        pairs : list of tuple of (str, EntityType)
             Pares ``(nome_variante, entidade)``, vindos de
             :func:`create_reference_matcher`.

        Notes
        -----
        Pra cada par, pra cada afixo, pra cada separador, gera até 4
        padrões: dois "prefixo" (nome-antes-do-afixo e afixo-antes-do-nome,
        ambos incondicionais) e dois "sufixo" (mesma coisa, mas só quando
        **não** é o caso de separador **e** afixo serem os dois vazios ao
        mesmo tempo — senão o padrão viraria ``^.*?$``, que bate com
        qualquer string). O Java monta isso com 4 blocos de stream
        concatenados (``Stream.concat`` aninhado, ``:40-51``); aqui os 4
        nascem juntos, dentro do mesmo laço de separador — reorganização
        segura, porque todos os 4 desse laço apontam pra mesma entidade, e
        a ordem entre eles não afeta qual entidade ``maybe_match`` acha
        primeiro (só a ordem entre pares/afixos diferentes afetaria isso, e
        essa continua igual ao Java).
        """
        self.id_regexps = []
        for name, entity in pairs:
            for affix in self.affixes:
                for stop in self.stop_chars:
                    self.id_regexps.append((f"^{name}{stop}{affix}.*$".lower(), entity))
                    self.id_regexps.append((f"^{affix}{stop}{name}.*$".lower(), entity))
                    if stop != "" or affix != "":
                        self.id_regexps.append((f"^.*?{name}{stop}{affix}$".lower(), entity))
                        self.id_regexps.append((f"^.*?{affix}{stop}{name}$".lower(), entity))

    def maybe_match(self, field_id: str) -> EObject | None:
        """Achar a entidade que ``field_id`` provavelmente referencia.

        Porte de ``maybeMatch`` (``DefaultReferenceMatcher.java:57-63``).

        Parameters
        ----------
        field_id : str
             Nome do campo a testar.

        Returns
        -------
        EntityType or None
             A entidade encontrada, ou ``None`` se nada bateu (substitui o
             ``Optional`` do Java).

        Notes
        -----
        Primeiro rejeita nomes que contêm alguma ``unlikely_words``
        (``:59-60``). Senão, procura o **primeiro** padrão que bate com
        ``field_id`` **por inteiro** — ``String.matches()`` do Java exige
        casar a string inteira, não só uma parte, por isso ``re.fullmatch``
        e não ``re.match``/``re.search``. ``findFirst().map(...)``
        (``:62``) vira ``next(gerador, None)``, mesmo padrão já usado em
        ``_infer_object``/etc.
        """
        lowered = field_id.lower()
        if any(word in lowered for word in self.unlikely_words):
            return None
        return next(
            (entity for pattern, entity in self.id_regexps if re.fullmatch(pattern, lowered)),
            None,
        )
