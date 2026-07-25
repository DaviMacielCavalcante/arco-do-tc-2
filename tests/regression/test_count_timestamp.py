"""Porte do ``CountTimestampTest.java`` (regressão JUnit, bloco B do INVENTARIO).

Fixa a inferência de **count/timestamp por variação**, e a propagação deles das
ocorrências-raiz para as entidades **internas** — que nascem em 0 e recebem a
soma dos pais (``CountTimestampTest.java``, doc: *"In non root entity variations,
the count and timestamp is copied from the parents"*). É a área do bug **#8**.

Fixture (bloco B — cortada na tripla)
------------------------------------
O JUnit sobe um Mongo, injeta ``testSources/CountTimestamp.json`` e roda o
map-reduce ``v1``. Aqui a tripla equivalente está **congelada** em
``tests/fixtures/count_timestamp.json``, gerada por esse mesmo map-reduce v1 num
Mongo descartável (ver ``tests/fixtures/README.md`` para a proveniência e a
reprodução). Diferente de ``Types``/``ObjectId``, a asserção **é a contagem** —
por isso a fixture veio do caminho de extração real, não reconstruída à mão.

Asserção por entidade, não por índice
------------------------------------
O JUnit indexa ``getEntities().get(0/1/2)``. A ordem das entidades no nosso
pipeline não precisa casar com a do ``HashMap`` do Java (que não é significativa);
o que o teste fixa é **a contagem de cada entidade**. Afirmo por nome/forma, como
no ``OptionalTest``. Os valores (Areas 8/3, Container 1/1, Aggr interna com 2)
são os do JUnit, confirmados contra o fixture pelo próprio pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyecore.ecore import EObject

from uschema.extractors.triple import SchemaTriple
from uschema.inference.builder import USchemaModelBuilder
from uschema.inference.schema_inference import SchemaInference
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "count_timestamp.json"


def _build() -> EObject:
    """Rodar `infer` + `build` sobre a tripla congelada do map-reduce v1."""
    triples = [
        SchemaTriple(
            schema=t["schema"],
            count=t["count"],
            first_timestamp=t["firstTimestamp"],
            last_timestamp=t["lastTimestamp"],
        )
        for t in json.loads(_FIXTURE.read_text())
    ]
    return USchemaModelBuilder(load_metamodel()).build(
        "DEBUG_CountTimestamp", SchemaInference().infer(triples)
    )


def _counts_by_entity(schema: EObject) -> dict[str, list[int]]:
    """``nome da entidade -> lista de counts das variações``."""
    return {e.name: sorted(v.count for v in e.variations) for e in schema.entities}


def test_tres_entidades() -> None:
    # `CountTimestampTest.java` — assertEquals(3, entities.size()).
    schema = _build()
    assert len(schema.entities) == 3


def test_counts_por_variacao_das_entidades_raiz() -> None:
    # As entidades-raiz Areas e Container, com os counts por variação do JUnit.
    counts = _counts_by_entity(_build())
    assert counts["Areas"] == [3, 8]
    assert counts["Container"] == [1, 1]


def test_entidade_interna_recebe_count_propagado_dos_pais() -> None:
    # `aggr` (aninhado em Container) vira a entidade interna Aggr. Nasce em 0 e
    # recebe a soma das ocorrências-raiz de Container (1 + 1 = 2). É a propagação
    # de count/timestamp para entidades internas — o cerne do CountTimestampTest.
    schema = _build()
    [aggr] = [e for e in schema.entities if e.name == "Aggr"]
    assert len(aggr.variations) == 1
    assert aggr.variations[0].count == 2


def test_timestamps_zerados_em_todas_as_variacoes() -> None:
    # No cenário relacional→NoSQL os timestamps entram como 0 (a fixture os tem
    # em 0), e assim permanecem — o JUnit afirma firstTimestamp/lastTimestamp 0
    # em cada variação.
    schema = _build()
    for entity in schema.entities:
        for variation in entity.variations:
            assert variation.firstTimestamp == 0
            assert variation.lastTimestamp == 0
