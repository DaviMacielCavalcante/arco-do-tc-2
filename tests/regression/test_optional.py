"""Porte do ``OptionalTest.java`` (regressão JUnit, bloco A do INVENTARIO).

Fixa a **opcionalidade de atributo entre variações**: uma feature presente em
uma variação mas ausente de outra é ``optional``; uma presente em todas não é.
Quem decide isso é o ``FeatureAnalyzer`` (``set_optional_properties``, Fase 1.3b),
rodado no fim do ``USchemaModelBuilder.build``.

Duas divergências deliberadas em relação ao JUnit original, ambas registradas:

1. **O oráculo reprova este teste; o porte passa — e é o correto.** O
   ``OptionalTest`` do Java instancia o builder via ``OptionalTestConfig``, que
   **não liga o ``FeatureAnalyzer``** (é o bug do patch ``#1``, nunca corrigido no
   upstream): ``optionalAttr.isOptional()`` devolve ``false`` e o
   ``assertTrue(...)`` falha. Sem Guice, o nosso wiring liga o analyzer sempre, o
   bug **some por construção**, e o valor correto é afirmado aqui — como manda o
   roadmap ("afirme o valor corrigido onde houve bug"). Não tomar o vermelho do
   oráculo como esperado.

2. **Asserção por semântica, não por índice posicional.** O JUnit indexa
   ``features.get(1)``/``.get(2)``. No nosso porte ``features[1]`` é o ``Key`` que
   o campo ``_id`` gera (``fillEV:201-207``), então os índices literais do Java
   apontariam para o objeto errado. O que o teste realmente fixa é a
   opcionalidade **por nome de feature**, e é isso que se afirma.

O ``jsonContent`` do original é a lista de triplas escrita à mão dentro do teste
— exatamente o contrato de ``extractors/triple.py``. Reusado aqui verbatim.
"""

from __future__ import annotations

import pytest
from pyecore.ecore import EObject

from uschema.extractors.triple import SchemaTriple
from uschema.inference.builder import USchemaModelBuilder
from uschema.inference.schema_inference import SchemaInference
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit

# `OptionalTest.java:24-45` — o `jsonContent` literal, como triplas nativas.
# `optionalAttr` só existe na 1ª variação; `requiredAttr` e `_id` nas duas.
_TRIPLES = [
    SchemaTriple(
        schema={"_id": "s", "optionalAttr": "s", "requiredAttr": "s", "_type": "MyEntity"},
        count=1,
        first_timestamp=0,
        last_timestamp=0,
    ),
    SchemaTriple(
        schema={"_id": "s", "requiredAttr": "s", "_type": "MyEntity"},
        count=10,
        first_timestamp=0,
        last_timestamp=0,
    ),
]


def _build() -> EObject:
    """Rodar o pipeline `infer` + `build` sobre as triplas do teste."""
    raw = SchemaInference().infer(_TRIPLES)
    return USchemaModelBuilder(load_metamodel()).build("test", raw)


def _attributes_by_name(variation: EObject) -> dict[str, EObject]:
    """Mapear ``nome -> Attribute`` das features de uma variação (ignora Key)."""
    return {f.name: f for f in variation.structuralFeatures if f.eClass.name == "Attribute"}


def test_uma_entidade() -> None:
    # `OptionalTest.java:61` — assertEquals(1, entities.size()).
    schema = _build()

    assert len(schema.entities) == 1


def test_atributo_ausente_de_uma_variacao_e_opcional() -> None:
    # `:65,68` — o `optionalAttr` (só na 1ª variação) é opcional.
    schema = _build()
    [entity] = list(schema.entities)

    # a variação que tem optionalAttr (a de count=1).
    variation = next(v for v in entity.variations if "optionalAttr" in _attributes_by_name(v))
    optional_attr = _attributes_by_name(variation)["optionalAttr"]

    assert optional_attr.optional is True


def test_atributo_presente_em_todas_as_variacoes_nao_e_opcional() -> None:
    # `:66-67,69-70` — `requiredAttr` está nas duas variações: não é opcional,
    # em nenhuma delas. (No Java: mandatoryAttr1 na var 0, mandatoryAttr2 na var 1.)
    schema = _build()
    [entity] = list(schema.entities)

    required = [
        _attributes_by_name(v)["requiredAttr"]
        for v in entity.variations
        if "requiredAttr" in _attributes_by_name(v)
    ]

    assert len(required) == 2
    assert all(attr.optional is False for attr in required)
