"""``SchemaInference.infer`` — o núcleo da inferência (Fase 1.2).

Porte de ``SchemaInference.java``. Consome a lista de :class:`SchemaTriple`
(Fase 1.0, já validada por ``triples_from_rows``) e devolve
``rawEntities``: um mapa entidade → lista de variações estruturais
(:class:`~uschema.intermediate.raw.ObjectSC`).

Os seis passos, na ordem do original (``SchemaInference.java:125-146`` —
**não reordenar**, é *load-bearing*):

1. ``forEach`` das triplas, cada uma via ``infer`` recursivo.
2. Colapso inline de variações iguais (dentro do passo 1, por entidade).
3. ``joiner.joinAggregatedEntities`` — une entidades-alias (Fase 1.3a).
4. ``innerCountAndTimestampsAdjust`` — propaga meta pras entidades internas.
5. ``merger.mergeEquivalentEVs`` — funde variações equivalentes (Fase 1.3a).

Sobre o bug **#8** (``bugs_originais.md``): ao colapsar uma variação nova numa
já existente (abaixo, em :meth:`SchemaInference._infer_object`), o original
**não** combina metadados — ``retSchema = foundSchema.get();`` e mais nada
(``SchemaInference.java:207-211``). O ``schema.meta`` inteiro da ocorrência
nova — ``count`` **e** timestamps, não só bounds de array — é descartado.
Este módulo replica isso fielmente: **não** chama ``combine_metadata`` neste
ponto, de propósito.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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

#: `DefaultSchemaInferenceConfig.java:9` — único atributo ignorado na
#: inferência. É também o marcador de tipo (linha abaixo): por isso nunca
#: aparece como campo no modelo final.
_IGNORED_ATTRIBUTES: frozenset[str] = frozenset({"_type"})

#: `DefaultSchemaInferenceConfig.java:20`.
_TYPE_MARKER_ATTRIBUTE = "_type"

_Joiner = Callable[[dict[str, list[SchemaComponent]], set[str]], None]
_Merger = Callable[[dict[str, list[SchemaComponent]]], None]


def _java_string_sort_key(value: str) -> bytes:
    """Chave de ordenação que replica ``String.compareTo`` (Java, ``:191-194``).

    Java compara ``String`` por *code unit* UTF-16 (``char``), não por code
    point Unicode. Um caractere suplementar (fora do BMP) vira par substituto
    (``0xD800-0xDFFF``) nessa comparação — e o primeiro code unit do par fica
    numericamente **antes** da área de uso privado do BMP (``0xE000+``), mesmo
    que o code point representado seja maior. ``sorted()`` do Python compara
    por code point e diverge nesse caso; codificar em UTF-16 big-endian
    reproduz a ordem de ``char`` do Java. ``surrogatepass`` só entra em jogo
    se a string tiver substituto sem par (entrada mal-formada, não deveria
    ocorrer em nome de campo) — evita ``UnicodeEncodeError`` em vez de estourar.
    """
    return value.encode("utf-16-be", "surrogatepass")


class SchemaInference:
    """Infere ``rawEntities`` a partir de triplas — porte de ``SchemaInference.java``.

    Guice desaparece: ``joiner``/``merger`` entram por construtor, com as
    implementações da Fase 1.3a como default (não há `Null*` pra nenhum dos
    dois, ao contrário das estratégias de nível EMF da 1.3b).

    Notes
    -----
    **Uso único por instância.** ``raw_entities``/``inner_schema_names`` são
    inicializados no construtor, como no Java (``SchemaInference():63-68``), e
    nunca resetados dentro de :meth:`infer`. Chamar :meth:`infer` duas vezes na
    mesma instância acumularia estado entre as duas chamadas — fiel ao
    original, que tem o mesmo comportamento implícito.

    Parameters
    ----------
    joiner : callable, optional
        ``join_aggregated_entities`` da Fase 1.3a, por padrão.
    merger : callable, optional
        ``merge_equivalent_evs`` da Fase 1.3a, por padrão.
    ignored_attributes : frozenset of str, optional
        ``{"_type"}`` por padrão (``DefaultSchemaInferenceConfig``).
    type_marker_attribute : str, optional
        ``"_type"`` por padrão.
    """

    def __init__(
        self,
        joiner: _Joiner = join_aggregated_entities,
        merger: _Merger = merge_equivalent_evs,
        ignored_attributes: frozenset[str] = _IGNORED_ATTRIBUTES,
        type_marker_attribute: str = _TYPE_MARKER_ATTRIBUTE,
    ) -> None:
        self._joiner = joiner
        self._merger = merger
        self._ignored_attributes = ignored_attributes
        self._type_marker_attribute = type_marker_attribute

        # SchemaInference():65-67 — inicializados uma vez, não a cada infer().
        self._raw_entities: dict[str, list[SchemaComponent]] = {}
        self._inner_schema_names: set[str] = set()

    def infer(self, triples: list[SchemaTriple]) -> dict[str, list[SchemaComponent]]:
        """Inferir as árvores raw por entidade a partir das triplas.

        Porte de ``SchemaInference.infer(IAJArray)`` (``:125-146``). A
        validação (``validateRows``) já aconteceu na Fase 1.0
        (``triples_from_rows``); esta função assume triplas válidas.

        Parameters
        ----------
        triples : list of SchemaTriple
            Saída da Fase 2 (ou de ``triples_from_rows``), na ordem de
            entrada — a ordem decide qual variação é a primeira de cada
            entidade (``SchemaInference.java:204-211``).

        Returns
        -------
        dict of str to list of SchemaComponent
            ``raw_entities``: variações estruturais por nome de entidade.
        """
        for triple in triples:
            self._infer(
                triple.schema,
                None,
                is_root=True,
                meta=ObjectMetadata(triple.count, triple.first_timestamp, triple.last_timestamp),
            )

        self._joiner(self._raw_entities, self._inner_schema_names)
        self._inner_count_and_timestamps_adjust()
        self._merger(self._raw_entities)

        return self._raw_entities

    def _infer(
        self,
        value: Any,
        element_name: str | None,
        is_root: bool,
        meta: ObjectMetadata,
    ) -> SchemaComponent:
        """Despachar por tipo — porte de ``infer(IAJElement, …)`` (``:148-174``).

        Parameters
        ----------
        value : Any
            Nó do ``schema`` da tripla (dict, list, ou folha).
        element_name : str or None
            Nome do campo/posição que produziu ``value``. Só é ``None`` no
            objeto raiz (a chamada de ``infer()``, acima); todo outro
            caminho recebe um nome real — como no Java, que desembrulha o
            ``Optional`` (``elementName.get()``) nesses ramos.
        is_root : bool
            Se ``value`` é um documento de topo.
        meta : ObjectMetadata
            Metadado a atribuir (real, se raiz; zerado, se não).

        Returns
        -------
        SchemaComponent
            O componente inferido.
        """
        kind = classify(value)

        if kind is JsonKind.OBJECT:
            return self._infer_object(value, element_name, is_root, meta)

        # A partir daqui, `elementName` nunca é None por construção — só o
        # objeto raiz (tratado acima) é chamado sem nome.
        assert element_name is not None

        if kind is JsonKind.ARRAY:
            return self._infer_array(value, element_name)
        if kind is JsonKind.BOOLEAN:
            return BooleanSC()
        if kind is JsonKind.NUMBER:
            return NumberSC()
        if kind is JsonKind.NULL:
            return NullSC()
        if kind is JsonKind.TEXTUAL:
            return StringSC()
        if kind is JsonKind.OBJECT_ID:
            return ObjectIdSC()

        raise AssertionError(f"JsonKind não tratado: {kind!r}")  # inalcançável

    def _infer_object(
        self,
        obj: Mapping[str, Any],
        element_name: str | None,
        is_root: bool,
        meta: ObjectMetadata,
    ) -> SchemaComponent:
        """Porte de ``infer(IAJObject, …)`` (``:176-228``).

        Constrói o ``ObjectSC``, tenta colapsar com uma variação já
        registrada em ``raw_entities`` e devolve a sobrevivente (nova ou
        reaproveitada).
        """
        inflector = get_inflector()

        # `:182-183` — só o objeto raiz olha o marcador de tipo.
        type_name: str | None = None
        if is_root:
            type_value = obj.get(self._type_marker_attribute)
            if type_value is not None:
                type_name = inflector.capitalize(type_value)

        # `Inflector.capitalize` é `str | None -> str | None` (devolve `None`
        # só quando a entrada é `None`); aqui a entrada é sempre `str`
        # (`element_name or ""`), então o resultado nunca é `None` de fato —
        # o `assert` é só pra provar isso ao mypy, que não enxerga essa
        # relação pela assinatura genérica.
        capitalized_element_name = inflector.capitalize(element_name or "")
        assert capitalized_element_name is not None
        entity_name: str = type_name if type_name is not None else capitalized_element_name

        schema = ObjectSC(is_root=is_root, meta=meta)
        schema.entity_name = entity_name

        # `:191-194` — TreeSet = ordem natural de string, por code unit UTF-16.
        # `_java_string_sort_key` reproduz isso (ver docstring da função).
        fields = sorted(
            (f for f in obj if f not in self._ignored_attributes),
            key=_java_string_sort_key,
        )

        # `:197-198` — fase recursiva, um `ObjectMetadata()` zerado por campo:
        # a contagem real só existe no nível raiz, o resto vem depois via
        # `_inner_count_and_timestamps_adjust`.
        for f in fields:
            schema.add((f, self._infer(obj[f], f, False, ObjectMetadata())))

        # `:200-225` — tenta colapsar com uma variação já vista.
        entity_variations = self._raw_entities.get(entity_name)
        ret_schema: SchemaComponent = schema

        if entity_variations is not None:
            found = next((existing for existing in entity_variations if schema == existing), None)
            if found is not None:
                # `:207-211` — só `retSchema = foundSchema.get();`. NENHUM
                # combine de metadados aqui. O `meta` inteiro de `schema`
                # (count e timestamps da ocorrência nova) é descartado,
                # fielmente — ver #8 em `bugs_originais.md`. Não "consertar"
                # adicionando combine_metadata neste ponto.
                ret_schema = found
            else:
                entity_variations.append(schema)
        else:
            self._raw_entities[entity_name] = [schema]
            # `:223-224` — só entra em innerSchemaNames quando a entidade é
            # nova (este ramo), e só se não-raiz.
            if not is_root:
                self._inner_schema_names.add(entity_name)

        return ret_schema

    def _infer_array(self, values: Sequence[Any], element_name: str) -> SchemaComponent:
        """Porte de ``infer(IAJArray, String)`` (``:230-248``).

        Parameters
        ----------
        values : sequence
            Elementos do array, na ordem da tripla.
        element_name : str
            Nome do campo array; singularizado pro nome dos ``inners``.
        """
        schema = ArraySC()
        inflector = get_inflector()

        # `:236` — nome singular pros elementos do array.
        singular_name = inflector.singularize(element_name)
        assert singular_name is not None  # só é None se o input for None

        # `:240-245` — LinkedHashSet: dedup por __eq__/__hash__, preservando
        # ordem de inserção. `dict.fromkeys` é o idiom Python equivalente.
        inferred = (self._infer(v, singular_name, False, ObjectMetadata()) for v in values)
        deduped = dict.fromkeys(inferred)
        schema.add_all(list(deduped))

        return schema

    def _inner_count_and_timestamps_adjust(self) -> None:
        """Propagar meta das ocorrências-raiz pras entidades internas.

        Porte de ``innerCountAndTimestampsAdjust`` (``:92-113``). O autor
        original deixou um ``FIXME: I'm not sure this will work for n levels
        of aggregation`` (``:94``) — não investigado; ver
        ``bugs_originais.md``, seção "Incerteza declarada, adjacente ao #8".

        Notes
        -----
        ⚠️ **Sem guarda, de propósito.** Se o Joiner já removeu uma chave de
        ``raw_entities`` que ``inner_schema_names`` ainda referencia, o Java
        estoura ``NullPointerException`` no ``for``-each sobre ``null``; aqui
        o acesso direto ao dict estoura ``KeyError``. Decisão explícita:
        replicar fielmente, não guardar.
        """
        all_components = [sc for variations in self._raw_entities.values() for sc in variations]

        for inner_schema in self._inner_schema_names:
            for sch_component in self._raw_entities[inner_schema]:
                assert isinstance(sch_component, ObjectSC)
                non_root_obj = sch_component

                for sc in all_components:
                    assert isinstance(sc, ObjectSC)
                    if self._contains_schema_component(sc, non_root_obj):
                        assert non_root_obj.meta is not None
                        assert sc.meta is not None
                        non_root_obj.meta.combine_metadata(sc.meta)

    def _contains_schema_component(self, osc: ObjectSC, non_root_obj: ObjectSC) -> bool:
        """Porte de ``containsSchemaComponent`` (``:116-123``).

        ``True`` se algum campo de ``osc`` é um ``ArraySC`` cujos ``inners``
        contêm ``non_root_obj`` (por igualdade, como ``List.contains``), ou é
        o próprio ``non_root_obj`` (por igualdade, como ``ObjectSC``).
        """
        for _, inner in osc.inners:
            if isinstance(inner, ArraySC) and non_root_obj in inner.inners:
                return True
            if isinstance(inner, ObjectSC) and inner == non_root_obj:
                return True
        return False
