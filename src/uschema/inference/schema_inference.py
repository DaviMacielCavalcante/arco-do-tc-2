"""``SchemaInference.infer`` — o núcleo da inferência (Fase 1.2).

Porte de ``SchemaInference.java``. Consome a lista de :class:`SchemaTriple`
(Fase 1.0, já validada em ``extractors/triple.py``) e devolve
``raw_entities``: um mapa entidade → lista de variações estruturais
(:class:`~uschema.intermediate.raw.ObjectSC`).

Os cinco passos, na ordem do original (``SchemaInference.java:125-146`` —
**não reordenar**, é *load-bearing*):

1. ``forEach`` das triplas, cada uma via ``_infer`` recursivo.
2. Colapso inline de variações iguais (dentro do passo 1, por entidade, em
   ``_infer_object``).
3. ``joiner`` — une entidades-alias (Fase 1.3a, ``join_aggregated_entities``).
4. ``inner_count_and_time_stamps_adjust`` — propaga meta pras entidades
   internas.
5. ``merger`` — funde variações equivalentes (Fase 1.3a,
   ``merge_equivalent_evs``).

Sobre o bug **#8** (``bugs_originais.md``): ao colapsar uma variação nova numa
já existente (``_infer_object``), o original **não** combina metadados —
``retSchema = foundSchema.get();`` e mais nada (``:207-211``). O ``meta``
inteiro da ocorrência nova — ``count`` **e** timestamps, não só bounds de
array — é descartado. Este módulo replica isso fielmente: **não** chama
``combine_metadata`` nesse ponto, de propósito.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from uschema.extractors.triple import JsonKind, SchemaTriple, classify
from uschema.inference.strategies import join_aggregated_entities, merge_equivalent_evs
from uschema.intermediate.metadata import ObjectMetadata
from uschema.intermediate.raw import (
    ArraySC,
    BooleanSC,
    NullSC,
    NumberSC,
    ObjectIdSC,
    ObjectSC,
    SchemaComponent,
    StringSC,
)
from uschema.naming.inflector import get_instance as get_inflector

__all__ = ["SchemaInference"]

_IGNORED_ATTRIBUTES: frozenset[str] = frozenset({"_type"})
_TYPE_MARKER_ATTRIBUTE = "_type"

_Joiner = Callable[[dict[str, list[SchemaComponent]], set[str]], None]
_Merger = Callable[[dict[str, list[SchemaComponent]]], None]


class SchemaInference:
    """Núcleo da inferência: consome triplas, devolve ``rawEntities``.

    Porte de ``SchemaInference.java`` (``:43-276``). Ver a docstring do módulo
    para os cinco passos, na ordem em que ``infer`` os executa.
    """

    def __init__(
        self,
        joiner: _Joiner = join_aggregated_entities,
        merger: _Merger = merge_equivalent_evs,
        ignored_attributes: frozenset[str] = _IGNORED_ATTRIBUTES,
        type_marker_attribute: str = _TYPE_MARKER_ATTRIBUTE,
    ):
        """Inicializar o estado da inferência.

        Porte dos dois construtores do original (``:63-76``): o sem-argumentos
        (``:63-68``, usado pelo Guice) e o de injeção manual (``:70-76``).
        Aqui viram um construtor só, com defaults — sem framework de DI, cada
        ``@Inject`` do Java (``:45-52``) vira um parâmetro com o valor padrão
        de produção.

        Parameters
        ----------
        joiner : _Joiner, default join_aggregated_entities
            Estratégia da Fase 1.3a que une entidades-alias
            (``AliasedAggregatedEntityJoiner``, ``:48-49``).
        merger : _Merger, default merge_equivalent_evs
            Estratégia da Fase 1.3a que funde variações equivalentes
            (``EVariationMerger``, ``:45-46``).
        ignored_attributes : frozenset of str, default _IGNORED_ATTRIBUTES
            Achatamento de ``config.getIgnoredAttributes()`` (``:52``,
            ``SchemaInferenceConfig``) — o config só tinha getters, então vira
            parâmetro direto em vez de objeto.
        type_marker_attribute : str, default _TYPE_MARKER_ATTRIBUTE
            Achatamento de ``config.getTypeMarkerAttribute()`` (``:52``),
            mesma razão.

        Notes
        -----
        ``docArray`` (``:54``) e ``debug_type``/``DEBUG_TYPE`` (``:59,61``)
        não são portados: o primeiro é escrito e nunca relido: o segundo é
        sempre ``NO_DEBUG`` — código morto. ``ROOT_TYPE`` (``:58``, enum de 2
        valores) vira o parâmetro ``is_root: bool`` recebido em ``_infer``.
        """
        self._raw_entities: dict[str, list[SchemaComponent]] = {}
        self._inner_schema_names: set[str] = set()
        self._joiner: _Joiner = joiner
        self._merger: _Merger = merger
        self._type_marker_attribute = type_marker_attribute
        self._ignored_attributes = ignored_attributes

    def infer(self, triples: Iterable[SchemaTriple]) -> dict[str, list[SchemaComponent]]:
        """Inferir ``rawEntities`` a partir das triplas (Fase 1.0).

        Porte de ``infer(IAJArray rows)`` (``:125-146``), o método público.

        Parameters
        ----------
        triples : iterable of SchemaTriple
            Já validadas — ``validateRows`` (``:78-90``, ``:127-128``) não é
            reimplementado aqui: a validação de forma já acontece na Fase 1.0
            (``extractors/triple.py``), antes da tripla existir.

        Returns
        -------
        dict[str, list[SchemaComponent]]
            ``rawEntities``: entidade → lista de variações estruturais.

        Notes
        -----
        Os cinco passos, na ordem do original: (1) ``forEach`` recursivo
        (``:132-136``); (2) colapso inline, dentro de ``_infer_object``;
        (3) ``joiner`` (``:138``); (4) ``inner_count_and_time_stamps_adjust``
        (``:139``); (5) ``merger`` (``:140``). O print de debug (``:142-143``)
        é omitido — é código morto (ver ``__init__``).
        """
        for triple in triples:
            self._infer(
                triple.schema,
                name="",
                is_root=True,
                meta=ObjectMetadata(triple.count, triple.first_timestamp, triple.last_timestamp),
            )
        self._joiner(self._raw_entities, self._inner_schema_names)
        inner_count_and_time_stamps_adjust(self._inner_schema_names, self._raw_entities)
        self._merger(self._raw_entities)
        return self._raw_entities

    def _infer(self, value: Any, name: str, is_root: bool, meta: ObjectMetadata) -> SchemaComponent:
        """Despachar por tipo de valor JSON, via ``classify``.

        Porte do despachante privado ``infer(IAJElement, ...)`` (``:148-174``).

        Parameters
        ----------
        value : Any
            O valor JSON a inferir.
        name : str
            Nome do campo/elemento de origem (usado pelas folhas compostas).
        is_root : bool
            Substitui o ``ROOT_TYPE`` do Java (``:58``, ``:134``/``:198``).
        meta : ObjectMetadata
            Metadado a propagar para este nó.

        Returns
        -------
        SchemaComponent
            O componente inferido.

        Notes
        -----
        No Java, cada sobrecarga de ``infer`` é escolhida pelo compilador a
        partir do tipo estático de ``n`` (``n.isObject()``, ``n.isArray()``,
        etc., ``:150-169``). Sem sobrecarga em Python, isso colapsa num
        ``if/elif`` sobre ``JsonKind`` (``classify(value)``). O
        ``assert(false); return null;`` de guarda (``:171-173``) vira
        ``raise AssertionError`` — nunca deveria disparar, dado que
        ``JsonKind`` é exaustivo.
        """
        kind = classify(value)
        if kind is JsonKind.OBJECT:
            return self._infer_object(value, name, is_root, meta)
        elif kind is JsonKind.ARRAY:
            return self._infer_array(value, name)
        elif kind is JsonKind.BOOLEAN:
            return self._infer_boolean(value, name)
        elif kind is JsonKind.NUMBER:
            return self._infer_number(value, name)
        elif kind is JsonKind.NULL:
            return self._infer_null(value, name)
        elif kind is JsonKind.TEXTUAL:
            return self._infer_textual(value, name)
        elif kind is JsonKind.OBJECT_ID:
            return self._infer_object_id(value, name)
        else:
            raise AssertionError(f"classify() devolveu um JsonKind não tratado: {kind!r}")

    def _infer_object(
        self, value: Any, name: str, is_root: bool, meta: ObjectMetadata
    ) -> SchemaComponent:
        """Inferir um ``ObjectSC``, colapsando variações repetidas.

        Porte de ``infer(IAJObject, ...)`` (``:176-225``).

        Parameters
        ----------
        value : Mapping[str, Any]
            O objeto JSON.
        name : str
            Nome do campo de origem — usado como *fallback* de
            ``entity_name`` quando não há marcador de tipo.
        is_root : bool
            Se este objeto veio de um documento de topo (``:182``).
        meta : ObjectMetadata
            Metadado desta ocorrência.

        Returns
        -------
        SchemaComponent
            A variação nova, **ou** uma variação já existente e
            estruturalmente igual (colapso inline).

        Notes
        -----
        O nome da entidade (``:178-188``) só olha o marcador de tipo
        (``self._type_marker_attribute``) quando ``is_root``; sem
        marcador — ou não-raiz — cai no nome do campo, capitalizado pelo
        Inflector. Os campos são ordenados (``:190-194``, ``TreeSet<String>``)
        por ``_java_string_sort_key`` para casar com a ordenação UTF-16 do
        Java, não a ordenação por *code point* do ``sorted`` puro.

        **Bug #8** (ver ``bugs_originais.md``): quando uma variação já igual
        é encontrada (``:206-209``, ``foundSchema.isPresent()``), o original
        só faz ``retSchema = foundSchema.get();`` — **sem** combinar
        ``meta``. Aqui replicamos isso: devolvemos ``variation`` direto, sem
        chamar ``combine_metadata``. O ``meta`` da ocorrência nova é
        descartado de propósito.
        """
        if is_root:
            original_name = name

            another_name = value.get(self._type_marker_attribute)
            if another_name is not None:
                capitalized_name = get_inflector().capitalize(another_name)
            elif another_name is None:
                capitalized_name = get_inflector().capitalize(original_name)

        else:
            capitalized_name = get_inflector().capitalize(name)

        assert capitalized_name is not None
        schema = ObjectSC(is_root=is_root, meta=meta, entity_name=capitalized_name)

        sorted_fields = sorted(
            [field_name for field_name in value if field_name not in self._ignored_attributes],
            key=_java_string_sort_key,
        )

        for field_name in sorted_fields:
            result = self._infer(value[field_name], field_name, False, ObjectMetadata())
            schema.add((field_name, result))

        entity_variations = self._raw_entities.get(capitalized_name)
        if entity_variations is not None:
            for variation in entity_variations:
                if variation == schema:
                    return variation

            entity_variations.append(schema)
            return schema
        else:
            new_list: list[SchemaComponent] = [schema]

            self._raw_entities[capitalized_name] = new_list
            if not is_root:
                self._inner_schema_names.add(capitalized_name)
            return schema

    def _infer_array(self, value: Any, name: str) -> ArraySC:
        """Inferir um ``ArraySC``, deduplicando elementos consecutivos-ou-não.

        Porte de ``infer(IAJArray n, String elementName)`` (``:227-245``).

        Parameters
        ----------
        value : Sequence[Any]
            O array JSON.
        name : str
            Nome do campo de origem; é singularizado (``:232-235``) antes de
            nomear os elementos internos.

        Returns
        -------
        SchemaComponent
            Um ``ArraySC`` com os elementos deduplicados adicionados.

        Notes
        -----
        O original usa ``LinkedHashSet`` (``:237-242``) para simplificar
        ``Aggr{V1, V2, V2, V2...V2}`` em ``Aggr{V1, V2}`` — dedup preservando
        a ordem de primeira aparição, antes mesmo de entrar no ``ArraySC``
        (que tem sua própria lógica de homogeneidade, ver ``raw.py``). Aqui,
        ``dict.fromkeys(save)`` faz o mesmo papel, apoiado no
        ``__eq__``/``__hash__`` de ``SchemaComponent``.
        """
        single_name = get_inflector().singularize(name)
        assert single_name is not None
        save = []
        for element in value:
            save.append(self._infer(element, single_name, is_root=False, meta=ObjectMetadata()))

        dedup = list(dict.fromkeys(save))

        new_array = ArraySC()
        new_array.add_all(dedup)
        return new_array

    def _infer_boolean(self, value: Any, name: str) -> BooleanSC:
        """Folha booleana, sem estado (``infer(IAJBoolean, ...)``, ``:247-251``)."""
        return BooleanSC()

    def _infer_number(self, value: Any, name: str) -> NumberSC:
        """Folha numérica, sem estado (``infer(IAJNumber, ...)``, ``:253-257``)."""
        return NumberSC()

    def _infer_textual(self, value: Any, name: str) -> StringSC:
        """Folha textual, sem estado (``infer(IAJTextual, ...)``, ``:265-269``)."""
        return StringSC()

    def _infer_null(self, value: Any, name: str) -> NullSC:
        """Folha nula, sem estado (``infer(IAJNull, ...)``, ``:259-263``)."""
        return NullSC()

    def _infer_object_id(self, value: Any, name: str) -> ObjectIdSC:
        """Folha ``ObjectId``, sem estado (``infer(IAJObjectId, ...)``, ``:271-275``)."""
        return ObjectIdSC()


def _java_string_sort_key(value: str) -> bytes:
    """Chave de ordenação equivalente ao ``TreeSet<String>`` do Java.

    Usada em ``_infer_object`` (``SchemaInference.java:190-194``) para
    ordenar os nomes de campo antes de montar ``ObjectSC.inners`` — a ordem
    entra no ``__eq__`` (ver ``raw.py``), então precisa bater com o Java.

    Parameters
    ----------
    value : str
        O nome do campo.

    Returns
    -------
    bytes
        ``value`` codificado em UTF-16-BE.

    Notes
    -----
    ``String.compareTo``/``TreeSet<String>`` comparam por *code unit* UTF-16;
    o ``sorted()`` do Python compara por *code point*. Divergem só em
    caracteres do plano suplementar (raros) — codificar para UTF-16-BE antes
    de comparar reproduz a ordem do Java nesses casos.
    """
    return value.encode("utf-16-be", "surrogatepass")


def inner_count_and_time_stamps_adjust(
    inner_schema_names: set[str], raw_entities: dict[str, list[SchemaComponent]]
) -> None:
    """Propagar ``meta`` das ocorrências-raiz para as entidades internas.

    Porte de ``innerCountAndTimestampsAdjust`` (``SchemaInference.java:92-114``).
    Entidades não-raiz nascem com ``ObjectMetadata()`` zerado (``_infer_object``,
    ramo não-raiz); este passo varre todas as variações já inferidas e
    combina o ``meta`` de quem efetivamente contém cada objeto não-raiz.

    Parameters
    ----------
    inner_schema_names : set of str
        Nomes de entidade marcados como não-raiz (``self._inner_schema_names``).
    raw_entities : dict[str, list[SchemaComponent]]
        Todas as variações inferidas até aqui (``self._raw_entities``).

    Notes
    -----
    O original tem um ``FIXME`` (``:94``): *"I'm not sure this will work for
    n levels of aggregation"* — mantido aqui sem tentar consertar, por
    fidelidade. Ver **M2** em ``bugs_originais.md``.
    """
    all_schema_components = [item for raw in raw_entities.values() for item in raw]
    for inner_schema in inner_schema_names:
        for non_root_obj in raw_entities[inner_schema]:
            assert isinstance(non_root_obj, ObjectSC)
            for sc in all_schema_components:
                assert isinstance(sc, ObjectSC)
                if contains_schema_component(sc, non_root_obj):
                    assert isinstance(sc.meta, ObjectMetadata)
                    assert isinstance(non_root_obj.meta, ObjectMetadata)
                    non_root_obj.meta.combine_metadata(sc.meta)


def contains_schema_component(sc: ObjectSC, non_root_obj: ObjectSC) -> bool:
    """Testar se ``non_root_obj`` aparece em algum campo de ``sc``.

    Porte de ``containsSchemaComponent(ObjectSC osc, ObjectSC nonRootObj)``
    (``SchemaInference.java:116-123``).

    Parameters
    ----------
    sc : ObjectSC
        O container candidato — cada valor de campo é testado.
    non_root_obj : ObjectSC
        O objeto não-raiz procurado.

    Returns
    -------
    bool
        ``True`` se algum campo de ``sc`` é ``non_root_obj`` diretamente
        (``ObjectSC``, igualdade estrutural), ou um ``ArraySC`` que o contém
        entre seus elementos.

    Notes
    -----
    Porte do ``anyMatch`` sobre ``osc.getInners()`` (``:119-122``): o Java
    testa primeiro o ramo ``ArraySC`` e depois o ``ObjectSC`` (``||``); aqui
    a ordem está invertida — equivalente, já que ``or``/``||`` são
    comutativos em resultado (só muda a ordem de avaliação, não o valor).
    """
    return any(
        (isinstance(field_value, ObjectSC) and field_value == non_root_obj)
        or (
            isinstance(field_value, ArraySC)
            and any(inner_field == non_root_obj for inner_field in field_value.inners)
        )
        for field_name, field_value in sc.inners
    )
