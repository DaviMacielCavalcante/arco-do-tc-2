r"""``SchemaPrinter.schemaString`` — árvore raw → string de debug (Fase 1.6, dead code).

Porte de ``doc2uschema/intermediate/raw/util/SchemaPrinter.java`` (commit pinado
``0f8f58c``). Serializa uma :class:`~uschema.intermediate.raw.SchemaComponent` numa
string legível para depuração.

É **código morto no pipeline** — só roda sob ``DEBUG_TYPE.DEBUG`` (constante em
``NO_DEBUG``, ``SchemaInference:61,142``). O único consumidor de verdade é o
``J2SchemaSimpleTests``, que afirma sobre a saída de :func:`schema_string`.
Portado por "fiel e completo", junto do teste que o exercita.

Formato (verificado contra as asserções do JUnit)
-------------------------------------------------
- **folha**: ``Bool`` / ``Number`` / ``Null`` / ``Oid`` / ``String``;
- **objeto**: ``(root)`` se raiz, ``(count: …)(firstTs: …)(lastTs: …)`` se há
  ``meta``, depois ``<entity_name>{`` + cada campo ``"nome": <valor>`` + ``}``;
- **array**: ``[`` + cada inner + ``]``.

**Todo** componente contribui um espaço ``' '`` ao fim (o ``sb.append(' ')`` do
dispatcher, ``:63``) — é o que produz os espaços de ``"<null>{\"a\": Number } "``.
Os espaços são load-bearing na asserção; não "limpar".

.. note::
   **Decisão registrada — ``<null>`` e não ``<None>``.** O
   ``RawSchemaGen`` não seta ``entity_name`` (fica ``None``), e o Java imprime
   ``"<" + sc.entityName + ">"`` renderizando o ``null`` como a string ``"null"``
   (concatenação ``String + null``, comportamento da linguagem). Para reproduzir
   a saída do oráculo — a string que o ``J2SchemaSimpleTests`` afirma — este
   porte traduz ``None`` → ``"null"`` (:func:`_null_str`). Não é "consertar": é
   casar o literal do teste. Fosse ``f"<{None}>"`` sairia ``<None>``, divergindo.
"""

from __future__ import annotations

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

__all__ = ["schema_string"]


def _null_str(value: object) -> str:
    """Renderizar ``None`` como ``"null"`` (o ``String + null`` do Java, ``:80``)."""
    return "null" if value is None else str(value)


def schema_string(sc: SchemaComponent) -> str:
    """Serializar ``sc`` na string de debug do ``SchemaPrinter``.

    Porte de ``schemaString(SchemaComponent)`` (``:32-36``).

    Parameters
    ----------
    sc : SchemaComponent
        A raiz da árvore raw a imprimir.

    Returns
    -------
    str
        A representação-string, com os espaços que o original produz.
    """
    parts: list[str] = []
    _schema_string(sc, parts)
    return "".join(parts)


def _schema_string(sc: SchemaComponent | None, parts: list[str]) -> None:
    """Dispatcher: escreve o componente em ``parts`` e acrescenta o espaço final.

    Porte de ``schemaString(SchemaComponent, StringBuilder)`` (``:38-63``). Os
    ``if`` são sequenciais (não ``elif``), mas os tipos são mutuamente
    exclusivos; um ``None`` (folha não-tratada pelo ``RawSchemaGen``) passa por
    todos sem casar — só o espaço sai, como o ``null instanceof`` do Java.
    """
    if isinstance(sc, ObjectSC):
        _object_string(sc, parts)
    if isinstance(sc, ArraySC):
        _array_string(sc, parts)
    if isinstance(sc, BooleanSC):
        parts.append("Bool")
    if isinstance(sc, NumberSC):
        parts.append("Number")
    if isinstance(sc, NullSC):
        parts.append("Null")
    if isinstance(sc, ObjectIdSC):
        parts.append("Oid")
    if isinstance(sc, StringSC):
        parts.append("String")

    parts.append(" ")


def _object_string(sc: ObjectSC, parts: list[str]) -> None:
    """Objeto → ``(root)?(meta)?<entity_name>{campos}`` (``:71-88``)."""
    if sc.is_root:
        parts.append("(root)")
    if sc.meta is not None:
        parts.append(f"(count: {sc.meta.count})")
        parts.append(f"(firstTs: {sc.meta.first_timestamp})")
        parts.append(f"(lastTs: {sc.meta.last_timestamp})")
    parts.append(f"<{_null_str(sc.entity_name)}>{{")
    for name, value in sc.inners:
        parts.append(f'"{name}": ')  # `_outname`, `:66-69`.
        _schema_string(value, parts)
    parts.append("}")


def _array_string(sc: ArraySC, parts: list[str]) -> None:
    """Array → ``[inners]`` (``:90-95``)."""
    parts.append("[")
    for inner in sc.inners:
        _schema_string(inner, parts)
    parts.append("]")
