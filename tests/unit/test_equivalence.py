"""Testes do harness de equivalência estrutural (Fase 0.3).

Testa as funções de comparação de baixo para cima (folhas → topo), montando
``EObject``s mínimos via API reflexiva do PyEcore.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pyecore.ecore import EObject, EPackage

from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model
from uschema.validation.equivalence import (
    DivergenceCategory,
    _match_bag,
    _same_container,
    compare,
    compare_aggregate,
    compare_datatype,
    compare_feature,
    compare_key,
    compare_primitive_type,
    compare_reference,
    compare_variation,
)


@pytest.fixture
def metamodel() -> EPackage:
    """Metamodelo U-Schema carregado (para instanciar EObjects de teste)."""
    return load_metamodel()


def make_primitive(pkg: EPackage, name: str | None) -> EObject:
    """Criar um ``PrimitiveType`` com o nome dado, via API reflexiva.

    ``name=None`` monta um ``PrimitiveType`` **sem nome** — o ecore declara
    ``lowerBound=1``, mas o PyEcore não impõe, e o ``ComparePrimitiveType`` do
    original trata o caso explicitamente (XOR).
    """
    primitive_type_class = pkg.getEClassifier("PrimitiveType")
    return primitive_type_class(name=name)


def make_primitives(pkg: EPackage, names: list[str]) -> list[EObject]:
    """Criar uma lista de ``PrimitiveType`` a partir de uma lista de nomes."""
    return [make_primitive(pkg, name) for name in names]


def make_null(pkg: EPackage) -> EObject:
    """Criar um ``Null`` (o tipo nulo do U-Schema)."""
    return pkg.getEClassifier("Null")()


def make_plist(pkg: EPackage, element: EObject) -> EObject:
    """Criar um ``PList`` com o ``elementType`` dado."""
    plist = pkg.getEClassifier("PList")()
    plist.elementType = element
    return plist


def make_empty_plist(pkg: EPackage) -> EObject:
    """Criar um ``PList`` **sem** ``elementType`` — o array vazio.

    É o que a ferramenta produz para um ``[]`` no documento: um ``PList`` cujo
    ``elementType`` fica nulo, porque não há elemento do qual inferir o tipo. É o
    caso do atributo ``privileges`` de ``Employees`` no ``model_northwind.xmi``.

    Parameters
    ----------
    pkg : EPackage
        Metamodelo U-Schema carregado.

    Returns
    -------
    EObject
        Um ``PList`` com ``elementType is None``.
    """
    plist = pkg.getEClassifier("PList")()
    return plist


def make_pset(pkg: EPackage, element: EObject) -> EObject:
    """Criar um ``PSet`` com o ``elementType`` dado."""
    pset = pkg.getEClassifier("PSet")()
    pset.elementType = element
    return pset


def make_empty_pset(pkg: EPackage) -> EObject:
    """Criar um ``PSet`` **sem** ``elementType`` — o análogo do ``make_empty_plist``."""
    return pkg.getEClassifier("PSet")()


def make_pmap(pkg: EPackage, key: EObject | None, value: EObject | None) -> EObject:
    """Criar um ``PMap`` com ``keyType`` (primitivo) e ``valueType`` dados.

    Ambos aceitam ``None``: o ``ComparePMap`` do original guarda ``keyType`` e
    ``valueType`` ausentes de forma **independente**, e o teste precisa montar
    cada combinação.
    """
    pmap = pkg.getEClassifier("PMap")()
    if key is not None:
        pmap.keyType = key
    if value is not None:
        pmap.valueType = value
    return pmap


def make_ptuple(pkg: EPackage, elements: list[EObject]) -> EObject:
    """Criar um ``PTuple`` com a lista de ``elements`` dada."""
    ptuple = pkg.getEClassifier("PTuple")()
    for element in elements:
        ptuple.elements.append(element)
    return ptuple


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name1", "name2", "expected"),
    [
        ("Long", "Integer", True),
        ("Long", "Number", True),
        ("Double", "Float", True),
        ("String", "Long", False),
        ("Date", "Date", True),
        ("Date", "date", False),
        ("String", "String", True),
    ],
)
def test_compare_primitive_type(
    metamodel: EPackage, name1: str, name2: str, expected: bool
) -> None:
    p1 = make_primitive(metamodel, name1)
    p2 = make_primitive(metamodel, name2)

    assert compare_primitive_type(p1, p2) is expected


@pytest.mark.unit
def test_compare_primitive_type_guards(metamodel: EPackage) -> None:
    """Nulos em ``ComparePrimitiveType`` — objeto e nome tratados de formas opostas.

    Espelha as asserções do ``CompareDataTypeTest`` do upstream, que este porte
    não cobria: `compare_pmap` chama `compare_primitive_type` **direto** com o
    `keyType`, que pode ser nulo de um lado só — sem estes guardas, `AttributeError`.

    - **objeto** nulo -> `checkNulls` é `or`: reprova, mesmo com os dois nulos.
    - **nome** nulo -> XOR: um só reprova, os dois casam.
    """
    string = make_primitive(metamodel, "String")
    unnamed = make_primitive(metamodel, None)

    # checkNulls (`or`): assertFalse(cPrimitiveType.compare(null, null))
    assert compare_primitive_type(None, None) is False
    assert compare_primitive_type(string, None) is False
    assert compare_primitive_type(None, string) is False

    # nome nulo (XOR): assertFalse(compare(createPrimitiveType(null), ...("string")))
    assert compare_primitive_type(unnamed, string) is False
    assert compare_primitive_type(string, unnamed) is False

    # ambos os nomes nulos -> casam
    assert compare_primitive_type(unnamed, make_primitive(metamodel, None)) is True

    # `"null"` é um NOME de tipo, não ausência de nome — não confundir os dois.
    null_named = make_primitive(metamodel, "null")
    assert compare_primitive_type(null_named, make_primitive(metamodel, "null")) is True
    assert compare_primitive_type(null_named, unnamed) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("names1", "names2", "expected"),
    [
        (["String", "Long"], ["Long", "String"], True),
        (["String", "String"], ["String", "Double"], False),
        ([], [], True),
        (["Long", "Float"], ["Double", "Integer"], True),
    ],
)
def test_match_bag(
    metamodel: EPackage, names1: list[str], names2: list[str], expected: bool
) -> None:
    items1 = make_primitives(metamodel, names1)
    items2 = make_primitives(metamodel, names2)

    assert _match_bag(items1, items2, compare_primitive_type) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build1", "build2", "expected"),
    [
        # Cada `build*` é uma função que recebe o metamodelo e devolve um DataType
        # montado — usamos funções porque criar um EObject precisa do `pkg`.
        # PrimitiveType String vs String -> mesmo tipo canônico -> casam.
        (
            lambda p: make_primitive(p, "String"),
            lambda p: make_primitive(p, "String"),
            True,
        ),
        # PList de String vs PList de String -> recursa no elementType -> casam.
        (
            lambda p: make_plist(p, make_primitive(p, "String")),
            lambda p: make_plist(p, make_primitive(p, "String")),
            True,
        ),
        # PList vs PSet (tipos concretos diferentes) -> nomes de eClass diferem -> NÃO casam.
        (
            lambda p: make_plist(p, make_primitive(p, "String")),
            lambda p: make_pset(p, make_primitive(p, "String")),
            False,
        ),
        # PList de PList de Long vs de Integer -> recursa aninhado + colapso number -> casam.
        (
            lambda p: make_plist(p, make_plist(p, make_primitive(p, "Long"))),
            lambda p: make_plist(p, make_plist(p, make_primitive(p, "Integer"))),
            True,
        ),
        # PTuple (String, Long) vs (Long, String) -> _match_bag ignora ordem -> casam.
        (
            lambda p: make_ptuple(p, make_primitives(p, ["String", "Long"])),
            lambda p: make_ptuple(p, make_primitives(p, ["Long", "String"])),
            True,
        ),
        # PMap String->Long vs String->Integer -> value colapsa p/ number -> casam.
        (
            lambda p: make_pmap(p, make_primitive(p, "String"), make_primitive(p, "Long")),
            lambda p: make_pmap(p, make_primitive(p, "String"), make_primitive(p, "Integer")),
            True,
        ),
        # Null vs Null -> case "Null" -> casam.
        (make_null, make_null, True),
        # Null vs PrimitiveType String (tipos diferentes) -> NÃO casam.
        (make_null, lambda p: make_primitive(p, "String"), False),
        # --- Tipo AUSENTE (None) != tipo `Null` do metamodelo.
        # `Null` é uma EClass: um tipo que EXISTE e diz "o valor é nulo".
        # `None` é a AUSÊNCIA de tipo: o elementType de um array vazio.
        #
        # `compare_datatype` ISOLADO reprova (None, None): o `checkNulls` do Java é
        # `or`, não XOR, e o CompareDataTypeTest do upstream trava isso. Quem trata
        # "ausente dos dois lados" são os CONTÊINERES, antes de delegar — ver os
        # casos de PList/PSet/PMap logo abaixo.
        (lambda p: None, lambda p: None, False),
        (lambda p: None, lambda p: make_primitive(p, "String"), False),
        (lambda p: make_primitive(p, "String"), lambda p: None, False),
        # O caso do dado real: `privileges` de Employees no northwind (array vazio).
        # Dois PList sem elementType casam pela guarda do ComparePList, que
        # curto-circuita ANTES do compare_datatype. Sem ela, o northwind não é
        # equivalente a si mesmo.
        (make_empty_plist, make_empty_plist, True),
        # PList vazio vs. PList de String -> um tem elemento, o outro não -> NÃO casam.
        (make_empty_plist, lambda p: make_plist(p, make_primitive(p, "String")), False),
        # Mesma guarda no PSet (o ComparePSet é o ComparePList palavra por palavra).
        (make_empty_pset, make_empty_pset, True),
        (make_empty_pset, lambda p: make_pset(p, make_primitive(p, "String")), False),
        # PMap: guardas INDEPENDENTES para keyType e valueType.
        (
            lambda p: make_pmap(p, make_primitive(p, "String"), None),
            lambda p: make_pmap(p, make_primitive(p, "String"), None),
            True,
        ),
        (
            lambda p: make_pmap(p, None, make_primitive(p, "Boolean")),
            lambda p: make_pmap(p, None, make_primitive(p, "Boolean")),
            True,
        ),
        (
            lambda p: make_pmap(p, make_primitive(p, "String"), None),
            lambda p: make_pmap(p, make_primitive(p, "String"), make_primitive(p, "Boolean")),
            False,
        ),
    ],
)
def test_compare_datatype(
    metamodel: EPackage,
    build1: Callable[[EPackage], EObject | None],
    build2: Callable[[EPackage], EObject | None],
    expected: bool,
) -> None:
    assert compare_datatype(build1(metamodel), build2(metamodel)) is expected


def make_attribute(
    pkg: EPackage, name: str | None, type_name: str | None = "String", *, optional: bool = False
) -> EObject:
    """Criar um ``Attribute`` com nome, tipo primitivo e ``optional`` dados."""
    attribute = pkg.getEClassifier("Attribute")(name=name)
    if type_name is not None:
        attribute.type = make_primitive(pkg, type_name)
    attribute.optional = optional
    return attribute


def make_key(pkg: EPackage, attributes: list[EObject], name: str | None = "pk") -> EObject:
    """Criar uma ``Key`` com a lista de ``attributes`` dada."""
    key = pkg.getEClassifier("Key")(name=name)
    for attribute in attributes:
        key.attributes.append(attribute)
    return key


def make_entity(pkg: EPackage, name: str) -> EObject:
    """Criar um ``EntityType`` com o nome dado."""
    return pkg.getEClassifier("EntityType")(name=name)


def make_variation(
    pkg: EPackage,
    features: list[EObject] | None = None,
    *,
    container_name: str | None = None,
    variation_id: int = 1,
    count: int = 0,
) -> EObject:
    """Criar uma ``StructuralVariation``, opcionalmente dentro de um ``EntityType``.

    Passar ``container_name`` cria o ``EntityType`` e o liga pelo ``eOpposite``
    de ``variations``/``container``.
    """
    variation = pkg.getEClassifier("StructuralVariation")(variationId=variation_id)
    variation.count = count
    for feature in features or []:
        variation.features.append(feature)
    if container_name is not None:
        make_entity(pkg, container_name).variations.append(variation)
    return variation


def make_aggregate(
    pkg: EPackage,
    container_names: list[str | None],
    *,
    name: str | None = "agg",
    upper: int = 1,
    lower: int = 0,
    optional: bool = False,
) -> EObject:
    """Criar um ``Aggregate`` apontando para uma variação por nome de container."""
    aggregate = pkg.getEClassifier("Aggregate")(name=name)
    aggregate.upperBound = upper
    aggregate.lowerBound = lower
    aggregate.optional = optional
    for container_name in container_names:
        aggregate.aggregates.append(make_variation(pkg, container_name=container_name))
    return aggregate


def make_reference(
    pkg: EPackage,
    *,
    name: str | None = "ref",
    refs_to: str | None = "Order",
    upper: int = 1,
    lower: int = 0,
    attributes: list[EObject] | None = None,
    featured_by: list[str] | None = None,
    opposite: EObject | None = None,
) -> EObject:
    """Criar uma ``Reference`` com os cinco campos que o comparador olha."""
    reference = pkg.getEClassifier("Reference")(name=name)
    reference.upperBound = upper
    reference.lowerBound = lower
    if refs_to is not None:
        reference.refsTo = make_entity(pkg, refs_to)
    for attribute in attributes or []:
        reference.attributes.append(attribute)
    for container_name in featured_by or []:
        reference.isFeaturedBy.append(make_variation(pkg, container_name=container_name))
    if opposite is not None:
        reference.opposite = opposite
    return reference


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build1", "build2", "expected"),
    [
        # Attribute: nome, tipo e `optional` iguais -> casam.
        (
            lambda p: make_attribute(p, "id", "String"),
            lambda p: make_attribute(p, "id", "String"),
            True,
        ),
        # `optional` diferente -> reprova (o XOR vive no ramo StructuralFeature).
        (
            lambda p: make_attribute(p, "id", "String"),
            lambda p: make_attribute(p, "id", "String", optional=True),
            False,
        ),
        # Tipo diferente -> reprova.
        (
            lambda p: make_attribute(p, "id", "String"),
            lambda p: make_attribute(p, "id", "Long"),
            False,
        ),
        # Nome de Feature é case-SENSITIVE: é chave literal do documento, não
        # passou pelo Inflector (ao contrário dos nomes de SchemaType).
        (
            lambda p: make_attribute(p, "id", "String"),
            lambda p: make_attribute(p, "ID", "String"),
            False,
        ),
        # Long vs Integer colapsam para `number` no _PRIMITIVE_TYPE_MAP.
        (
            lambda p: make_attribute(p, "n", "Long"),
            lambda p: make_attribute(p, "n", "Integer"),
            True,
        ),
        # XOR de presença de nome: nomeado vs anônimo -> reprova.
        (
            lambda p: make_attribute(p, "id", "String"),
            lambda p: make_attribute(p, None, "String"),
            False,
        ),
        # Ambos anônimos: o bloco de nomes NÃO aprova, cai no despacho por tipo.
        (
            lambda p: make_attribute(p, None, "String"),
            lambda p: make_attribute(p, None, "String"),
            True,
        ),
        # Ambos anônimos, tipos diferentes: o despacho reprova. Se o bloco de
        # nomes aprovasse cedo (bug), isto daria True.
        (
            lambda p: make_attribute(p, None, "String"),
            lambda p: make_attribute(p, None, "Long"),
            False,
        ),
        # eClass diferente (Attribute vs Key) -> reprova sem tocar em `optional`.
        (
            lambda p: make_attribute(p, "id", "String"),
            lambda p: make_key(p, [make_attribute(p, "id", "String")], name="id"),
            False,
        ),
        # Key vs Key: LogicalFeature não tem `optional`. Ler o campo aqui seria
        # AttributeError — este caso existe para travar o despacho no braço certo.
        (
            lambda p: make_key(p, [make_attribute(p, "_id", "String")]),
            lambda p: make_key(p, [make_attribute(p, "_id", "String")]),
            True,
        ),
        # Reference vs Reference: idem, e exercita o caminho compare_reference.
        (
            lambda p: make_reference(p),
            lambda p: make_reference(p),
            True,
        ),
    ],
)
def test_compare_feature(
    metamodel: EPackage,
    build1: Callable[[EPackage], EObject],
    build2: Callable[[EPackage], EObject],
    expected: bool,
) -> None:
    assert compare_feature(build1(metamodel), build2(metamodel)) is expected


@pytest.mark.unit
def test_compare_feature_guards(metamodel: EPackage) -> None:
    """`checkNulls` é ``or`` (dois ``None`` reprovam) e `checkEquals` é identidade."""
    feature = make_attribute(metamodel, "id", "String")

    assert compare_feature(None, feature) is False
    assert compare_feature(feature, None) is False
    assert compare_feature(None, None) is False
    assert compare_feature(feature, feature) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("names1", "names2", "expected"),
    [
        ([("_id", "String")], [("_id", "String")], True),
        ([], [], True),
        # Multiset: ordem não importa.
        ([("a", "String"), ("b", "Long")], [("b", "Long"), ("a", "String")], True),
        ([("_id", "String")], [("_id", "Long")], False),
        ([("_id", "String")], [("id", "String")], False),
        ([("a", "String"), ("b", "Long")], [("a", "String")], False),
        ([("a", "String")], [("a", "String"), ("b", "Long")], False),
        # `_match_bag` remove do saco: uma duplicata não casa duas vezes.
        ([("a", "String"), ("a", "String")], [("a", "String"), ("b", "String")], False),
    ],
)
def test_compare_key(
    metamodel: EPackage,
    names1: list[tuple[str, str]],
    names2: list[tuple[str, str]],
    expected: bool,
) -> None:
    key1 = make_key(metamodel, [make_attribute(metamodel, n, t) for n, t in names1])
    key2 = make_key(metamodel, [make_attribute(metamodel, n, t) for n, t in names2])

    assert compare_key(key1, key2) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build1", "build2", "expected"),
    [
        (lambda p: make_variation(p), lambda p: make_variation(p), True),
        (
            lambda p: make_variation(p, [make_attribute(p, "a", "String")]),
            lambda p: make_variation(p, [make_attribute(p, "a", "String")]),
            True,
        ),
        # Multiset de features: ordem não importa.
        (
            lambda p: make_variation(
                p, [make_attribute(p, "a", "String"), make_attribute(p, "b", "Long")]
            ),
            lambda p: make_variation(
                p, [make_attribute(p, "b", "Long"), make_attribute(p, "a", "String")]
            ),
            True,
        ),
        # `variationId` e `count` são IGNORADOS pelo CompareStructuralVariation.
        (
            lambda p: make_variation(
                p, [make_attribute(p, "a", "String")], variation_id=1, count=7
            ),
            lambda p: make_variation(
                p, [make_attribute(p, "a", "String")], variation_id=9, count=3000
            ),
            True,
        ),
        (
            lambda p: make_variation(p, [make_attribute(p, "a", "String")]),
            lambda p: make_variation(p, [make_attribute(p, "a", "Long")]),
            False,
        ),
        (
            lambda p: make_variation(
                p, [make_attribute(p, "a", "String"), make_attribute(p, "b", "Long")]
            ),
            lambda p: make_variation(p, [make_attribute(p, "a", "String")]),
            False,
        ),
    ],
)
def test_compare_variation(
    metamodel: EPackage,
    build1: Callable[[EPackage], EObject],
    build2: Callable[[EPackage], EObject],
    expected: bool,
) -> None:
    assert compare_variation(build1(metamodel), build2(metamodel)) is expected


@pytest.mark.unit
def test_compare_variation_guards(metamodel: EPackage) -> None:
    """`checkNulls` é ``or``; `checkEquals` corta a recursão no smoke test A==A."""
    variation = make_variation(metamodel, [make_attribute(metamodel, "a", "String")])

    assert compare_variation(None, variation) is False
    assert compare_variation(None, None) is False
    assert compare_variation(variation, variation) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("container1", "container2", "expected"),
    [
        ("Address", "Address", True),
        ("Address", "Payment", False),
        # Fuzzy do compare_names: pluralização passa.
        ("Order", "Orders", True),
        # Fuzzy NÃO é distância de edição: typo reprova (e deve reprovar).
        ("Address", "Adress", False),
        # Ambos sem container: o Java aprova.
        (None, None, True),
        # XOR de presença do container.
        ("Address", None, False),
    ],
)
def test_same_container(
    metamodel: EPackage, container1: str | None, container2: str | None, expected: bool
) -> None:
    variation1 = make_variation(metamodel, container_name=container1)
    variation2 = make_variation(metamodel, container_name=container2)

    assert _same_container(variation1, variation2) is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build1", "build2", "expected"),
    [
        (lambda p: make_aggregate(p, ["Address"]), lambda p: make_aggregate(p, ["Address"]), True),
        (lambda p: make_aggregate(p, ["Address"]), lambda p: make_aggregate(p, ["Payment"]), False),
        (
            lambda p: make_aggregate(p, ["Address"], upper=1),
            lambda p: make_aggregate(p, ["Address"], upper=-1),
            False,
        ),
        (
            lambda p: make_aggregate(p, ["Address"], lower=0),
            lambda p: make_aggregate(p, ["Address"], lower=1),
            False,
        ),
        # Multiset de containers: ordem não importa.
        (
            lambda p: make_aggregate(p, ["Address", "Payment"]),
            lambda p: make_aggregate(p, ["Payment", "Address"]),
            True,
        ),
        (
            lambda p: make_aggregate(p, ["Address", "Payment"]),
            lambda p: make_aggregate(p, ["Address"]),
            False,
        ),
    ],
)
def test_compare_aggregate(
    metamodel: EPackage,
    build1: Callable[[EPackage], EObject],
    build2: Callable[[EPackage], EObject],
    expected: bool,
) -> None:
    assert compare_aggregate(build1(metamodel), build2(metamodel)) is expected


@pytest.mark.unit
def test_compare_aggregate_ignores_aggregated_features(metamodel: EPackage) -> None:
    """As variações agregadas são casadas SÓ pelo nome do container.

    Espelha ``CompareAggregate``: duas ``Aggregate`` apontando para variações
    estruturalmente diferentes do **mesmo** ``EntityType`` casam. É deliberado —
    é o que impede recursão infinita em agregado cíclico.
    """
    aggregate1 = metamodel.getEClassifier("Aggregate")(name="agg")
    aggregate2 = metamodel.getEClassifier("Aggregate")(name="agg")
    for aggregate in (aggregate1, aggregate2):
        aggregate.upperBound = 1
        aggregate.lowerBound = 0

    variation1 = make_variation(
        metamodel, [make_attribute(metamodel, "street", "String")], container_name="Address"
    )
    variation2 = make_variation(
        metamodel, [make_attribute(metamodel, "zip", "Long")], container_name="Address"
    )
    aggregate1.aggregates.append(variation1)
    aggregate2.aggregates.append(variation2)

    assert compare_variation(variation1, variation2) is False
    assert compare_aggregate(aggregate1, aggregate2) is True


@pytest.mark.unit
def test_compare_aggregate_guards(metamodel: EPackage) -> None:
    """`checkNulls` é ``or``: dois ``None`` reprovam (não aprovam)."""
    aggregate = make_aggregate(metamodel, ["Address"])

    assert compare_aggregate(None, aggregate) is False
    assert compare_aggregate(None, None) is False
    assert compare_aggregate(aggregate, aggregate) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build1", "build2", "expected"),
    [
        (lambda p: make_reference(p), lambda p: make_reference(p), True),
        # bounds
        (
            lambda p: make_reference(p, upper=1),
            lambda p: make_reference(p, upper=-1),
            False,
        ),
        # refsTo
        (
            lambda p: make_reference(p, refs_to="Order"),
            lambda p: make_reference(p, refs_to="Payment"),
            False,
        ),
        # refsTo passa pelo fuzzy de compare_names (pluralização).
        (
            lambda p: make_reference(p, refs_to="Order"),
            lambda p: make_reference(p, refs_to="Orders"),
            True,
        ),
        (
            lambda p: make_reference(p, refs_to=None),
            lambda p: make_reference(p, refs_to=None),
            True,
        ),
        (
            lambda p: make_reference(p, refs_to="Order"),
            lambda p: make_reference(p, refs_to=None),
            False,
        ),
        # attributes: multiset via compare_feature.
        (
            lambda p: make_reference(
                p, attributes=[make_attribute(p, "a", "String"), make_attribute(p, "b", "Long")]
            ),
            lambda p: make_reference(
                p, attributes=[make_attribute(p, "b", "Long"), make_attribute(p, "a", "String")]
            ),
            True,
        ),
        (
            lambda p: make_reference(p, attributes=[make_attribute(p, "a", "String")]),
            lambda p: make_reference(p, attributes=[make_attribute(p, "a", "Long")]),
            False,
        ),
        (
            lambda p: make_reference(p, attributes=[make_attribute(p, "a", "String")]),
            lambda p: make_reference(p),
            False,
        ),
        # isFeaturedBy: XOR de vazio.
        (
            lambda p: make_reference(p, featured_by=["Order"]),
            lambda p: make_reference(p),
            False,
        ),
        (
            lambda p: make_reference(p, featured_by=["Order"]),
            lambda p: make_reference(p, featured_by=["Order"]),
            True,
        ),
        (
            lambda p: make_reference(p, featured_by=["Order"]),
            lambda p: make_reference(p, featured_by=["Payment"]),
            False,
        ),
        # isFeaturedBy: o check de tamanho é load-bearing (não há _match_bag).
        (
            lambda p: make_reference(p, featured_by=["Order", "Payment"]),
            lambda p: make_reference(p, featured_by=["Order"]),
            False,
        ),
        # opposite: XOR de presença.
        (
            lambda p: make_reference(p, opposite=make_reference(p, name="opp")),
            lambda p: make_reference(p),
            False,
        ),
        (
            lambda p: make_reference(p, opposite=make_reference(p, name="opp")),
            lambda p: make_reference(p, opposite=make_reference(p, name="opp")),
            True,
        ),
        (
            lambda p: make_reference(p, opposite=make_reference(p, name="opp", upper=1)),
            lambda p: make_reference(p, opposite=make_reference(p, name="opp", upper=-1)),
            False,
        ),
    ],
)
def test_compare_reference(
    metamodel: EPackage,
    build1: Callable[[EPackage], EObject],
    build2: Callable[[EPackage], EObject],
    expected: bool,
) -> None:
    assert compare_reference(build1(metamodel), build2(metamodel)) is expected


@pytest.mark.unit
def test_compare_reference_only_compares_first_featured_by(metamodel: EPackage) -> None:
    """``isFeaturedBy`` casa tamanhos, mas só compara o container do índice ``[0]``.

    Espelha ``CompareReference`` literalmente: os elementos ``1..n`` são
    ignorados. Não é engano — é o comportamento do oráculo, e o harness tem de
    reproduzi-lo para não ser mais rígido que ele.
    """
    reference1 = make_reference(metamodel, featured_by=["Order", "Address"])
    reference2 = make_reference(metamodel, featured_by=["Order", "Payment"])

    assert compare_reference(reference1, reference2) is True


@pytest.mark.unit
def test_compare_reference_guards(metamodel: EPackage) -> None:
    """`checkNulls` é ``or``: dois ``None`` reprovam."""
    reference = make_reference(metamodel)

    assert compare_reference(None, reference) is False
    assert compare_reference(None, None) is False
    assert compare_reference(reference, reference) is True


# Os dois lados são carregados do MESMO arquivo em DUAS chamadas de `load_model`:
# grafos estruturalmente iguais e fisicamente distintos. Reusar o mesmo EObject
# faria toda comparação profunda dar curto-circuito nos atalhos de identidade
# (`f1 is f2`, `v1 == v2`) — o teste passaria sem comparar nada.
NORTHWIND_XMI = Path("resources/mongodb/model_northwind.xmi")
MOVIES_XMI = Path("resources/neo4j/movies_min.xmi")


def load_pair(xmi_path: Path, pkg: EPackage) -> tuple[EObject, EObject]:
    """Carregar o mesmo XMI duas vezes, como dois modelos independentes.

    Parameters
    ----------
    xmi_path : Path
        XMI de referência a carregar nos dois lados.
    pkg : EPackage
        Metamodelo U-Schema já carregado.

    Returns
    -------
    tuple of EObject
        ``(schema1, schema2)`` — iguais em estrutura, distintos em identidade.
    """
    return load_model(xmi_path, pkg), load_model(xmi_path, pkg)


@pytest.mark.unit
def test_compare_identical_models_are_equivalent(metamodel: EPackage) -> None:
    """A == A: o northwind é equivalente a uma cópia sua — nenhuma divergência **fatal**.

    Reflexividade do harness. É a execução mais completa do driver: percorre
    `start_comparison` -> `_compare_entities` -> `_compare_schema_type_variations`
    -> toda a árvore de comparadores, sobre 19 entidades reais.

    **Não-fatais são esperadas aqui, e o assert não as proíbe** (ao contrário do
    teste do movies, que exige relatório vazio). O northwind tem variações
    estruturalmente indistinguíveis dentro da mesma entidade — o colapso
    `Long`/`Integer`/`Number` do `ComparePrimitiveType` as torna iguais —, e o
    casamento guloso do C7 pareia a primeira que encontra, não a "certa". Daí
    saírem divergências `COUNT` (contagens trocadas entre variações gêmeas) e
    `VARIATION` órfã. São o C7 aparecendo no relatório, exatamente como projetado:
    visível, não fatal. Ver `bugs_originais.md`.

    Este teste também é o que trava a guarda de tipo ausente do `compare_plist`:
    sem ela, o `PList` de array vazio de `privileges` (entidade `Employees`) cai no
    `checkNulls` do `compare_datatype`, derruba a variação inteira, e o veredito vem
    `False` — o modelo deixaria de ser equivalente a si mesmo. O original tem essa
    guarda; portá-la é o que mantém o comparador reflexivo.
    """
    schema1, schema2 = load_pair(NORTHWIND_XMI, metamodel)

    result = compare(schema1, schema2)

    assert result.equivalent is True


@pytest.mark.unit
def test_compare_identical_models_with_relationships(metamodel: EPackage) -> None:
    """A == A no modelo Neo4j: é o único que exercita `_compare_relationships`.

    O northwind é MongoDB e não tem `RelationshipType` — sem este teste, o laço
    de relationships fica com cobertura zero.

    Aqui o relatório tem de vir **vazio**, não só "sem fatais": o movies é pequeno
    e não dispara o C7. É a assimetria com o teste do northwind, e é deliberada —
    se um dia sair divergência não-fatal daqui, é regressão, não ruído conhecido.
    """
    schema1, schema2 = load_pair(MOVIES_XMI, metamodel)

    result = compare(schema1, schema2)

    assert result.equivalent is True
    assert result.divergences == []


def rename_schema(schema: EObject) -> None:
    """Renomear o schema (o Java compara este nome CRU, case-sensitive)."""
    schema.name = "OutroSchema"


def drop_entity(schema: EObject) -> None:
    """Remover a primeira entidade: dispara contagem E entidade não-casada."""
    schema.entities.remove(schema.entities[0])


def rename_entity_far(schema: EObject) -> None:
    """Renomear uma entidade para longe do alcance do fuzzy (nada em comum)."""
    schema.entities[0].name = "Zzzzzzzzzz"


def rename_entity_near(schema: EObject) -> None:
    """Despluralizar uma entidade: cai no fuzzy do `compare_names`, variações intactas.

    ``Employees`` -> ``Employee``: substring bidirecional, 1 letra de diferença
    (< ``_MAX_DIFF_LETTERS_TO_MATCH``). O Java loga isto como *hit*, não warning —
    daí a divergência ser **não-fatal**.
    """
    entity = next(e for e in schema.entities if e.name == "Employees")
    entity.name = "Employee"


def flip_root(schema: EObject) -> None:
    """Inverter o `root` da primeira entidade (o Java nunca compara `root`)."""
    schema.entities[0].root = not schema.entities[0].root


def drop_variation(schema: EObject) -> None:
    """Remover uma variação de uma entidade que tenha mais de uma."""
    entity = next(e for e in schema.entities if len(e.variations) > 1)
    entity.variations.remove(entity.variations[0])


def bump_count(schema: EObject) -> None:
    """Alterar o `count` de uma variação.

    Escolhe uma entidade de variação **única** de propósito: com mais de uma, o
    casamento guloso (C7) já embaralha os `count` sozinho e a divergência não
    seria atribuível à mutação.
    """
    entity = next(e for e in schema.entities if len(e.variations) == 1)
    entity.variations[0].count += 100


def drop_relationship(schema: EObject) -> None:
    """Remover um `RelationshipType` (só o modelo Neo4j tem)."""
    schema.relationships.remove(schema.relationships[0])


def rename_relationship(schema: EObject) -> None:
    """Renomear um `RelationshipType`: aqui **não** há fallback fuzzy — é fatal."""
    schema.relationships[0].name = "Zzzzzzzzzz"


# Cada caso: (nome, xmi, mutação aplicada a schema2, categoria esperada, é fatal?).
# A mutação é um Callable[[EObject], None] — recebe schema2 e o adultera in-place.
_MUTATIONS: list[tuple[str, Path, Callable[[EObject], None], DivergenceCategory, bool]] = [
    ("schema_renamed", NORTHWIND_XMI, rename_schema, DivergenceCategory.SCHEMA_NAME, True),
    ("entity_dropped", NORTHWIND_XMI, drop_entity, DivergenceCategory.ENTITY, True),
    ("entity_renamed_far", NORTHWIND_XMI, rename_entity_far, DivergenceCategory.ENTITY, True),
    ("entity_renamed_near", NORTHWIND_XMI, rename_entity_near, DivergenceCategory.ENTITY, False),
    ("root_flipped", NORTHWIND_XMI, flip_root, DivergenceCategory.ROOT, False),
    ("variation_dropped", NORTHWIND_XMI, drop_variation, DivergenceCategory.VARIATION, True),
    ("count_bumped", NORTHWIND_XMI, bump_count, DivergenceCategory.COUNT, False),
    ("relationship_dropped", MOVIES_XMI, drop_relationship, DivergenceCategory.RELATIONSHIP, True),
    (
        "relationship_renamed",
        MOVIES_XMI,
        rename_relationship,
        DivergenceCategory.RELATIONSHIP,
        True,
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("xmi_path", "mutate", "expected_category", "expected_fatal"),
    [pytest.param(xmi, fn, cat, fatal, id=name) for name, xmi, fn, cat, fatal in _MUTATIONS],
)
def test_compare_detects_mutation(
    metamodel: EPackage,
    xmi_path: Path,
    mutate: Callable[[EObject], None],
    expected_category: DivergenceCategory,
    expected_fatal: bool,
) -> None:
    """Cada adulteração de `schema2` produz uma divergência da categoria esperada.

    O harness detecta divergência injetada (gate da Fase 0). Duas asserções, e a
    segunda é a que importa: a categoria **e** a fatalidade têm de bater. Um caso
    não-fatal (`ROOT`, `COUNT`, fuzzy-hit de entidade) aparece no relatório **sem**
    reprovar o veredito — é a política "fiel + reporte extra". Se o teste só olhasse
    `equivalent`, essa metade ficaria sem cobertura, e o harness poderia estar mais
    rígido que o oráculo sem ninguém notar.
    """
    schema1, schema2 = load_pair(xmi_path, metamodel)
    mutate(schema2)

    result = compare(schema1, schema2)

    assert result.equivalent is not expected_fatal
    assert any(d.category is expected_category for d in result.divergences)
