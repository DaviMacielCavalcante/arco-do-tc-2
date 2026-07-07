"""Testes do metamodelo U-Schema (Fase 0.1/0.2).

Cobre a criação reflexiva de um modelo U-Schema mínimo e sua serialização em
XMI. Semente do round-trip da Fase 0.2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pyecore.ecore import EAttribute, EObject, EPackage, EReference

from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model, save_model


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


def _canonical_ref(obj: EObject | None) -> tuple[object, ...]:
    """Descritor curto e sem ``xmi:id`` para uma referência cruzada (não-contenção).

    Usado só para *identificar* o alvo de uma cross-reference (``refsTo``,
    ``isFeaturedBy``, ``key``, ``aggregates``, ``opposite``, ``attributes``...)
    sem recursar na estrutura completa dele — recursar arriscaria ciclo (ex.:
    ``Reference.opposite`` aponta pra outra ``Reference``; ``Key.attributes``
    e ``Attribute.key`` são opostos um do outro).

    Parameters
    ----------
    obj : EObject or None
        Objeto referenciado (ou ``None``, se a referência for opcional e vazia).

    Returns
    -------
    tuple of object
        Tupla identificadora, comparável entre o modelo original e o recarregado.
    """
    if obj is None:
        return ("None",)

    cls_name: str = obj.eClass.name

    if cls_name in {"EntityType", "RelationshipType"}:
        return (cls_name, obj.name)

    if cls_name == "StructuralVariation":
        container = obj.container
        return (cls_name, container.eClass.name, container.name, obj.variationId)

    if cls_name in {"Attribute", "Reference", "Aggregate", "Key"}:
        name = getattr(obj, "name", None)
        if name:
            return (cls_name, name)
        # Feature sem nome (ex.: `Reference` implícita de FK): desambigua pela
        # posição dentro da variação-container, já que a lista de `features`
        # preserva ordem de inserção/leitura.
        container = obj.eContainer()
        index = list(container.features).index(obj) if container is not None else -1
        return (cls_name, "#", index)

    return (cls_name,)


def assert_structurally_equal(original: EObject, reloaded: EObject, path: str = "$") -> None:
    """Comparar recursivamente dois modelos U-Schema, ignorando ``xmi:id``.

    Percorre ``eAllStructuralFeatures()`` de forma genérica (não hardcoded por
    classe): ``EAttribute`` compara por valor; ``EReference`` de contenção
    recursa (a árvore de contenção não tem ciclo, por definição do Ecore);
    ``EReference`` cruzada (``containment=False``) compara por
    ``_canonical_ref`` — sem recursar, para não cair num ciclo (ex.:
    ``Reference.opposite``, ``Key.attributes`` <-> ``Attribute.key``).

    Parameters
    ----------
    original : EObject
        Objeto carregado do XMI-oráculo original.
    reloaded : EObject
        Mesmo objeto, depois de ``save_model`` + ``load_model`` num arquivo novo.
    path : str, optional
        Trilha de depuração (ex.: ``$.entities[0].variations[1]``), só para
        mensagens de assert mais úteis.

    Raises
    ------
    AssertionError
        Na primeira divergência estrutural encontrada, com o `path` de onde
        ocorreu.
    """
    assert original.eClass.name == reloaded.eClass.name, f"{path}: classe diverge"

    for feature in original.eClass.eAllStructuralFeatures():
        feature_path = f"{path}.{feature.name}"
        original_value = getattr(original, feature.name)
        reloaded_value = getattr(reloaded, feature.name)

        if isinstance(feature, EAttribute):
            assert original_value == reloaded_value, (
                f"{feature_path}: {original_value!r} != {reloaded_value!r}"
            )
            continue

        assert isinstance(feature, EReference)

        if not feature.containment:
            # Cross-reference: compara identidade canônica, sem recursar.
            if feature.many:
                original_refs = sorted(_canonical_ref(o) for o in original_value)
                reloaded_refs = sorted(_canonical_ref(o) for o in reloaded_value)
                assert original_refs == reloaded_refs, (
                    f"{feature_path}: {original_refs} != {reloaded_refs}"
                )
            else:
                assert _canonical_ref(original_value) == _canonical_ref(reloaded_value), (
                    f"{feature_path}: referência cruzada diverge"
                )
            continue

        # Contenção: recursa (árvore, sem risco de ciclo).
        if feature.many:
            assert len(original_value) == len(reloaded_value), (
                f"{feature_path}: {len(original_value)} itens != {len(reloaded_value)}"
            )
            for index, (original_item, reloaded_item) in enumerate(
                zip(original_value, reloaded_value, strict=True)
            ):
                assert_structurally_equal(original_item, reloaded_item, f"{feature_path}[{index}]")
        elif original_value is None or reloaded_value is None:
            assert original_value is None and reloaded_value is None, (
                f"{feature_path}: um dos dois é None e o outro não"
            )
        else:
            assert_structurally_equal(original_value, reloaded_value, feature_path)


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

    save_model(schema, out)

    reloaded = load_model(out, metamodel)

    attribute = reloaded.entities[0].variations[0].features[0]

    assert out.exists()
    assert out.stat().st_size > 0
    assert reloaded.entities[0].name == "Customer"
    assert reloaded.entities[0].root is True
    assert attribute.type.name == "String"


@pytest.mark.unit
def test_minimal_schema_round_trip_is_structurally_equal(
    metamodel: EPackage, tmp_path: Path
) -> None:
    """O schema mínimo, depois de save+load, é estruturalmente idêntico ao original."""
    schema = build_minimal_schema(metamodel)
    out = tmp_path / "minimal_roundtrip.xmi"

    save_model(schema, out)
    reloaded = load_model(out, metamodel)

    assert_structurally_equal(schema, reloaded)


RESOURCES_DIR = Path(__file__).resolve().parents[2] / "resources"

ORACLE_XMIS = [
    RESOURCES_DIR / "mongodb" / "model_northwind.xmi",
    RESOURCES_DIR / "mongodb" / "model.xmi",
    RESOURCES_DIR / "neo4j" / "movies_min.xmi",
]


@pytest.mark.unit
@pytest.mark.parametrize("xmi_path", ORACLE_XMIS, ids=lambda p: p.name)
def test_oracle_xmi_round_trip_is_structurally_equal(
    metamodel: EPackage, tmp_path: Path, xmi_path: Path
) -> None:
    """Cada XMI-oráculo, depois de save+load, é estruturalmente idêntico ao original."""
    original = load_model(xmi_path, metamodel)
    out = tmp_path / "roundtrip.xmi"

    save_model(original, out)
    reloaded = load_model(out, metamodel)

    assert_structurally_equal(original, reloaded)


@pytest.mark.unit
def test_structural_comparator_detects_renamed_entity(metamodel: EPackage, tmp_path: Path) -> None:
    """O comparador acusa divergência se uma entidade for renomeada após o reload."""
    schema = build_minimal_schema(metamodel)
    out = tmp_path / "minimal_mutated.xmi"

    save_model(schema, out)
    reloaded = load_model(out, metamodel)
    reloaded.entities[0].name = "Mutated"

    with pytest.raises(AssertionError, match="Mutated"):
        assert_structurally_equal(schema, reloaded)


@pytest.mark.unit
def test_structural_comparator_detects_cleared_cross_reference(
    metamodel: EPackage, tmp_path: Path
) -> None:
    """O comparador acusa divergência se uma cross-reference (``isFeaturedBy``) for zerada."""
    original = load_model(RESOURCES_DIR / "neo4j" / "movies_min.xmi", metamodel)
    out = tmp_path / "movies_mutated.xmi"

    save_model(original, out)
    reloaded = load_model(out, metamodel)

    mutated = False
    for entity in reloaded.entities:
        for variation in entity.variations:
            for feature in variation.features:
                if feature.eClass.name == "Reference" and len(feature.isFeaturedBy) > 0:
                    feature.isFeaturedBy.clear()
                    mutated = True
                    break
            if mutated:
                break
        if mutated:
            break

    assert mutated, "esperava achar uma Reference com isFeaturedBy em movies_min.xmi"

    with pytest.raises(AssertionError, match="isFeaturedBy"):
        assert_structurally_equal(original, reloaded)
