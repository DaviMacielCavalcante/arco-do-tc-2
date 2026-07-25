"""Porte do ``RelationshipTypeToEntityTypeTest.java`` (regressão JUnit, Fase 1.4b).

Fixa a conversão ``RelationshipType`` → ``EntityType`` pela transformação m2m
``USchemaToDocumentDb.relTypeToEntityType`` (``m2m/USchemaToDocumentDb.java:78-155``):
todo ``RelationshipType`` vira um ``EntityType`` com prefixo ``Ref_``, e as
``Reference`` que decoravam variações do relacionamento (via ``isFeaturedBy``)
passam a apontar para o novo ``EntityType``, com os atributos da aresta
embutidos na variação de origem.

Como o ``RemovePMapTest``, este JUnit **não testa o ``USchemaModelBuilder``** —
chama ``schema2DDb.adaptToDocumentDb(schema)`` e monta o ``USchema`` de entrada
na própria classe (ver o achado da 1.6, ``INVENTARIO.md``).
"""

from __future__ import annotations

import pytest
from pyecore.ecore import EObject, EPackage

from uschema.inference.m2m import USchemaToDocumentDb
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit


@pytest.fixture
def pkg() -> EPackage:
    """Metamodelo U-Schema carregado."""
    return load_metamodel()


def _with_variations(pkg: EPackage, schema_type: EObject, count: int) -> EObject:
    """Preencher ``schema_type`` com ``count`` variações ``{attr<i>: String}``.

    Espelha os helpers ``createRelType``/``createEntityType`` do JUnit
    (``:118-155``): variationId de 1 em diante, cada variação com um único
    Attribute ``attr<i>`` de PrimitiveType ``string``.
    """
    for i in range(1, count + 1):
        var = pkg.getEClassifier("StructuralVariation")()
        var.variationId = i
        pt = pkg.getEClassifier("PrimitiveType")()
        pt.name = "string"
        attr = pkg.getEClassifier("Attribute")()
        attr.name = f"attr{i}"
        attr.type = pt
        var.features.append(attr)
        schema_type.variations.append(var)
    return schema_type


def _rel_type(pkg: EPackage, name: str, variations: int) -> EObject:
    rel = pkg.getEClassifier("RelationshipType")()
    rel.name = name
    return _with_variations(pkg, rel, variations)


def _entity_type(pkg: EPackage, name: str, variations: int) -> EObject:
    entity = pkg.getEClassifier("EntityType")()
    entity.name = name
    return _with_variations(pkg, entity, variations)


def _schema(pkg: EPackage, entities: list[EObject], relationships: list[EObject]) -> EObject:
    schema = pkg.getEClassifier("USchema")()
    schema.name = "schema"
    for entity in entities:
        schema.entities.append(entity)
    for rel in relationships:
        schema.relationships.append(rel)
    return schema


def test_relationship_type_vira_entity_type(pkg: EPackage) -> None:
    # `:37-48` — um RelationshipType de 3 variações vira 1 EntityType de 3.
    rel = _rel_type(pkg, "class1", 3)
    schema = _schema(pkg, [], [rel])

    USchemaToDocumentDb(pkg)._rel_type_to_entity_type(schema, rel)

    assert len(schema.relationships) == 0
    assert len(schema.entities) == 1
    assert len(schema.entities[0].variations) == 3


def test_colisao_de_nome_funde_sem_duplicar_forma(pkg: EPackage) -> None:
    # `:51-65` — RelationshipType "class1" (15 vars) + EntityType "Ref_Class1"
    # (4 vars). As 4 primeiras formas colidem e são descartadas; sobem 11.
    # 4 + 11 = 15, não 19.
    rel = _rel_type(pkg, "class1", 15)
    existing = _entity_type(pkg, "Ref_Class1", 4)
    schema = _schema(pkg, [existing], [rel])

    USchemaToDocumentDb(pkg)._rel_type_to_entity_type(schema, rel)

    assert len(schema.relationships) == 0
    assert len(schema.entities) == 1
    assert len(schema.entities[0].variations) == 15


def _featuring_reference(
    pkg: EPackage, host_var: EObject, rel: EObject, refs_to: EObject
) -> EObject:
    """Anexar em ``host_var`` uma Reference que é featured por ``rel`` (``:80-88``)."""
    ref = pkg.getEClassifier("Reference")()
    ref.name = "theReference"
    ref.lowerBound = 1
    ref.upperBound = 2
    ref.refsTo = refs_to
    ref.isFeaturedBy.append(rel.variations[0])
    host_var.features.append(ref)
    return ref


def test_fix_references_embute_a_aresta_sem_criar_aggregate(pkg: EPackage) -> None:
    # `:68-91` — a Reference featured pelo relacionamento é reescrita; a
    # variação de origem NÃO ganha Aggregate (a aresta virou Reference + attrs).
    rel = _rel_type(pkg, "relClass", 1)
    entity1 = _entity_type(pkg, "entity1", 1)
    entity2 = _entity_type(pkg, "entity2", 1)
    schema = _schema(pkg, [entity1, entity2], [rel])
    _featuring_reference(pkg, entity1.variations[0], rel, entity2)

    USchemaToDocumentDb(pkg)._rel_type_to_entity_type(schema, rel)

    assert len(schema.relationships) == 0
    assert len(schema.entities) == 3  # entity1, entity2, Ref_Relclass
    assert all(f.eClass.name != "Aggregate" for f in entity1.variations[0].features)


def test_fix_references_com_colisao_nao_estoura(pkg: EPackage) -> None:
    # `:94-116` — fixReferences + entidade "Ref_Relclass" preexistente. O JUnit
    # só serializa (não afirma); aqui basta rodar sem estourar e limpar a aresta.
    rel = _rel_type(pkg, "relClass", 1)
    entity1 = _entity_type(pkg, "entity1", 1)
    entity2 = _entity_type(pkg, "entity2", 1)
    entity3 = _entity_type(pkg, "Ref_Relclass", 3)
    schema = _schema(pkg, [entity1, entity2, entity3], [rel])
    _featuring_reference(pkg, entity1.variations[0], rel, entity2)

    USchemaToDocumentDb(pkg)._rel_type_to_entity_type(schema, rel)

    assert len(schema.relationships) == 0
    assert len(schema.entities) == 3
