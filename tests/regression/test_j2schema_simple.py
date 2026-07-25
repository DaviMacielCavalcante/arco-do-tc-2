"""Porte do ``J2SchemaSimpleTests.java`` (regressão JUnit, bloco A do INVENTARIO).

Fixa o caminho ``JSON → árvore raw → string``, exercitando dois utilitários que
a 1.1 deixou de fora de propósito (código morto no pipeline, portados junto deste
teste, o único consumidor):

- :func:`~uschema.intermediate.raw_schema_gen.de_schema` — o ``RawSchemaGen``,
  construtor de árvore raw **separado** do ``infer`` (não seta ``entity_name``/
  ``meta``, não deduplica array);
- :func:`~uschema.intermediate.schema_printer.schema_string` — o ``SchemaPrinter``.

As três entradas são o JSON literal do JUnit (``test1``/``test2``/``test3``), e a
saída afirmada é a **mesma string**, espaços inclusos.

Sobre o ``<null>``
------------------
O ``entity_name`` fica ``None`` (o ``RawSchemaGen`` não o seta) e o Java imprime
``null`` (concatenação ``String + null``). O porte reproduz o literal do oráculo
traduzindo ``None`` → ``"null"`` (ver :mod:`~uschema.intermediate.schema_printer`),
então a asserção afirma ``<null>``, não ``<None>`` — casar a saída do original,
não "consertar".
"""

from __future__ import annotations

import json

import pytest

from uschema.intermediate.raw_schema_gen import de_schema
from uschema.intermediate.schema_printer import schema_string

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("json_input", "expected"),
    [
        # `J2SchemaSimpleTests.java:test1` — objeto de um campo Number.
        ('{"a": 1}', '<null>{"a": Number } '),
        # `test2` — campo cujo valor é array de Number (colapsa homogêneo).
        ('{"a": [1,2,3]}', '<null>{"a": [Number ] } '),
        # `test3` — campos fora de ordem na entrada, ordenados na saída (TreeSet).
        ('{"c": 1,"b": 1,"a": 1}', '<null>{"a": Number "b": Number "c": Number } '),
    ],
)
def test_schema_string(json_input: str, expected: str) -> None:
    sc = de_schema(None, json.loads(json_input))
    assert sc is not None
    assert schema_string(sc) == expected
