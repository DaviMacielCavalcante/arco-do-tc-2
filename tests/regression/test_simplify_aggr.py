"""Porte do ``SimplifyAggrTest.java`` (regressão JUnit, bloco B do INVENTARIO).

Fixa a **simplificação de agregado**: ``Aggr{V1, V2, V2, …}`` colapsa em
``Aggr{V1, V2}``. Quem faz isso é o ``LinkedHashSet`` em
``SchemaInference.infer(IAJArray)`` (``:237-242``, deduplicação dos inners de um
array) — **não** o ``EVariationMerger``, como ``fase1_nucleo_inferencia.md`` §1.6
e o ``INVENTARIO.md`` diziam (os dois erram; corrigido). Módulo **1.2**.

Fixture (bloco B — cortada na tripla)
------------------------------------
Congelada em ``tests/fixtures/simplify_aggr.json``, gerada pelo map-reduce ``v1``
sobre ``testSources/SimplifyAggr.json`` (ver ``tests/fixtures/README.md``). São
4 ocorrências de ``persons`` com ``other_names`` de tamanhos 1/2/4/6 — arrays de
tamanho variável, mas com só **duas** formas distintas de elemento
(``{name, note}`` e ``{lang, name, note}``). O array de tamanho variável é também
dado do #8.

Asserção por entidade, não por índice
------------------------------------
Como no ``CountTimestampTest``: o JUnit indexa ``get(0)``/``get(1)``, mas a ordem
das entidades não é significativa. Afirmo 2 entidades, cada uma com 2 variações,
por nome.
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

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "simplify_aggr.json"


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
        "DEBUG_SimplifyAggr", SchemaInference().infer(triples)
    )


def test_duas_entidades_com_duas_variacoes_cada() -> None:
    # `SimplifyAggrTest.java` — assertEquals(2, entities); cada uma 2 variações.
    schema = _build()

    assert len(schema.entities) == 2
    for entity in schema.entities:
        assert len(entity.variations) == 2


def test_agregado_colapsa_para_as_formas_distintas() -> None:
    # O `other_names` de tamanho 1/2/4/6 tem só 2 formas de elemento; a entidade
    # interna Other_name fica com exatamente essas 2 variações (colapso), não uma
    # por tamanho de array.
    schema = _build()

    by_name = {e.name: e for e in schema.entities}
    assert "Persons" in by_name
    assert "Other_name" in by_name
    assert len(by_name["Other_name"].variations) == 2
