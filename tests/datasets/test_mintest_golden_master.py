"""Golden-master do dataset **mintest** (Fase 1.7) — pipeline ponta a ponta.

Roda a fachada :class:`~uschema.inference.build_uschema.BuildUSchema` sobre a
tripla do mintest e compara o ``USchema`` resultante com o XMI-oráculo
``resources/mongodb/model_mintest.xmi`` pelo harness de equivalência da Fase 0.3
(:func:`~uschema.validation.equivalence.compare`).

É o **gate de integração** da Fase 1 no caso mínimo: exercita, de uma vez,
``infer`` (colapso de variações, entidade interna ``_id`` do ``{$oid}``,
propagação de count para a interna) + ``build`` (agregados, ``PList``, chaves,
opcionalidade via ``FeatureAnalyzer``) + o wiring da fachada (o do
``MongoDB2USchemaMain``, que gerou os XMIs-oráculo — sorter ``Default``; ver
:mod:`~uschema.inference.build_uschema`).

Proveniência da fixture (honestidade sobre o que isto valida)
------------------------------------------------------------
``tests/fixtures/mintest_spark.json`` é a tripla do **caminho Spark**
(``_id`` como ``{"$oid": …}``, folhas como sentinelas de tipo, ``_type`` = nome
da coleção). Ela foi **reconstruída à mão** a partir da estrutura de
``model_mintest.xmi`` seguindo as regras do ``Helpers.simplify`` (documentadas em
``extractors/triple.py``) — **não** extraída por um Spark independente, que ainda
não existe (Fase 2). Logo este teste valida ``infer``+``build``+fachada contra o
oráculo, mas **não** o extrator. Um golden-master totalmente independente (e o do
Northwind, cujo objetivo é exibir a divergência do #8) espera a Fase 2 ou um dump
de tripla do oráculo — ver ``todolist_fase1.md`` §1.7.

O teste é ``unit`` (rápido, sem banco nem Spark — a tripla está congelada), mas
é golden-master de dataset por natureza, daí morar em ``tests/datasets/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyecore.ecore import EPackage

from uschema.extractors.triple import SchemaTriple
from uschema.inference.build_uschema import BuildUSchema
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model
from uschema.validation.equivalence import compare

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mintest_spark.json"
_ORACLE_XMI = Path(__file__).resolve().parents[2] / "resources" / "mongodb" / "model_mintest.xmi"


@pytest.fixture
def pkg() -> EPackage:
    """Metamodelo U-Schema carregado."""
    return load_metamodel()


def _triples() -> list[SchemaTriple]:
    return [
        SchemaTriple(
            schema=t["schema"],
            count=t["count"],
            first_timestamp=t["firstTimestamp"],
            last_timestamp=t["lastTimestamp"],
        )
        for t in json.loads(_FIXTURE.read_text())
    ]


def test_mintest_reproduz_o_xmi_oraculo(pkg: EPackage) -> None:
    # O nome do USchema (`testdb`) é o do XMI-oráculo — o `compare_names` da 0.3
    # afirma sobre ele.
    port = BuildUSchema(pkg).build_from_rows("testdb", _triples())
    oracle = load_model(_ORACLE_XMI, pkg)

    result = compare(oracle, port)

    assert result.equivalent, [f"{d.category}: {d.message}" for d in result.divergences]
    assert result.divergences == []


def test_mintest_estrutura_esperada(pkg: EPackage) -> None:
    # Contraparte legível: as entidades e contagens de variação que o oráculo tem.
    port = BuildUSchema(pkg).build_from_rows("testdb", _triples())

    by_name = {e.name: e for e in port.entities}
    assert set(by_name) == {"Products", "Customers", "_id"}
    assert len(by_name["Products"].variations) == 2
    assert len(by_name["Customers"].variations) == 3
    # a entidade interna `_id` nasce do `{$oid}` e recebe o count de todas as
    # 5 ocorrências-raiz (propagação para a interna).
    [id_var] = list(by_name["_id"].variations)
    assert id_var.count == 5
