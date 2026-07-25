"""Porte do ``ObjectIdTest.java`` (regressão JUnit, bloco B do INVENTARIO).

Fixa que o ``_id`` é inferido como **``ObjectId``, não ``String``** (``:56-64``):
uma entidade, cujo ``_id`` é um ``Attribute`` de ``PrimitiveType`` de nome
``"ObjectId"``.

Fixture — e por que **map-reduce v1**
------------------------------------
Este é o único caminho em que ``ObjectId`` chega como tipo próprio. O
``ObjectIdTest.java`` roda o map-reduce **``v1``** (``:56``), onde o ``ObjectId``
vira a sentinela textual ``"oid"`` — e ``classify("oid")`` a mapeia para
``ObjectIdSC`` → ``PrimitiveType "ObjectId"``. **Não** dá para gerar a fixture
pelo Spark: lá o ``ObjectId`` sai como ``{"$oid": …}`` (um objeto), o ``_id``
vira **entidade agregada**, e o teste afirmaria um tipo que esse caminho nunca
produz (ver o achado da 1.0 em ``extractors/triple.py``). Por isso a tripla aqui
carrega ``_id: "oid"``.

Como a asserção é de **tipo** (não de contagem), a fixture é reconstruível à mão
com segurança — diferente de ``CountTimestamp``/``SimplifyAggr``, cujas
asserções são as contagens e exigem a geração pelo oráculo.

Bug #6 (corrigido por construção)
---------------------------------
No original, o extrator assumia que todo ``_id`` é ``ObjectId`` e estourava no
``getTimestamp()`` quando não era (``Helpers.java:66``, patch ``0006``). Isso é
**a montante da tripla** — quando o valor chega aqui já é um tipo qualquer. O
segundo teste trava o valor **corrigido**: um ``_id`` não-``ObjectId`` infere
para o seu próprio tipo, sem estourar.
"""

from __future__ import annotations

import pytest
from pyecore.ecore import EObject

from uschema.extractors.triple import SchemaTriple
from uschema.inference.builder import USchemaModelBuilder
from uschema.inference.schema_inference import SchemaInference
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit


def _id_attribute(schema: EObject, entity_index: int = 0) -> EObject:
    """Achar a feature ``_id`` da 1ª variação de uma entidade."""
    entity = list(schema.entities)[entity_index]
    variation = entity.variations[0]
    return next(f for f in variation.features if getattr(f, "name", None) == "_id")


def test_id_e_inferido_como_objectid() -> None:
    # `ObjectIdTest.java:60-63` — uma entidade; o `_id` é Attribute de
    # PrimitiveType "ObjectId". Tripla via map-reduce v1 (`_id: "oid"`).
    triples = [
        SchemaTriple(
            schema={"_type": "things", "_id": "oid", "label": "string"},
            count=4,
            first_timestamp=0,
            last_timestamp=0,
        )
    ]
    raw = SchemaInference().infer(triples)
    schema = USchemaModelBuilder(load_metamodel()).build("DEBUG_ObjectId", raw)

    assert len(schema.entities) == 1

    feature = _id_attribute(schema)
    assert feature.eClass.name == "Attribute"
    assert feature.type.eClass.name == "PrimitiveType"
    assert feature.type.name == "ObjectId"


def test_id_nao_objectid_infere_sem_estourar() -> None:
    # #6 corrigido por construção: um `_id` que não é ObjectId infere para o
    # seu próprio tipo (String), sem o crash do `getTimestamp()` do original.
    triples = [
        SchemaTriple(
            schema={"_type": "things", "_id": "string", "label": "string"},
            count=1,
            first_timestamp=0,
            last_timestamp=0,
        )
    ]
    raw = SchemaInference().infer(triples)
    schema = USchemaModelBuilder(load_metamodel()).build("DEBUG_ObjectId", raw)

    feature = _id_attribute(schema)
    assert feature.eClass.name == "Attribute"
    assert feature.type.name == "String"
