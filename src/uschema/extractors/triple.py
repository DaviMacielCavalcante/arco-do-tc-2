"""Contrato da tripla — a costura entre a extração (Fase 2) e a inferência (Fase 1).

A tripla é a única superfície que as duas frentes compartilham: o extrator
produz, o ``SchemaInference`` consome.

O que viaja na tripla **não é o documento** — é um esqueleto de tipos
---------------------------------------------------------------------
O extrator apaga os valores antes de emitir, trocando cada um por uma sentinela
do seu tipo. Os dois extratores do Java fazem isso de formas diferentes:

- **Spark** (``Helpers.simplify``, ``mongodb2uschema/utils/Helpers.java:29-56``,
  sentinelas em ``Constants.java:18-23``): ``str``/``Date`` → ``""``, ``bool`` →
  ``false``, ``int`` → ``0``, ``float`` → ``0.0``, ``ObjectId`` →
  ``ObjectId("000000000000000000000000")``. É o caminho que o **oráculo** roda
  (``MongoDB2USchema.java:73-80``).
- **map-reduce** (``resources/mapreduce/mongodb/v2/map.js``, e a ``v1`` que os
  JUnit usam): ``string`` → ``"s"`` (``"string"`` na ``v1``), ``number`` → ``0``,
  ``boolean`` → ``true``, ``ObjectId`` → ``"oid"``. Também **colapsa array
  homogêneo** para um só elemento, o que o Spark não faz.

Logo: o valor concreto de uma folha é irrelevante — só o **tipo** importa. A
exceção é o ``ObjectId``.

Como o ``ObjectId`` viaja
-------------------------
Não viaja como ``bson.ObjectId`` nem como *wrapper*. O Java despacha
``ObjectIdSC`` por ``n.isObjectId()`` (``SchemaInference.java:168``), e as duas
implementações do Bridge definem isso como **"o valor é a string literal
``oid``"** (``JacksonElement.java:93``, ``GsonElement.java:120`` — ambas
``isTextual() && asText().equals("oid")``; e ``isTextual()`` exclui esse caso,
``JacksonElement.java:87``). É a sentinela do ``map.js``, e só ela.

Daí um resultado que **contradiz a expectativa do plano**: no caminho do oráculo
(Spark) o ``ObjectId`` nunca chega como string. ``Document.toJson()`` serializa
a sentinela em *extended JSON* — ``{"$oid": "0000…"}`` — que é um **objeto**,
então ``isObject()`` casa primeiro e o ``_id`` vira **entidade agregada** com um
atributo ``$oid`` do tipo ``String``. Está no XMI de referência
(``resources/mongodb/model_mintest.xmi:69-72``; idem em ``model_northwind.xmi``).

Ou seja: **``ObjectIdSC`` é código morto no caminho Spark** — só o map-reduce o
alcança. O ``ObjectIdTest``, que afirma ``PrimitiveType`` de nome ``ObjectId``,
roda sobre ``mapreduce/mongodb/v1/`` (``ObjectIdTest.java:56``): a fixture dele
(1.6) tem de ser gerada nessa forma, ou o teste afirma um valor que o oráculo
nunca produz.

Manter a divergência é o ponto. "Consertar" o caminho Spark para reconhecer
``$oid`` produziria um modelo que o oráculo não gera, e o harness da 0.3
acusaria em cada ``_id``.

Notas
-----
O bug **#6** (``Helpers.java:66``) está a montante disto, no extrator: é o
``getTimestamp()`` do ``_id`` que alimenta os timestamps e que estoura quando o
``_id`` não é ``ObjectId``. Aqui eles já chegaram como ``int``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "OBJECT_ID_SENTINEL",
    "JsonKind",
    "SchemaTriple",
    "classify",
    "triples_from_rows",
    "validate_rows",
]

#: Sentinela que o extrator map-reduce emite no lugar de um ``ObjectId``
#: (``map.js``, ramo ``obj instanceof ObjectId``). É o **único** valor de folha
#: com significado próprio na tripla — ver o cabeçalho do módulo.
OBJECT_ID_SENTINEL = "oid"

#: Mensagem do ``IllegalArgumentException`` de ``SchemaInference.java:128``,
#: transcrita literalmente. Ela já estava desatualizada no original (fala de um
#: ``timestamp`` único, quando a tripla tem ``firstTimestamp``/``lastTimestamp``);
#: mantida assim por fidelidade.
_INVALID_ROWS_MESSAGE = (
    "JSON rows do not follow the expected schema: "
    "[ {schema: <JSON Object>, count: <Integer>, timestamp: <Long>} ...]"
)


class JsonKind(Enum):
    """Tipo de um valor da tripla, no vocabulário do ``IAJIdentify`` do Java.

    Um caso por ramo do despacho de ``SchemaInference.infer(IAJElement, …)``
    (``SchemaInference.java:150-171``), e cada um nomeia o ``SchemaComponent``
    que a Fase 1.2 vai construir.
    """

    OBJECT = "object"
    ARRAY = "array"
    BOOLEAN = "boolean"
    NUMBER = "number"
    NULL = "null"
    TEXTUAL = "textual"
    OBJECT_ID = "objectId"


def classify(value: Any) -> JsonKind:
    """Classificar um valor da tripla no tipo que o Java despacharia.

    Parameters
    ----------
    value : Any
        Valor de folha ou nó do ``schema`` da tripla.

    Returns
    -------
    JsonKind
        O tipo correspondente.

    Raises
    ------
    TypeError
        Se o valor não for representável em JSON. **Desvio deliberado**: o Java
        tem ``assert(false); return null`` (``:171-173``), que com *assertions*
        desligadas (o padrão da JVM) devolve ``null`` e só estoura adiante, em
        outro lugar. Falhar no ponto do erro não muda nenhum caminho válido.
    """
    # A ordem dos ramos é a de `SchemaInference.java:150-171`, e BOOLEAN **tem**
    # de vir antes de NUMBER: `bool` é subclasse de `int` no Python, então
    # `isinstance(True, int)` é verdadeiro e a ordem "natural" faria todo
    # booleano virar NumberSC em silêncio. No Java os dois ramos são disjuntos.
    if isinstance(value, Mapping):
        return JsonKind.OBJECT
    if isinstance(value, list):
        return JsonKind.ARRAY
    if isinstance(value, bool):
        return JsonKind.BOOLEAN
    if isinstance(value, int | float):
        return JsonKind.NUMBER
    if value is None:
        return JsonKind.NULL
    if isinstance(value, str):
        if value == OBJECT_ID_SENTINEL:
            return JsonKind.OBJECT_ID
        else:
            return JsonKind.TEXTUAL

    raise TypeError(f"valor não representável em JSON na tripla: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class SchemaTriple:
    """Uma linha da entrada do ``SchemaInference``: esqueleto + contagem + janela.

    Corresponde a um grupo do ``reduceByKey``: todos os documentos de uma
    coleção que colapsaram no mesmo esqueleto de tipos.

    Parameters
    ----------
    schema : Mapping of str to Any
        O esqueleto de tipos (valores já apagados — ver o cabeçalho do módulo).
        Inclui o *type marker* ``_type`` com o nome da coleção, injetado pelo
        extrator em ``MongoDB2USchema.java:79``.
    count : int
        Quantos documentos colapsaram neste esqueleto.
    first_timestamp : int
        Menor timestamp do grupo; ``0`` quando o extrator não soube derivar um
        (``_id`` não-``ObjectId``, ou map-reduce ``v1``, que emite ``0`` fixo).
        O ``0`` é **sentinela**, não valor — é assim que
        ``ObjectMetadata.combineMetadata`` o trata (1.1).
    last_timestamp : int
        Maior timestamp do grupo; mesma sentinela.
    """

    schema: Mapping[str, Any]
    count: int
    first_timestamp: int
    last_timestamp: int


def validate_rows(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Validar as linhas cruas da entrada — **só a primeira**.

    Porte fiel de ``SchemaInference.validateRows``
    (``SchemaInference.java:78-90``), com o comentário do autor na ``:80``:
    *"Check just the first element, suppose the rest are correct, as this will
    be the result of some automated process"*. Lista vazia é válida (``:82-83``).

    Não "melhorar" validando todas: uma entrada com a segunda linha malformada
    tem de falhar no mesmo ponto em que o oráculo falha.

    Parameters
    ----------
    rows : sequence of mapping
        Linhas cruas, como saem do extrator (chaves em *camelCase*).

    Returns
    -------
    bool
        ``True`` se a primeira linha tem ``schema`` (objeto) e ``count``,
        ``firstTimestamp``, ``lastTimestamp`` (números), ou se a lista é vazia.
    """
    if not rows:
        return True

    # `.get`, não `[...]`: cada checagem do Java é
    # `Optional.ofNullable(triple.get(k)).filter(<predicado>).isPresent()`, e o
    # `ofNullable` absorve a chave ausente — o filtro nem roda e o resultado é
    # `false`, o mesmo de uma chave presente com tipo errado. Aqui a chave
    # ausente vira `None`, que classifica como NULL e reprova sozinha; com
    # `[...]` seria `KeyError`, uma falha que o oráculo não produz.
    first = rows[0]
    return (
        classify(first.get("schema")) is JsonKind.OBJECT
        and classify(first.get("count")) is JsonKind.NUMBER
        and classify(first.get("firstTimestamp")) is JsonKind.NUMBER
        and classify(first.get("lastTimestamp")) is JsonKind.NUMBER
    )


def triples_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[SchemaTriple]:
    """Traduzir as linhas cruas do extrator em :class:`SchemaTriple`.

    A validação é a de :func:`validate_rows` — logo, uma lista cuja **primeira**
    linha está bem-formada passa inteira, e um defeito na segunda só aparece
    aqui, na conversão. É o comportamento do original.

    Parameters
    ----------
    rows : sequence of mapping
        Linhas cruas, com as chaves ``schema``/``count``/``firstTimestamp``/
        ``lastTimestamp``.

    Returns
    -------
    list of SchemaTriple
        As triplas na ordem de entrada — a ordem é *load-bearing*: é ela que
        decide qual variação é a primeira de cada entidade (``:204-211``).

    Raises
    ------
    ValueError
        Se :func:`validate_rows` reprovar. Equivale ao
        ``IllegalArgumentException`` de ``SchemaInference.java:127-128``.
    """
    # O `schema` é referenciado, não copiado — o Java também guarda o nó
    # original, e copiar custaria caro em coleção grande sem mudar semântica.
    # Os três números passam por `int()` porque o Java os lê com `asLong()`
    # (``:135``), que coage: um `1.0` vindo do JSON vazaria como float.
    if not validate_rows(rows):
        raise ValueError(_INVALID_ROWS_MESSAGE)

    return [
        SchemaTriple(
            row["schema"], int(row["count"]), int(row["firstTimestamp"]), int(row["lastTimestamp"])
        )
        for row in rows
    ]
