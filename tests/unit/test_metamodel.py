"""Testes do metamodelo U-Schema (Fase 0.1/0.2).

Cobre a criação reflexiva de um modelo U-Schema mínimo e sua serialização em
XMI. Semente do round-trip da Fase 0.2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pyecore.ecore import EObject, EPackage
from pyecore.resources import URI, Resource, ResourceSet

from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model


@pytest.fixture
def metamodel() -> EPackage:
    """Metamodelo U-Schema carregado e registrado."""
    return load_metamodel()


def build_minimal_schema(pkg: EPackage) -> EObject:
    """Construir um ``USchema`` mínimo via API reflexiva.

    Um schema com exatamente 1 ``EntityType`` (root) contendo 1
    ``StructuralVariation`` que contém 1 ``Attribute``.

    Parameters
    ----------
    pkg : EPackage
        Metamodelo carregado (saída de ``load_metamodel``).

    Returns
    -------
    EObject
        A raiz ``USchema`` do modelo montado.
    """
    # Padrão da API reflexiva do PyEcore: o EClass é obtido do pacote pelo nome
    # e é *chamável* para criar instâncias; features viram kwargs ou atributos.
    #   Cls = pkg.getEClassifier("NomeDaClasse")
    #   obj = Cls(atributo="valor")

    uschema_class = pkg.getEClassifier("USchema")

    entity_type_class = pkg.getEClassifier("EntityType")

    structural_variation_class = pkg.getEClassifier("StructuralVariation")

    attribute_class = pkg.getEClassifier("Attribute")

    primitive_type_class = pkg.getEClassifier("PrimitiveType")

    string_type = primitive_type_class(name="String")

    uschema_obj = uschema_class(name="Mongo")

    customer_obj = entity_type_class(name="Customer", root=True)

    uschema_obj.entities.append(customer_obj)

    customer_variation = structural_variation_class(variationId=1)

    customer_obj.variations.append(customer_variation)

    attribute_name = attribute_class(name="companyName")
    attribute_name.type = string_type

    customer_variation.features.append(attribute_name)

    return uschema_obj


@pytest.mark.unit
def test_minimal_schema_has_expected_shape(metamodel: EPackage) -> None:
    """O schema mínimo tem 1 entidade → 1 variação → 1 atributo."""

    schema = build_minimal_schema(metamodel)

    entity = schema.entities[0]

    variation = schema.entities[0].variations[0]

    attribute = variation.features[0]

    assert len(schema.entities) == 1
    assert len(entity.variations) == 1
    assert len(variation.features) == 1
    assert entity.root is True
    assert entity.name == "Customer"
    assert attribute.type is not None
    assert attribute.type.name == "String"
    assert attribute.name == "companyName"


@pytest.mark.unit
def test_minimal_schema_serializes_to_xmi(metamodel: EPackage, tmp_path: Path) -> None:
    """O schema mínimo serializa para um arquivo XMI não-vazio."""
    schema = build_minimal_schema(metamodel)
    out = tmp_path / "minimal.xmi"

    rset: ResourceSet = ResourceSet()

    resource: Resource = rset.create_resource(URI(str(out)))

    resource.append(schema)

    resource.save()

    reloaded = load_model(out, metamodel)

    attribute = reloaded.entities[0].variations[0].features[0]

    assert out.exists()
    assert out.stat().st_size > 0
    assert reloaded.entities[0].name == "Customer"
    assert reloaded.entities[0].root is True
    assert attribute.type.name == "String"
