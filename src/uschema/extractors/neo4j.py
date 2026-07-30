"""Extrator Neo4j — porte de ``SparkProcess``/``IdArchetypeMapping``/``TypeUtils``.

Porte fiel de ``neo4j2uschema/spark/*`` + ``neo4j2uschema/utils/TypeUtils.java``.
Este módulo cobre só a **camada de extração** (arquétipos por nó + contagem por
valor distinto) — a **camada de construção do modelo** (``USchemaBuilder``,
``StructuralVariationBuilder``, ``AttributeOptionalsChecker``,
``IgnoreSimilarReferenceBoundsProcessor``) é um módulo separado, porque **não é
a Fase 1**: ver o achado no topo de ``todolist_fase2.md`` §2.2.

Mecanismo do oráculo (``SparkProcess.java:50-121``)
-----------------------------------------------------
Duas *cypher*, não um ``find()`` direto:

1. ``MATCH (n) RETURN DISTINCT labels(n)`` (``:102-105``) — lista as combinações
   de labels existentes no banco.
2. Por combinação: ``MATCH (n:Labels) WHERE size(labels(n))=N WITH n OPTIONAL
   MATCH (n)-[r]->(m) RETURN n, r, labels(m)`` (``:107-114``) — uma linha por
   (nó, relacionamento de saída); ``OPTIONAL MATCH`` garante uma linha (com
   ``r``/``m`` nulos) mesmo pra nó sem saída.

O pipeline por linha, então:

.. code-block:: java

    .mapToPair(new IdArchetypeMapping())      // linha -> (id do nó, arquétipo da linha)
    .reduceByKey(new ReduceByIdArchetype())   // funde por nó: união das referências distintas
    .flatMap(new SplitMapping())              // nó -> [nó completo, cada referência distinta]
    .countByValue();                          // conta ocorrências de cada valor exato

Este módulo porta isso como ``node_archetype`` (:func:`node_archetype`),
``reduce_archetypes_by_node`` e ``build_archetype_counts`` — funções puras,
sem I/O — mais ``extract_database_archetype_counts``/``extract_archetype_counts``
(a conexão via ``neo4j`` nativo).

Por que **sem** o round-trip de texto JSON (e o que isso exige preservar)
----------------------------------------------------------------------------
``SplitMapping.generateJsonText`` serializa cada arquétipo pra **texto**;
``.countByValue()`` conta strings exatas; ``Json2USchemaModel`` faz
``new JSONObject(string)`` pra **reler**. Este porte pula o texto — mesma
decisão do Mongo (``extractors/mongo.py``, "Como os tipos viajam") — e produz
os arquétipos como ``dict`` nativo direto, agrupando por uma chave canônica
(:func:`_canonical_key`, igual a ``extractors.mongo._canonical_schema_key``).

**Isso só é seguro porque duas consequências observáveis do round-trip foram
verificadas na fonte e são replicadas explicitamente em** :func:`get_type_name`
(não em :func:`obtain_type` — a contagem/agrupamento acontece **antes** do
round-trip no Java, então usa os tipos "crus"; só a nomeação do tipo do
``Attribute``, que só acontece depois de reler o texto, é afetada):

1. **``Long`` (inteiro Neo4j) sempre vira ``"integer"``, nunca ``"long"``.**
   A sentinela de ``INTEGER`` é sempre o valor fixo ``0L`` (``TypeUtils.java:31``,
   ``SHORT_LONG``); ``Long.toString(0L)`` é o texto ``"0"``, sem sufixo; ao
   reler, ``org.json`` (``json:20180130``, verificado no fonte de
   ``JSONObject.stringToValue`` — tenta ``Integer`` antes de ``Long``, só sobe
   pra ``Long``/``BigInteger`` se o valor não couber em 32 bits) devolve
   sempre ``Integer``, nunca ``Long``, pro texto ``"0"``. Logo
   ``TypeUtils.geetSimpleType`` (que testa ``instanceof Long`` **antes** de
   ``instanceof Integer``) nunca vê um ``Long`` de verdade — o ramo ``"long"``
   é **código morto** no caminho real. `getTypeName` é chamado só sobre valores
   já relidos (``StructuralVariationBuilder.java:85``,
   ``TypeUtils.getTypeName(properties.get(name))`` — ``properties`` é sempre um
   ``JSONObject`` parseado, nunca o ``TreeMap`` cru).
2. **Lista heterogênea ou vazia sempre vira ``"string[]"``, nunca ``"any[]"``.**
   ``TypeUtils.obtainType(Iterable)`` devolve o literal ``"any"`` (uma
   ``String`` Java) quando os tipos não convergem pra 1 só (inclui lista
   vazia, 0 tipos distintos). Essa string, embutida no array-literal que
   ``addProperties`` monta (``["any"]``) e revertida por
   ``generateJsonText``/``JSONArray`` na releitura, chega em
   ``TypeUtils.getTypeName`` como uma ``String`` Java comum — e
   ``geetSimpleType`` não olha o *conteúdo* da string, só o *tipo* — qualquer
   ``String`` vira ``"string"``. O marcador ``"any"`` nunca sobrevive ao
   round-trip como um tipo especial.

Como :func:`obtain_type` já devolve tipos Python "nativos" (``bool``/``str``/
``float``/``int``, nunca uma distinção "era ``Long``"), e :func:`get_type_name`
despacha **pelo tipo Python do valor, não pelo conteúdo**, as duas
consequências acima saem **de graça** do despacho por tipo — não é preciso
nenhuma lógica especial pra "fingir" o round-trip. Isso só funciona porque as
duas conclusões acima foram verificadas contra o fonte real do ``org.json``
pinado (`JSONObject.stringToValue`, tag ``20180130``) — não são suposição.

Uma armadilha de tradução igual à do Mongo (``bool``/``int``)
------------------------------------------------------------------
Em Python, ``bool`` é subclasse de ``int`` (mesma armadilha de
``extractors/mongo.py``). :func:`obtain_type` despacha ``list`` → ``bool`` →
``str`` → ``float`` → ``int``, nessa ordem — trocar ``bool``/``int`` faz
booleano virar sentinela de inteiro em silêncio. A deduplicação de tipos numa
lista heterogênea (:func:`_list_sentinel`) tem o mesmo cuidado:
``False == 0`` em Python, então comparar por igualdade de valor confundiria
``[True, 5]`` com um array homogêneo; a chave de deduplicação inclui o
``type()`` do valor, não só o valor.

Uma assimetria do oráculo a preservar (labels próprios vs. labels do alvo)
------------------------------------------------------------------------------
``IdArchetypeMapping.nodeToJSONObject`` ordena os **próprios** labels do nó
antes de montar o campo ``labels`` (``.sorted()``, ``:60-62``) — e é esse valor
ordenado que vira o nome do ``EntityType`` (``StructuralVariationBuilder``,
``String.join("_AND_", labels)``). Mas ``addRelationships`` **não** ordena
``targetLabels`` (``:100-104``, sem ``.sorted()``) — o ``refsTo`` de uma
referência usa a ordem crua que ``labels(m)`` devolveu. Pra um nó
multi-label que também é alvo de alguma relação, isso pode gerar **dois**
``EntityType`` nominalmente diferentes pro mesmo nó (um pela ordem "própria",
outro pela ordem "de referência") — **confirmado com dado real** (Neo4j Aura,
27/07/2026, via ``scripts/verificar_extracao_neo4j.py``): um nó ``:Zebra:Apple``
produziu ``Apple_AND_Zebra`` (variação real) e ``Zebra_AND_Apple`` (placeholder
vazio) como dois ``EntityType`` distintos. Catalogado como ``N1`` em
``bugs_originais.md``. Este módulo **preserva a assimetria**
(:func:`node_archetype` ordena; :func:`_relationship_archetype` não) — decisão
de fidelidade, não um bug do porte.

Tipos Neo4j sem sentinela dedicada
-------------------------------------
``TypeUtils.obtainType`` só reconhece ``LIST``/``BOOLEAN``/``STRING``/
``FLOAT``/``INTEGER`` (``TYPE_SYSTEM``); qualquer outro tipo Cypher
(``Duration``, ``Point``, ``Date``/``Time``/``DateTime``, ``ByteArray``) cai no
``return NULL`` final (``:47``) — a string literal ``"null"``, que sobrevive o
round-trip como ``String`` comum e vira ``"string"`` em :func:`get_type_name`.
Comportamento observável do oráculo: nenhuma exceção, silenciosamente vira
"string". Diferente do Mongo, que lança pra tipo não suportado
(``extractors.mongo.simplify``) — não uniformizar os dois; cada um replica o
que o respectivo oráculo faz.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Protocol

from neo4j import Driver, RoutingControl

__all__ = [
    "build_archetype_counts",
    "extract_archetype_counts",
    "extract_database_archetype_counts",
    "get_type_name",
    "node_archetype",
    "obtain_type",
    "reduce_archetypes_by_node",
]


class _EntityLike(Protocol):
    """Superfície comum a ``Node``/``Relationship`` que este módulo usa.

    Espelha ``org.neo4j.driver.types.Entity`` (a interface Java que
    ``Node``/``Relationship`` implementam — ``IdArchetypeMapping.java`` importa
    ``Entity``, não uma classe concreta). Um ``Protocol``, não
    ``neo4j.graph.Node``/``Relationship`` diretamente, porque essas classes
    concretas exigem um ``Graph`` pra construir — dificultaria testar sem
    banco (mesma razão de ``extractors.mongo`` aceitar ``Mapping``, não
    ``bson.Document``).
    """

    def keys(self) -> Iterator[str]: ...
    def __getitem__(self, key: str) -> Any: ...


class _NodeLike(_EntityLike, Protocol):
    """Espelha ``org.neo4j.driver.types.Node`` — ``Entity`` + ``labels()``."""

    @property
    def element_id(self) -> str: ...
    @property
    def labels(self) -> Iterable[str]: ...


class _RelationshipLike(_EntityLike, Protocol):
    """Espelha ``org.neo4j.driver.types.Relationship`` — ``Entity`` + ``type()``."""

    type: str


#: Sentinela pra tipo Cypher fora de LIST/BOOLEAN/STRING/FLOAT/INTEGER
#: (``TypeUtils.java:47``, ``NULL``). É uma *string*, não ``None`` — sobrevive
#: ao round-trip de JSON do oráculo como texto comum (ver docstring do módulo).
_SENTINEL_OTHER = "null"

#: Marcador de "tipos não convergem pra 1 só" numa lista
#: (``TypeUtils.java:58``, ``ANY``) — usado só dentro de :func:`_list_sentinel`;
#: nunca sobrevive como conceito distinto em :func:`get_type_name` (vira
#: ``"string"`` pelo despacho por tipo Python, não por conteúdo — ver docstring).
_ANY_MARKER = "any"


def obtain_type(value: Any) -> Any:
    """Traduzir um valor de propriedade Neo4j pra sentinela do seu tipo.

    Porte de ``TypeUtils.obtainType(Value)`` (``TypeUtils.java:34-48``). O
    driver Python já desserializa Bolt em tipos nativos, então o despacho é
    por ``isinstance`` — na ordem **``list`` → ``bool`` → ``str`` → ``float``
    → ``int``**, obrigatória porque ``bool`` é subclasse de ``int`` em Python
    (armadilha igual à de ``extractors.mongo._simplify_value``; ver docstring
    do módulo).

    Parameters
    ----------
    value : Any
        Um valor de propriedade, como devolvido pelo driver ``neo4j``
        (``Node``/``Relationship`` são ``Mapping``; ``value = entity[key]``).

    Returns
    -------
    Any
        ``False`` (``BOOLEAN``), ``"s"`` (``STRING``), ``0.0`` (``FLOAT``),
        ``0`` (``INTEGER``), uma lista de 1 elemento com a sentinela do tipo
        homogêneo — ou ``["any"]`` se a lista for vazia ou heterogênea
        (``LIST``, recursivo) — ou a string ``"null"`` pra qualquer outro tipo
        Cypher (``TypeUtils.java:47``; não lança — comportamento observável do
        oráculo, ver docstring do módulo).
    """
    if isinstance(value, list):
        return [_list_sentinel(value)]
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return "s"
    if isinstance(value, float):
        return 0.0
    if isinstance(value, int):
        return 0

    return _SENTINEL_OTHER


def _list_sentinel(values: list[Any]) -> Any:
    """Colapsar os tipos de uma lista pra 1 sentinela, ou ``"any"``.

    Porte de ``TypeUtils.obtainType(Iterable<Value>)`` (``TypeUtils.java:51-59``):
    lista vazia ou com mais de 1 tipo distinto vira ``"any"`` (marcador que,
    no despacho de :func:`get_type_name`, se torna indistinguível de uma
    ``str`` comum — é assim que o oráculo perde essa distinção também, ver
    docstring do módulo). A deduplicação usa ``type()`` **e** valor — não só
    valor — porque ``False == 0`` em Python confundiria ``bool``/``int``.
    """
    distinct: dict[tuple[type[Any], Any], Any] = {}
    for element in values:
        sentinel = obtain_type(element)
        key = (type(sentinel), _hashable(sentinel))
        distinct.setdefault(key, sentinel)

    if len(distinct) == 1:
        return next(iter(distinct.values()))
    return _ANY_MARKER


def _hashable(sentinel: Any) -> Any:
    """Versão hasheável de uma sentinela, recursiva pra listas aninhadas.

    Neo4j não permite lista aninhada como valor de propriedade (arrays só de
    tipo primitivo homogêneo) — na prática :func:`obtain_type` nunca produz
    aninhamento de mais de 1 nível a partir de dado real. Ainda assim, uma
    conversão rasa (só ``tuple(sentinel)`` no nível externo) deixaria uma
    lista aninhada intacta dentro da tupla, e ``dict`` não aceita chave com
    lista — ``TypeError: unhashable type``. Recursivo por segurança; o custo
    extra é irrelevante.
    """
    if isinstance(sentinel, list):
        return tuple(_hashable(element) for element in sentinel)
    return sentinel


def get_type_name(sentinel: Any) -> str:
    """Nome do tipo do ``Attribute`` a partir da sentinela de :func:`obtain_type`.

    Porte de ``TypeUtils.getTypeName``/``geetSimpleType``
    (``TypeUtils.java:62-90``), com as duas consequências do round-trip de
    JSON do oráculo **já embutidas** no despacho por tipo Python — ver a seção
    "Por que sem o round-trip" no docstring do módulo para a derivação
    completa e verificada: ``int`` (a sentinela de ``INTEGER``) sempre vira
    ``"integer"`` (nunca ``"long"``); uma lista vazia/heterogênea (sentinela
    interna ``"any"``, uma ``str``) sempre vira ``"string[]"`` (nunca
    ``"any[]"``).

    Parameters
    ----------
    sentinel : Any
        Saída de :func:`obtain_type` pra uma propriedade.

    Returns
    -------
    str
        ``"boolean"``/``"string"``/``"double"``/``"integer"``, com sufixo
        ``"[]"`` se ``sentinel`` for uma lista (nome do tipo do primeiro —
        único — elemento); ``"any"`` no ``else`` final
        (``TypeUtils.java:89``), inalcançável a partir de :func:`obtain_type`
        (que nunca devolve uma lista vazia), mantido por fidelidade ao ramo
        Java.
    """
    if isinstance(sentinel, list):
        if len(sentinel) > 0:
            return _simple_type_name(sentinel[0]) + "[]"
        return _simple_type_name(sentinel)

    return _simple_type_name(sentinel)


def _simple_type_name(sentinel: Any) -> str:
    """Porte de ``TypeUtils.geetSimpleType`` (``TypeUtils.java:75-90``).

    Ordem **``bool`` → ``str`` → ``float`` → ``int``**, mesma razão de
    :func:`obtain_type`: ``bool`` é subclasse de ``int`` em Python.
    """
    if isinstance(sentinel, bool):
        return "boolean"
    if isinstance(sentinel, str):
        return "string"
    if isinstance(sentinel, float):
        return "double"
    if isinstance(sentinel, int):
        return "integer"

    return _ANY_MARKER


def node_archetype(
    node: _NodeLike, relationship: _RelationshipLike | None, target_labels: list[str] | None
) -> dict[str, Any]:
    """Montar o arquétipo de uma linha (nó + no máximo 1 relacionamento de saída).

    Porte de ``IdArchetypeMapping.nodeToJSONObject`` (``IdArchetypeMapping.java:57-68``).
    Os labels **próprios** do nó são ordenados (``:60-62``) — diferente do
    ``refsTo`` de uma referência (:func:`_relationship_archetype`), que não é
    — ver "Uma assimetria do oráculo a preservar" no docstring do módulo.

    Parameters
    ----------
    node : Node-like
        O nó da linha (``row.get(0)`` no Java); qualquer objeto com
        ``.element_id``/``.labels``/``.keys()``/``__getitem__`` (o real
        ``neo4j.graph.Node`` satisfaz isso).
    relationship : Relationship-like or None
        O relacionamento de saída da linha, se houver (``OPTIONAL MATCH`` pode
        devolver ``None``).
    target_labels : list of str or None
        Labels do nó-alvo do relacionamento (``labels(m)``); ``None`` junto
        com ``relationship`` ``None`` (mesma linha, ``:42`` — os dois nulos
        juntos, nunca só um).

    Returns
    -------
    dict of str to Any
        ``{"labels": [...], "entity": "node", "properties": {...},
        "references": [...]}`` — ``references`` tem **no máximo 1** elemento
        (o desta linha); a união entre linhas do mesmo nó é
        :func:`reduce_archetypes_by_node`.
    """
    return {
        "labels": sorted(node.labels),
        "entity": "node",
        "properties": _entity_properties(node),
        "references": _references(relationship, target_labels),
    }


def _entity_properties(entity: _NodeLike | _RelationshipLike) -> dict[str, Any]:
    """Porte de ``IdArchetypeMapping.addProperties`` (``:70-82``), sem a montagem de texto.

    ``Node``/``Relationship`` do driver não são ``dict`` de verdade (só
    ``Mapping``); ``.keys()`` explícito espelha ``entity.keys()`` do Java.
    """
    return {key: obtain_type(entity[key]) for key in entity.keys()}  # noqa: SIM118


def _references(
    relationship: _RelationshipLike | None, target_labels: list[str] | None
) -> list[dict[str, Any]]:
    if relationship is None or target_labels is None:
        return []
    return [_relationship_archetype(relationship, target_labels)]


def _relationship_archetype(
    relationship: _RelationshipLike, target_labels: list[str]
) -> dict[str, Any]:
    """Arquétipo de um relacionamento isolado.

    Porte do ramo com aresta de ``IdArchetypeMapping.addRelationships``
    (``IdArchetypeMapping.java:96-109``). ``refsTo`` **não** é ordenado — usa a
    ordem crua de ``target_labels`` (``labels(m)`` do Cypher), diferente dos
    labels próprios do nó em :func:`node_archetype`. Ver "Uma assimetria do
    oráculo a preservar" no docstring do módulo.
    """
    return {
        "type": relationship.type,
        "refsTo": list(target_labels),
        "entity": "relationship",
        "properties": _entity_properties(relationship),
    }


def _canonical_key(value: Mapping[str, Any]) -> str:
    """Chave de agrupamento estrutural — mesmo mecanismo de ``extractors.mongo``.

    Aqui faz o papel do texto exato que ``.countByValue()`` compara no Java;
    como este porte nunca serializa de verdade (ver docstring do módulo), a
    "string exata" vira esta chave canônica.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def reduce_archetypes_by_node(
    rows: Iterable[tuple[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Fundir os arquétipos de linha por nó — união das referências distintas.

    Porte de ``ReduceByIdArchetype.call`` (``ReduceByIdArchetype.java:16-23``),
    aplicado sobre **todas** as linhas de uma vez (o Java faz isso incremental
    via ``reduceByKey`` do Spark; o resultado final é o mesmo — a combinação é
    comutativa e associativa, mesma garantia já usada em
    ``extractors.mongo.reduce_pairs``). ``labels``/``entity``/``properties``
    vêm do **primeiro** arquétipo de cada nó (idênticos em toda linha do mesmo
    nó — o Cypher refaz o ``MATCH`` do nó a cada linha); só ``references``
    muda, por deduplicação estrutural (:func:`_canonical_key`, equivalente ao
    ``TreeSet`` do Java).

    Parameters
    ----------
    rows : iterable of (str, dict)
        Pares ``(id do nó, arquétipo da linha)`` — id é qualquer valor estável
        por nó dentro da mesma leitura (este porte usa ``node.element_id``,
        não ``node.id`` — descontinuado no driver 6.x; não muda o resultado,
        só a implementação da chave interna de fusão).

    Returns
    -------
    dict of str to dict
        Um arquétipo por nó, com ``references`` já unidas.
    """
    merged: dict[str, dict[str, Any]] = {}
    seen_reference_keys: dict[str, dict[str, dict[str, Any]]] = {}

    for node_id, archetype in rows:
        if node_id not in merged:
            merged[node_id] = {**archetype, "references": []}
            seen_reference_keys[node_id] = {}

        references_by_key = seen_reference_keys[node_id]
        for reference in archetype["references"]:
            key = _canonical_key(reference)
            if key not in references_by_key:
                references_by_key[key] = reference
                merged[node_id]["references"].append(reference)

    return merged


def build_archetype_counts(merged: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Explodir cada nó em (nó completo + cada referência distinta) e contar.

    Porte de ``SplitMapping.call`` (``SplitMapping.java:30-41``) seguido de
    ``.countByValue()`` (``SparkProcess.java:99``). Duas famílias de arquétipo
    coexistem na saída: **nó completo** (``entity: "node"``, conta variações
    de ``EntityType``) e **referência isolada** (``entity: "relationship"``,
    conta — por construção do ``references`` já deduplicado em
    :func:`reduce_archetypes_by_node` — quantos **nós de origem distintos**
    têm aquele relacionamento, não o total bruto de arestas).

    Parameters
    ----------
    merged : mapping of str to mapping
        Saída de :func:`reduce_archetypes_by_node`.

    Returns
    -------
    list of dict of str to Any
        Uma linha por arquétipo distinto (nó ou referência), no formato
        ``{"archetype": {...}, "count": N}`` — a chave de agrupamento
        (:func:`_canonical_key`) já não aparece na saída, só o efeito dela.
    """
    counts: dict[str, int] = {}
    archetypes: dict[str, Mapping[str, Any]] = {}

    for node_archetype_ in merged.values():
        _tally(node_archetype_, counts, archetypes)
        for reference in node_archetype_["references"]:
            _tally(reference, counts, archetypes)

    return [{"archetype": archetypes[key], "count": count} for key, count in counts.items()]


def _tally(
    archetype: Mapping[str, Any], counts: dict[str, int], archetypes: dict[str, Mapping[str, Any]]
) -> None:
    key = _canonical_key(archetype)
    counts[key] = counts.get(key, 0) + 1
    archetypes.setdefault(key, archetype)


def extract_archetype_counts(
    rows: Iterable[tuple[_NodeLike, _RelationshipLike | None, list[str] | None]],
) -> list[dict[str, Any]]:
    """Pipeline completo de extração, dado um iterável de linhas já lidas.

    Junta :func:`node_archetype` + :func:`reduce_archetypes_by_node` +
    :func:`build_archetype_counts` — a contraparte, sem I/O, de
    :func:`extract_database_archetype_counts`. Separado para ser testável sem
    banco (mesmo papel que ``build_triples`` tem em ``extractors.mongo``).

    Parameters
    ----------
    rows : iterable of (Node-like, Relationship-like or None, list of str or None)
        Uma tripla ``(n, r, labels(m))`` por linha do Cypher — ver
        :func:`node_archetype`.

    Returns
    -------
    list of dict of str to Any
        Ver :func:`build_archetype_counts`.
    """
    per_row = (
        (node.element_id, node_archetype(node, relationship, target_labels))
        for node, relationship, target_labels in rows
    )
    merged = reduce_archetypes_by_node(per_row)
    return build_archetype_counts(merged)


def extract_database_archetype_counts(
    driver: Driver, database: str | None = None, sampling_rate: float = 1.0
) -> list[dict[str, Any]]:
    """Ler o banco via driver nativo e montar os arquétipos com contagem.

    Porte de ``SparkProcess.process`` (``SparkProcess.java:50-75``) — duas
    *cypher* (ver "Mecanismo do oráculo" no docstring do módulo), driver
    nativo (``neo4j.Driver.execute_query``), não o conector Spark (ver
    ``fase2_decisao_leitura_mongo_neo4j.md``). Pura-Python, mesma decisão do
    Mongo (``todolist_fase2.md`` §2.0) — Spark, se entrar, é paralelizador
    futuro sobre isto, não um requisito.

    Parameters
    ----------
    driver : neo4j.Driver
        Driver já conectado (``neo4j.GraphDatabase.driver(...)``); quem
        abre/fecha é o chamador.
    database : str, optional
        Nome do banco (``None`` usa o banco padrão do driver — o oráculo lia
        sempre o banco padrão ``neo4j``, pré multi-database).
    sampling_rate : float, default 1.0
        Porte de ``SparkProcess``'s ``samplingRate`` (``:41-48``,
        ``IllegalArgumentException`` se fora de ``(0, 1]`` — aqui
        ``ValueError``). O oráculo que gerou os XMIs de referência sempre
        rodou com ``1.0`` (``Neo4j2USchemaMain.java:18``, ``SAMPLING_RATIO``).

    Returns
    -------
    list of dict of str to Any
        Ver :func:`build_archetype_counts`.

    Raises
    ------
    ValueError
        Se ``sampling_rate`` for ``<= 0`` ou ``> 1`` — porte de
        ``SparkProcess.java:43``.
    """
    if sampling_rate <= 0 or sampling_rate > 1:
        raise ValueError(f"Sampling rate <= 0 or > 1, Value: {sampling_rate}")

    def _rows() -> Iterator[tuple[_NodeLike, _RelationshipLike | None, list[str] | None]]:
        for labels in _distinct_label_combinations(driver, database):
            yield from _read_label_combination(driver, database, labels, sampling_rate)

    return extract_archetype_counts(_rows())


def _distinct_label_combinations(driver: Driver, database: str | None) -> list[list[str]]:
    """Porte de ``generateLabelsMinMaxCountQuery``/``executeSimpleQuery``.

    Chamada em ``SparkProcess.java:60``; definições em ``:102-105``
    (a *query*) e ``:116-121`` (execução — ``.collect()``, sem *map*/*reduce*).
    """
    result = driver.execute_query(
        "MATCH (n) RETURN DISTINCT labels(n)",
        database_=database,
        routing_=RoutingControl.READ,
    )
    return [list(record[0]) for record in result.records]


def _read_label_combination(
    driver: Driver, database: str | None, labels: list[str], sampling_rate: float
) -> list[tuple[_NodeLike, _RelationshipLike | None, list[str] | None]]:
    r"""Porte de ``generateLabels``/``generateQuery``/``executeQuery``.

    ``SparkProcess.java:83-90``/``:107-114``/``:92-100``.

    O padrão de labels (``:\`Label1\`:\`Label2\```) monta igual ao
    ``generateLabels`` — mesmos acentos graves, mesma ordem (a que veio da
    primeira *query*, não reordenada aqui).
    """
    label_pattern = "".join(f":`{label}`" for label in labels)
    query = (
        f"MATCH (n{label_pattern}) WHERE size(labels(n)) = $n_labels "
        "WITH n OPTIONAL MATCH (n)-[r]->(m) "
        + (f"WHERE rand() < {sampling_rate} " if sampling_rate != 1.0 else "")
        + "RETURN n, r, labels(m)"
    )
    result = driver.execute_query(
        query,
        n_labels=len(labels),
        database_=database,
        routing_=RoutingControl.READ,
    )
    return [
        (record[0], record[1], list(record[2]) if record[2] is not None else None)
        for record in result.records
    ]
