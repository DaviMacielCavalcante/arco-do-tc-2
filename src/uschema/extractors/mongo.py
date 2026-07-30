"""Extrator MongoDB — porte de ``Helpers.java`` (simplify/generateDocumentPair/reducePairs).

Porte fiel de ``mongodb2uschema/utils/Helpers.java`` (**não** o pacote `.spark`,
que é um caminho paralelo não usado pelo oráculo — ver o achado no topo de
``todolist_fase2.md``). O pipeline original (``MongoDB2USchema.java:73-83``):

.. code-block:: java

    JavaMongoRDD<Document> rddCollection = MongoSpark.load(jsc);
    rddCollection
        .mapToPair(doc -> Helpers.generateDocumentPair(doc))
        .reduceByKey((t1, t2) -> Helpers.reducePairs(t1, t2))
        .collect().stream()
        .map(pair -> { pair._1.put(typeField, collectionName); return ...; })

Este módulo porta o `map`/`reduce` inteiro (``simplify``, ``generate_document_pair``,
``reduce_pairs``, e o agrupamento por assinatura em ``build_triples``) como
funções puras, sem I/O — recebem os documentos já materializados (uma lista,
ou o cursor do ``pymongo``), não abrem conexão.

A conexão em si — porte de ``MongoDB2USchema.process``/``processEntity``
(``:48-58``/``:60-86``) e de ``MongoDB2USchemaMain.run`` (``:45-59``) — é
``extract_database_triples``/``extract_triples``, no fim do módulo: driver
nativo (``pymongo``), não o conector Spark; ver a seção seguinte.

Por que driver nativo, não conector Spark
------------------------------------------
Investigado em ``fase2_decisao_leitura_mongo_neo4j.md``: o oráculo lê via API
RDD do conector antigo (``MongoSpark.load``), que devolve ``org.bson.Document``
cru — nunca passa por DataFrame nem por inferência de schema. Nenhum conector
Spark vivo hoje (Mongo v11.x, Neo4j v6.0.0) ainda expõe essa API; os dois
viraram DataFrame-only. Ler direto via ``pymongo`` é a reconstrução mais fiel
do mecanismo do oráculo disponível — não um desvio dele.

Como os tipos viajam (a decisão central deste módulo)
-------------------------------------------------------
``Helpers.simplify`` apaga cada valor de folha, trocando por uma sentinela do
seu tipo (``Constants.java:18-23``). O oráculo produz o esqueleto final via
``Document.toJson()``, que serializa ``ObjectId`` como **objeto** extended-JSON
(``{"$oid": "..."}``) — e, como este projeto descobriu ao investigar o driver
Java (``JsonWriterSettings``, modo ``STRICT``, ``fase2_decisao_leitura_mongo_neo4j.md``),
serializa ``int64`` do mesmo jeito (``{"$numberLong": "..."}``). Os dois viram
**entidades agregadas** na inferência (Fase 1), não atributos primitivos.

Este módulo produz esses objetos **diretamente no ``dict`` nativo** — não via
``bson.json_util.dumps()`` + ``json.loads()``, que reintroduziria uma camada de
texto JSON que a Fase 1.5 já eliminou de propósito (o ``abstractjson`` do Java
não tem equivalente no porte; ver ``extractors/triple.py``).

Como o agrupamento por assinatura funciona (build_triples)
-------------------------------------------------------------
O `reduceByKey` do Java (``MongoDB2USchema.java:76-77``) agrupa pela **chave**
``pair._1`` — o ``Document`` simplificado. ``org.bson.Document`` estende
``LinkedHashMap``, cujo ``equals``/``hashCode`` (herdados de ``AbstractMap``)
são **estruturais e independentes de ordem de chave**: dois documentos com os
mesmos pares chave/valor, em ordem diferente, são a mesma chave de grupo. Uma
``ArrayList`` aninhada, ao contrário, compara **por ordem** — ``[1, 2]`` e
``[2, 1]`` não são o mesmo array.

``build_triples`` reproduz isso agrupando por uma chave canônica —
``json.dumps(schema, sort_keys=True)`` — que ordena chaves de objeto (como o
``equals`` de mapa faz) mas preserva a ordem de listas (como o ``equals`` de
``ArrayList`` faz). O `_type` (``MongoDB2USchema.java:82``, atributo
`typeField`) é anexado **depois** do agrupamento, igual ao Java — incluí-lo
antes não mudaria o resultado neste caso (é a mesma string pra toda coleção),
mas a ordem importa como documentação do comportamento original.

A armadilha de tradução (Int64/bool são subclasses de int em Python)
-----------------------------------------------------------------------
No Java, ``Boolean``/``Integer``/``Long`` são classes disjuntas — a ordem dos
``instanceof`` em ``Helpers.java`` não importa. Em Python isso não vale:
``bson.Int64`` é subclasse de ``int`` (existe justamente pra forçar codificação
BSON ``int64`` em vez de ``int32``), e ``bool`` também é subclasse de ``int``
(fato da linguagem). Um despacho que testasse ``isinstance(v, int)`` antes de
``Int64``/``bool`` devolveria ``0`` silenciosamente onde o oráculo produz
``{"$numberLong": "0"}``, e ``0`` onde produz ``false`` — sem nenhum erro.
``_simplify_value`` testa **``Int64`` → ``bool`` → ``int`` genérico**, nessa
ordem, por isso.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.int64 import Int64
from pymongo import MongoClient
from pymongo.database import Database

__all__ = [
    "SIMPLE_DEFAULT_LONG",
    "SIMPLE_DEFAULT_OBJECTID",
    "TYPE_FIELD",
    "build_triples",
    "extract_database_triples",
    "extract_triples",
    "generate_document_pair",
    "reduce_pairs",
    "simplify",
]

#: Nome do atributo de tipo injetado em cada esqueleto agregado
#: (``typeField``/``config.getTypeMarkerAttribute()``, ``MongoDB2USchema.java:82``).
#: Mesma convenção usada em toda a Fase 1 — ver ``extractors/triple.py``.
TYPE_FIELD = "_type"

#: Sentinela de string/data (``Constants.java:18``, ``SIMPLE_DEFAULT_STRING``).
_SIMPLE_DEFAULT_STRING = ""
#: Sentinela de booleano (``Constants.java:19``, ``SIMPLE_DEFAULT_BOOLEAN``).
_SIMPLE_DEFAULT_BOOLEAN = False
#: Sentinela de inteiro 32-bit (``Constants.java:20``, ``SIMPLE_DEFAULT_INTEGER``).
_SIMPLE_DEFAULT_INTEGER = 0
#: Sentinela de ponto flutuante (``Constants.java:21``, ``SIMPLE_DEFAULT_DOUBLE``).
_SIMPLE_DEFAULT_DOUBLE = 0.0

#: Sentinela de ``ObjectId`` (``Constants.java:23``, ``SIMPLE_DEFAULT_OBJECTID``)
#: já na forma que ``Document.toJson()`` produz — um objeto extended-JSON, não
#: uma string. Vira entidade agregada na inferência (Fase 1), com um atributo
#: ``$oid`` do tipo string. Ver ``extractors/triple.py`` para a análise completa
#: de por que ``ObjectIdSC`` é código morto no caminho Spark.
SIMPLE_DEFAULT_OBJECTID: dict[str, str] = {"$oid": "000000000000000000000000"}

#: Equivalente pra ``int64``/``bson.Int64`` — **não existe** em
#: ``Constants.java`` porque o Java nunca precisou dessa sentinela como objeto
#: (``Long`` tem sua própria sentinela escalar, ``0L``, linha 22). A
#: necessidade de tratar ``int64`` como objeto agregado é um achado deste
#: porte (``fase2_decisao_leitura_mongo_neo4j.md``): o mesmo ``Document.toJson()``
#: que serializa ``ObjectId`` como ``{"$oid": ...}`` serializa ``long`` como
#: ``{"$numberLong": ...}`` em modo ``STRICT`` — o modo que o driver do
#: conector 2.4.1 usa por padrão. Sem fixture de golden-master ainda (nenhum
#: XMI de referência tem campo ``long``); cobrir com teste dedicado.
SIMPLE_DEFAULT_LONG: dict[str, str] = {"$numberLong": "0"}


def simplify(document: Mapping[str, Any]) -> dict[str, Any]:
    """Apagar os valores de um documento, preservando só o esqueleto de tipos.

    Porte de ``Helpers.simplify(Document)`` (``Helpers.java:18-27``). Percorre
    as chaves do documento e substitui cada valor pela sentinela do seu tipo
    via :func:`_simplify_value` — recursivo em objetos aninhados e listas.

    Parameters
    ----------
    document : Mapping of str to Any
        Documento cru, como devolvido por ``pymongo`` (``dict`` por padrão).

    Returns
    -------
    dict of str to Any
        O mesmo documento com cada folha trocada pela sentinela do seu tipo.

    Raises
    ------
    TypeError
        Se algum valor não for de um tipo suportado — porte de
        ``UnsupportedOperationException`` (``Helpers.java:53-54``). O oráculo
        lança para binário, ``Decimal128`` e qualquer tipo BSON fora de
        ``String``/``Date``/``Boolean``/``Integer``/``Double``/``Long``/
        ``ObjectId``/``Document``/``ArrayList``; este porte replica o mesmo
        comportamento observável, só com o tipo de exceção idiomático do
        Python (mesma escolha que ``extractors.triple.classify`` já faz para
        um caso análogo).
    """
    return {key: _simplify_value(value) for key, value in document.items()}


def _simplify_value(value: Any) -> Any:
    """Traduzir um valor de folha (ou nó) para a sentinela do seu tipo.

    Porte de ``Helpers.simplify(Object)`` (``Helpers.java:29-57``). A ordem de
    despacho **diverge** da ordem textual do Java — ver a seção "A armadilha
    de tradução" no docstring do módulo: ``Int64`` e ``bool`` têm de ser
    testados antes de qualquer ``isinstance(v, int)`` genérico, porque os dois
    são subclasses de ``int`` em Python (não são no Java, onde ``Boolean``,
    ``Integer`` e ``Long`` são classes disjuntas).

    Parameters
    ----------
    value : Any
        Um valor de folha do documento, ou um nó (``dict``/``list``) a
        percorrer recursivamente.

    Returns
    -------
    Any
        A sentinela correspondente, ou a estrutura recursivamente simplificada
        para ``dict``/``list``, ou ``None`` se o valor já era ``None`` (o Java
        também deixa ``null`` passar — nenhum ramo do ``if``/``else if`` o
        alcança, e o ``throw`` final é guardado por ``input != null``).

    Raises
    ------
    TypeError
        Ver :func:`simplify`.
    """
    # `Int64` antes de `bool` antes de `int`: os dois primeiros são subclasses
    # de `int` em Python. Trocar a ordem faz `long`/`bool` virarem `0` em
    # silêncio — sem erro, sem teste falhando, só um dado errado.
    if isinstance(value, Int64):
        return dict(SIMPLE_DEFAULT_LONG)
    if isinstance(value, bool):
        return _SIMPLE_DEFAULT_BOOLEAN
    if isinstance(value, str | datetime):
        return _SIMPLE_DEFAULT_STRING
    if isinstance(value, int):
        return _SIMPLE_DEFAULT_INTEGER
    if isinstance(value, float):
        return _SIMPLE_DEFAULT_DOUBLE
    if isinstance(value, ObjectId):
        return dict(SIMPLE_DEFAULT_OBJECTID)
    if isinstance(value, Mapping):
        return simplify(value)
    if isinstance(value, list):
        # Recursivo **sem colapsar** (`Helpers.java:46-52`) — o Spark mantém
        # todos os elementos do array; colapsar pra um só é comportamento do
        # extrator map-reduce (`map.js`), não deste.
        return [_simplify_value(element) for element in value]
    if value is None:
        return None

    raise TypeError(f"Document field type not supported: {type(value).__name__}")


def generate_document_pair(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[int, int, int]]:
    """Produzir o par (esqueleto simplificado, metadados) de um documento.

    Porte de ``Helpers.generateDocumentPair`` (``Helpers.java:64-70``), **com
    o bug #6 corrigido por construção** (``bugs_originais.md`` #6,
    ``Helpers.java:66``): o Java faz ``doc.getObjectId("_id").getTimestamp()``,
    que lança ``ClassCastException`` quando ``_id`` não é um ``ObjectId`` —
    derrubando a extração inteira em qualquer coleção de origem relacional
    (é o caso do Northwind, cujo ``_id`` é inteiro). Aqui o timestamp só é
    extraído quando ``_id`` é de fato um ``ObjectId``; caso contrário, ``0``
    — sentinela válida, não valor (mesmo tratamento que
    ``extractors.triple.SchemaTriple.first_timestamp``/``last_timestamp``).

    Parameters
    ----------
    document : Mapping of str to Any
        Documento cru, como devolvido por ``pymongo``.

    Returns
    -------
    tuple of (dict of str to Any, tuple of (int, int, int))
        ``(simplify(document), (timestamp, timestamp, 1))`` — o par que o
        ``reduceByKey`` do Java (``Tuple2<Document, Tuple3<Long, Long, Integer>>``)
        agruparia por esqueleto. O primeiro elemento da tupla de metadados é
        ``firstTimestamp``, o segundo ``lastTimestamp``, o terceiro ``count``.
    """
    document_id = document.get("_id")
    if isinstance(document_id, ObjectId):
        timestamp = int(document_id.generation_time.timestamp())
    else:
        timestamp = 0

    return simplify(document), (timestamp, timestamp, 1)


def reduce_pairs(first: tuple[int, int, int], second: tuple[int, int, int]) -> tuple[int, int, int]:
    """Combinar dois metadados (firstTimestamp, lastTimestamp, count) de mesmo esqueleto.

    Porte fiel de ``Helpers.reducePairs`` (``Helpers.java:79-85``).

    Parameters
    ----------
    first, second : tuple of (int, int, int)
        Metadados no formato ``(firstTimestamp, lastTimestamp, count)`` —
        ver :func:`generate_document_pair`.

    Returns
    -------
    tuple of (int, int, int)
        ``(min(firstTimestamp), max(lastTimestamp), soma dos counts)``.
    """
    first_ts_a, last_ts_a, count_a = first
    first_ts_b, last_ts_b, count_b = second

    return (min(first_ts_a, first_ts_b), max(last_ts_a, last_ts_b), count_a + count_b)


def _canonical_schema_key(schema: Mapping[str, Any]) -> str:
    """Chave de agrupamento estrutural, order-independent pra objeto, order-dependent pra lista.

    Ver "Como o agrupamento por assinatura funciona" no docstring do módulo —
    reproduz o ``equals``/``hashCode`` de ``org.bson.Document`` (mapa,
    independente de ordem) sem reproduzir o de ``ArrayList`` (dependente de
    ordem), porque ``json.dumps(sort_keys=True)`` só reordena chaves de
    ``dict``, nunca elementos de ``list``.

    Parameters
    ----------
    schema : Mapping of str to Any
        Um esqueleto já simplificado (saída de :func:`simplify`) — só contém
        os tipos que ``json.dumps`` serializa nativamente.

    Returns
    -------
    str
        Representação canônica, estável para o mesmo esqueleto estrutural.
    """
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def build_triples(
    documents: Iterable[Mapping[str, Any]], collection_name: str
) -> list[dict[str, Any]]:
    """Agrupar documentos pelo esqueleto e montar as triplas de uma coleção.

    Porte do restante de ``processEntity`` (``MongoDB2USchema.java:73-83``):
    o `map`/`reduceByKey` (via :func:`generate_document_pair`/
    :func:`reduce_pairs`), seguido da anexação do `_type` **depois** da
    agregação (``:82``, ``pair._1.put(typeField, collectionName)``) — mesma
    ordem aqui. A materialização de ``documentPairToJSONNode`` (``:101-115``)
    é só empacotar em ``dict`` no formato camelCase que
    ``extractors.triple.triples_from_rows`` espera; sem a etapa de
    string/``ObjectMapper`` do Java, porque o porte nunca serializa pra texto
    entre a extração e a inferência (ver "Como os tipos viajam" no docstring
    do módulo).

    Parameters
    ----------
    documents : iterable of Mapping of str to Any
        Documentos crus de uma coleção — tipicamente o cursor de
        ``pymongo_collection.find()``, mas qualquer iterável serve (é assim
        que os testes exercitam esta função sem banco).
    collection_name : str
        Nome cru da coleção — vira o valor de ``_type``, **sem capitalizar**
        (quem capitaliza é ``infer``, Fase 1.2).

    Returns
    -------
    list of dict of str to Any
        Uma linha por esqueleto distinto, no formato
        ``{"schema", "count", "firstTimestamp", "lastTimestamp"}`` — pronta
        para ``extractors.triple.triples_from_rows``.
    """
    grouped: dict[str, tuple[dict[str, Any], tuple[int, int, int]]] = {}

    for document in documents:
        schema, meta = generate_document_pair(document)
        key = _canonical_schema_key(schema)
        if key in grouped:
            existing_schema, existing_meta = grouped[key]
            grouped[key] = (existing_schema, reduce_pairs(existing_meta, meta))
        else:
            grouped[key] = (schema, meta)

    rows: list[dict[str, Any]] = []
    for schema, (first_timestamp, last_timestamp, count) in grouped.values():
        schema[TYPE_FIELD] = collection_name
        rows.append(
            {
                "schema": schema,
                "count": count,
                "firstTimestamp": first_timestamp,
                "lastTimestamp": last_timestamp,
            }
        )

    return rows


def extract_database_triples(
    database: Database[Mapping[str, Any]], collections: Iterable[str]
) -> list[dict[str, Any]]:
    """Ler cada coleção via ``pymongo`` e montar as triplas de todas juntas.

    Porte de ``MongoDB2USchema.process``/``processEntity``
    (``Helpers.java`` não; ``MongoDB2USchema.java:48-58`` e ``:60-86``), com
    duas simplificações deliberadas que não mudam o resultado:

    - o Java abre um ``JavaSparkContext`` **novo por coleção** (``:63-71``,
      ``jsc.close()`` em ``:84``) só porque cada ``MongoSpark.load(jsc)``
      precisa da coleção-alvo na ``SparkConf``; aqui uma única conexão
      ``pymongo`` já resolvida (o parâmetro ``database``) serve pra todas —
      reabrir por coleção não teria efeito observável;
    - o Java empacota tudo num ``ArrayNode`` do Jackson antes de entregar pra
      inferência; aqui é só uma ``list[dict]`` — mesmo formato de linha que
      :func:`build_triples` já produz, sem a camada de texto/``ObjectMapper``
      (ver "Como os tipos viajam" no docstring do módulo).

    Parameters
    ----------
    database : pymongo.database.Database
        Banco já resolvido a partir de um ``MongoClient`` conectado
        (``client[database_name]``) — quem abre/fecha o cliente é o
        chamador (ou :func:`extract_triples`, que faz as duas coisas).
    collections : iterable of str
        Nomes crus das coleções a ler, na ordem em que
        ``MongoDB2USchemaMain`` as concatena (``:57``, propriedade
        ``mongodb.collections`` separada por vírgula).

    Returns
    -------
    list of dict of str to Any
        As linhas de **todas** as coleções concatenadas, uma por esqueleto
        distinto por coleção — pronto para
        ``extractors.triple.triples_from_rows``.
    """
    rows: list[dict[str, Any]] = []
    for collection_name in collections:
        cursor = database[collection_name].find()
        rows.extend(build_triples(cursor, collection_name))

    return rows


def extract_triples(
    database_uri: str, database_name: str, collections: Iterable[str]
) -> list[dict[str, Any]]:
    """Conectar via ``pymongo`` e montar as triplas — ponta a ponta.

    Porte de ``MongoDB2USchemaMain.run`` (``:45-59``) + ``MongoDB2USchema.process``
    (``:48-58``), sem a etapa final de gravar o XMI (``:57`` — isso é
    responsabilidade de ``inference.build_uschema.BuildUSchema``, não do
    extrator). Driver nativo, não o conector Spark — ver "Por que driver
    nativo, não conector Spark" no docstring do módulo e
    ``fase2_decisao_leitura_mongo_neo4j.md``.

    Abre e fecha o ``MongoClient`` só para esta chamada (``with``); para ler
    várias vezes com a mesma conexão, use :func:`extract_database_triples`
    diretamente com um cliente já aberto.

    Parameters
    ----------
    database_uri : str
        URI de conexão (``Constants.CONFIG_MONGODB_CONNECTION_KEY``,
        ``mongodb.connection`` no ``config.properties`` original).
    database_name : str
        Nome do banco (``mongodb.database``).
    collections : iterable of str
        Nomes das coleções a ler (``mongodb.collections``, separadas por
        vírgula no original).

    Returns
    -------
    list of dict of str to Any
        Ver :func:`extract_database_triples`.
    """
    with MongoClient[Mapping[str, Any]](database_uri) as client:
        return extract_database_triples(client[database_name], collections)
