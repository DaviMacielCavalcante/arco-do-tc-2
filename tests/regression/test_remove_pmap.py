"""Porte do ``RemovePMapTest.java`` (regressão JUnit, Fase 1.4b).

Fixa a remoção de ``PMap`` pela transformação m2m
``USchemaToDocumentDb.removePMap`` (``m2m/USchemaToDocumentDb.java:166-220``):
cada ``Attribute`` de tipo ``PMap`` é extraído para uma entidade ``Map_<Attr>``
com uma variação ``{key, value}``, e o mapa vira um ``Aggregate`` que aponta
para ela. Recursivo em ``PMap`` de ``PMap``.

Este JUnit **não testa o ``USchemaModelBuilder``** — o ``INVENTARIO.md`` mapeava
errado (ver o achado da 1.6). Ele chama ``schema2DDb.adaptToDocumentDb(schema)``,
o módulo m2m, e monta o ``USchema`` de entrada **na própria classe** (sem Mongo,
sem inferência). Aqui os ``EObject`` de entrada são montados igual, via API
reflexiva do PyEcore.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from pyecore.ecore import EObject, EPackage

from uschema.inference.m2m import USchemaToDocumentDb
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit


@pytest.fixture
def pkg() -> EPackage:
    """Metamodelo U-Schema carregado."""
    return load_metamodel()


def _primitive(pkg: EPackage, name: str) -> EObject:
    pt = pkg.getEClassifier("PrimitiveType")()
    pt.name = name
    return pt


def _attribute(pkg: EPackage, name: str, type_: EObject) -> EObject:
    attr = pkg.getEClassifier("Attribute")()
    attr.name = name
    attr.type = type_
    return attr


def _pmap(pkg: EPackage, key_type: EObject, value_type: EObject) -> EObject:
    pmap = pkg.getEClassifier("PMap")()
    pmap.keyType = key_type
    pmap.valueType = value_type
    return pmap


def _variation(pkg: EPackage, variation_id: int, features: list[EObject]) -> EObject:
    var = pkg.getEClassifier("StructuralVariation")()
    var.variationId = variation_id
    for feature in features:
        var.features.append(feature)
    return var


def _entity(pkg: EPackage, name: str, variations: list[EObject]) -> EObject:
    entity = pkg.getEClassifier("EntityType")()
    entity.name = name
    for var in variations:
        entity.variations.append(var)
    return entity


def _schema(pkg: EPackage, name: str, entities: list[EObject]) -> EObject:
    schema = pkg.getEClassifier("USchema")()
    schema.name = name
    for entity in entities:
        schema.entities.append(entity)
    return schema


def _by_name(features: Iterable[EObject]) -> dict[str, EObject]:
    return {f.name: f for f in features}


def test_remove_pmap_simples(pkg: EPackage) -> None:
    # `RemovePMapTest.java:32-66`.
    attr_map = _attribute(
        pkg, "attr2map", _pmap(pkg, _primitive(pkg, "string"), _primitive(pkg, "string"))
    )
    var = _variation(pkg, 1, [_attribute(pkg, "attr1Str", _primitive(pkg, "string")), attr_map])
    entity = _entity(pkg, "entityName", [var])
    schema = _schema(pkg, "testRemovePMap", [entity])

    USchemaToDocumentDb(pkg)._remove_pmap(schema, attr_map)

    # entidade original: attr1Str continua Attribute; attr2map virou Aggregate.
    assert len(schema.entities) == 2
    entity_out = schema.entities[0]
    assert entity_out.name == "entityName"
    assert len(entity_out.variations) == 1
    feats = _by_name(entity_out.variations[0].features)
    assert feats["attr1Str"].eClass.name == "Attribute"
    assert feats["attr2map"].eClass.name == "Aggregate"

    # entidade nova Map_Attr2map: uma variação com key/value.
    map_entity = schema.entities[1]
    assert map_entity.name == "Map_Attr2map"
    assert len(map_entity.variations) == 1
    map_feats = _by_name(map_entity.variations[0].features)
    assert map_feats["key"].eClass.name == "Attribute"
    assert map_feats["value"].eClass.name == "Attribute"


def test_remove_pmap_de_duas_variacoes_nao_duplica_entidade(pkg: EPackage) -> None:
    # `:69-115` — o mesmo mapa em duas variações gera UMA entidade Map_ só.
    map1 = _attribute(
        pkg, "attr2map", _pmap(pkg, _primitive(pkg, "string"), _primitive(pkg, "string"))
    )
    map2 = _attribute(
        pkg, "attr2map", _pmap(pkg, _primitive(pkg, "string"), _primitive(pkg, "string"))
    )
    var1 = _variation(pkg, 1, [_attribute(pkg, "attr1Str", _primitive(pkg, "string")), map1])
    var2 = _variation(pkg, 2, [map2])
    entity = _entity(pkg, "entityName", [var1, var2])
    schema = _schema(pkg, "testTwoVariations", [entity])

    transformer = USchemaToDocumentDb(pkg)
    transformer._remove_pmap(schema, map1)
    transformer._remove_pmap(schema, map2)

    assert len(schema.entities) == 2
    map_entity = schema.entities[1]
    assert map_entity.name == "Map_Attr2map"
    assert len(map_entity.variations) == 1  # find-or-create segurou a duplicata


def test_remove_pmap_recursivo(pkg: EPackage) -> None:
    # `:118-140` — Map<String, Map<Int,Int>>: o mapa interno também é extraído.
    inner = _pmap(pkg, _primitive(pkg, "int"), _primitive(pkg, "int"))
    attr_map = _attribute(pkg, "attr2map", _pmap(pkg, _primitive(pkg, "string"), inner))
    var = _variation(pkg, 1, [attr_map])
    entity = _entity(pkg, "entityName", [var])
    schema = _schema(pkg, "testRecursive", [entity])

    USchemaToDocumentDb(pkg)._remove_pmap(schema, attr_map)

    # nenhum Attribute de tipo PMap sobra na variação original.
    leftover_pmaps = [
        f for f in var.features if f.eClass.name == "Attribute" and f.type.eClass.name == "PMap"
    ]
    assert leftover_pmaps == []
    # e o mapa aninhado virou sua própria entidade.
    assert {e.name for e in schema.entities} == {"entityName", "Map_Attr2map", "Map_Value"}
