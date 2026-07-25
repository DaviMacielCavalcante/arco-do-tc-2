"""``RawSchemaGen.deSchema`` — árvore raw a partir de JSON (Fase 1.6, dead code).

Porte de ``doc2uschema/main/util/RawSchemaGen.java`` (commit pinado ``0f8f58c``).
Constrói uma árvore :class:`~uschema.intermediate.raw.SchemaComponent` direto de
um JSON nativo — um **construtor alternativo** ao ``SchemaInference.infer``, e
diferente dele em três pontos deliberados:

- **não atribui ``entity_name`` nem ``meta``** (ficam ``None``);
- **não lê o marcador de tipo** (``_type`` é um campo comum aqui);
- **o ramo de array não deduplica** os inners (o ``infer`` usa ``LinkedHashSet``;
  aqui é ``ArraySC.add`` puro, com a otimização homogênea da 1.1).

É **código morto no pipeline** — só o ``J2SchemaSimpleTests`` o exercita, junto
do :mod:`~uschema.intermediate.schema_printer`. Portado por "fiel e completo".

.. note::
   O ``deSchema`` do Java **não trata string** (``:34-49``: despacha
   ``isObject``/``isArray``/``isBoolean``/``isInt``/``isFloatingPointNumber``/
   ``isNull`` e devolve ``null`` no resto). Uma string cai no fallback ``None``.
   Incompletude do original — replicada, não "corrigida"; os testes não exercem
   string, e o printer tolera ``None`` (todo ``isinstance`` falha, só o espaço
   sai), como o ``null instanceof`` do Java.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from uschema.intermediate.raw import (
    ArraySC,
    BooleanSC,
    NullSC,
    NumberSC,
    ObjectSC,
    SchemaComponent,
)

__all__ = ["de_schema"]


def de_schema(name: str | None, node: Any) -> SchemaComponent | None:
    """Construir a árvore raw de ``node`` (JSON nativo).

    Porte de ``RawSchemaGen.deSchema`` (``:34-49`` + as sobrecargas privadas).

    Parameters
    ----------
    name : str or None
        Nome do campo (repassado na recursão de objeto, ``:60``), **vestigial** —
        o original nunca o usa no corpo (não seta ``entity_name``). Mantido por
        fidelidade de assinatura.
    node : Any
        Valor JSON nativo: ``dict``/``list``/``bool``/``int``/``float``/``None``,
        ou uma folha de outro tipo (que cai no fallback).

    Returns
    -------
    SchemaComponent or None
        A árvore raw, ou ``None`` no fallback (ex.: string — ver o *note* do
        módulo).
    """
    # `bool` antes de `int`: em Python `bool` é subclasse de `int`, então a ordem
    # do Java (isBoolean antes de isInt, `:40-43`) tem de ser preservada.
    if isinstance(node, Mapping):
        return _de_object(node)
    if isinstance(node, Sequence) and not isinstance(node, str | bytes):
        return _de_array(node)
    if isinstance(node, bool):
        return BooleanSC()
    if isinstance(node, int | float):
        return NumberSC()
    if node is None:
        return NullSC()
    return None


def _de_object(node: Mapping[str, Any]) -> SchemaComponent:
    """Objeto → ``ObjectSC`` com campos **ordenados** (``:55-63``).

    Campos por ordem natural de string (``TreeSet`` no Java), cada valor via
    :func:`de_schema`.
    """
    schema = ObjectSC()
    for field in sorted(node):
        child = de_schema(field, node[field])
        # Java armazena `null` aqui para folhas não-tratadas (string); nosso
        # `ObjectSC.inners` é tipado e não aceita `None`. A única fonte de `None`
        # é string, que os testes que exercem este dead code não usam — logo o
        # assert é inalcançável ali. Divergência documentada (ver *note* do módulo).
        assert child is not None
        schema.add((field, child))
    return schema


def _de_array(node: Sequence[Any]) -> SchemaComponent:
    """Array → ``ArraySC``, cada elemento via ``add`` (``:65-71``).

    Sem deduplicação de inners (ao contrário do ``infer``): é o ``ArraySC.add``
    puro, que mantém a otimização homogênea da 1.1.
    """
    schema = ArraySC()
    for element in node:
        child = de_schema(None, element)
        assert child is not None  # ver a nota em `_de_object`.
        schema.add(child)
    return schema
