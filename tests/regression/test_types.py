"""Porte do ``TypesTest.java`` (regressão JUnit, bloco B do INVENTARIO).

Fixa que o marcador **``_type`` não vaza para o modelo final**: ele é ao mesmo
tempo o marcador de tipo (nome da entidade) e um atributo ignorado
(``DefaultSchemaInferenceConfig``: ``_type`` está em ``ignored`` e é o
``typeMarker``), então nenhuma ``Feature`` chamada ``_type`` pode sobrar em
nenhuma variação de nenhuma entidade. É a dupla asserção do Java (``:59-64``):
``for e: for ev: assertFalse(feature "_type" present)``.

Sobre a fixture (bloco B — cortada na tripla)
--------------------------------------------
O ``TypesTest.java`` sobe um Mongo, injeta ``testSources/Types.json`` e roda o
map-reduce ``v1`` para obter a lista de triplas. Aqui a tripla é **reconstruída à
mão** a partir da estrutura do ``Types.json`` (coleção ``persons``: campos
escalares + ``links``/``other_names`` aninhados) mais o comportamento do
map-reduce v1: cada folha vira a sentinela ``"string"`` e a **raiz ganha
``_type`` = nome da coleção**. Também injeto ``_type`` num objeto **aninhado**
para exercitar a filtragem em profundidade, não só na raiz.

Esta reconstrução é segura **porque a asserção é independente de contagem**: o
teste só verifica ausência de ``_type``, não os `count`/`variationId` que
dependeriam da agregação exata do map-reduce. Os outros testes do bloco B
(``CountTimestamp``/``ObjectId``/``SimplifyAggr``), cujas asserções **são** as
contagens, precisam da fixture gerada pelo oráculo — não reconstruível à mão sem
risco de "passar por motivo errado".
"""

from __future__ import annotations

import pytest

from uschema.extractors.triple import SchemaTriple
from uschema.inference.builder import USchemaModelBuilder
from uschema.inference.schema_inference import SchemaInference
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit

# Tripla reconstruída de `Types.json` (coleção `persons`) + map-reduce v1:
# folhas viram `"string"`, a raiz ganha `_type`, e — de propósito — um objeto
# aninhado (`other_names`) também carrega `_type`, para cobrir a filtragem em
# profundidade. Duas variações (uma sem `other_names`) para ter >1 EV.
_TRIPLES = [
    SchemaTriple(
        schema={
            "_type": "persons",
            "family_name": "string",
            "given_name": "string",
            "id": "string",
            "links": [{"note": "string", "url": "string"}],
            "name": "string",
            "other_names": [{"_type": "sub", "lang": "string", "name": "string"}],
        },
        count=5,
        first_timestamp=0,
        last_timestamp=0,
    ),
    SchemaTriple(
        schema={
            "_type": "persons",
            "id": "string",
            "name": "string",
        },
        count=3,
        first_timestamp=0,
        last_timestamp=0,
    ),
]


def test_type_marker_nao_aparece_no_modelo() -> None:
    # `TypesTest.java:59-64` — nenhuma feature chamada "_type" em variação alguma.
    raw = SchemaInference().infer(_TRIPLES)
    schema = USchemaModelBuilder(load_metamodel()).build("DEBUG_Type", raw)

    leaked = [
        (entity.name, variation.variationId, feature.name)
        for entity in schema.entities
        for variation in entity.variations
        for feature in variation.features
        if getattr(feature, "name", None) == "_type"
    ]

    assert leaked == [], f"'_type' vazou para o modelo: {leaked}"


def test_type_marker_vira_nome_da_entidade_raiz() -> None:
    # Contraparte positiva: o `_type` é consumido como nome da entidade (raiz),
    # capitalizado pelo Inflector — não some, é *promovido*. Prova que a ausência
    # acima é filtragem, não perda do dado.
    raw = SchemaInference().infer(_TRIPLES)
    schema = USchemaModelBuilder(load_metamodel()).build("DEBUG_Type", raw)

    entity_names = {entity.name for entity in schema.entities}
    assert "Persons" in entity_names
