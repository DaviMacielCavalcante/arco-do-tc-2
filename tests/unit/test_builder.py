"""Testes do ``USchemaModelBuilder`` (Fase 1.4).

Porte de ``USchemaModelBuilder.build`` + ``fillEV`` (``USchemaModelBuilder.java``,
commit pinado ``0f8f58c``). Cada teste trava um comportamento citado por linha
do original; ver ``src/uschema/inference/builder.py`` pras citações completas.

Como a fronteira PyEcore é ``Any`` (a lib não distribui ``py.typed``), **cada
acesso a campo de ``EObject`` tem de ser exercitado ao menos uma vez** — foi
assim que os typos ``entitties``/``Attribue``/``upperBouund`` só apareceram em
execução, nunca no ``mypy``. Estes testes são essa rede.

Os componentes raw (``ObjectSC``/``ArraySC``/folhas) são montados à mão; os
``EObject`` do modelo saem do metamodelo reflexivo (mesma abordagem de
``test_strategies_emf.py``).
"""

from __future__ import annotations

import pytest
from pyecore.ecore import EPackage

from uschema.inference.builder import USchemaModelBuilder, _primitive_type_name
from uschema.inference.strategies import create_reference_matcher
from uschema.intermediate.metadata import ObjectMetadata
from uschema.intermediate.raw import (
    ArraySC,
    BooleanSC,
    NullSC,
    NumberSC,
    ObjectIdSC,
    ObjectSC,
    SchemaComponent,
    StringSC,
)
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit


@pytest.fixture
def pkg() -> EPackage:
    """Metamodelo U-Schema carregado (para instanciar EObjects)."""
    return load_metamodel()


@pytest.fixture
def builder(pkg: EPackage) -> USchemaModelBuilder:
    """Um builder novo sobre o metamodelo carregado."""
    return USchemaModelBuilder(pkg)


def _obj(
    inners: list[tuple[str, SchemaComponent]],
    *,
    is_root: bool = False,
    count: int = 0,
    first: int = 0,
    last: int = 0,
    entity_name: str | None = None,
) -> ObjectSC:
    """Montar um ``ObjectSC`` com meta, como o ``infer`` produz."""
    return ObjectSC(
        inners=inners,
        is_root=is_root,
        meta=ObjectMetadata(count=count, first_timestamp=first, last_timestamp=last),
        entity_name=entity_name,
    )


def _array(elements: list[SchemaComponent]) -> ArraySC:
    """Montar um ``ArraySC`` via ``add_all`` (mantém homogeneidade coerente)."""
    array = ArraySC()
    array.add_all(elements)
    return array


# --- _primitive_type_name (:344-362) ---------------------------------------


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        (BooleanSC(), "Boolean"),
        (NumberSC(), "Number"),
        (StringSC(), "String"),
        (ObjectIdSC(), "ObjectId"),
        (NullSC(), "Null"),
        (ObjectSC(inners=[]), ""),  # `:361` — objeto cai no fallback vazio.
        (ArraySC(), ""),  # idem array.
    ],
)
def test_primitive_type_name(component: SchemaComponent, expected: str) -> None:
    assert _primitive_type_name(component) == expected


# --- _feature_from_primitive (:388-396) ------------------------------------


def test_feature_from_primitive(builder: USchemaModelBuilder) -> None:
    attribute = builder._feature_from_primitive("freight", "Number")

    assert attribute.eClass.name == "Attribute"
    assert attribute.name == "freight"
    assert attribute.type.eClass.name == "PrimitiveType"
    assert attribute.type.name == "Number"


# --- _recursive_type (:330-342) --------------------------------------------


def test_recursive_type_folha_vira_primitive_type(builder: USchemaModelBuilder) -> None:
    result = builder._recursive_type(StringSC())

    assert result.eClass.name == "PrimitiveType"
    assert result.name == "String"


def test_recursive_type_array_desce_recursivo(builder: USchemaModelBuilder) -> None:
    # `:332-333` — array de array de escalares: a recursão mútua com
    # `_plist_or_ptuple_for_array` fecha.
    inner_array = _array([NumberSC(), NumberSC()])
    result = builder._recursive_type(inner_array)

    assert result.eClass.name == "PList"
    assert result.elementType.name == "Number"


# --- _plist_or_ptuple_for_array (:307-328) ---------------------------------


def test_plist_vazio_sem_element_type(builder: USchemaModelBuilder) -> None:
    # `:310-311` — array vazio -> PList sem elementType (obrigatório no .ecore,
    # mas o PyEcore não exige; o oráculo produz assim). Caminho do #7.
    result = builder._plist_or_ptuple_for_array(ArraySC())

    assert result.eClass.name == "PList"
    assert result.elementType is None


def test_plist_homogeneo(builder: USchemaModelBuilder) -> None:
    # `:313-317`.
    result = builder._plist_or_ptuple_for_array(_array([StringSC(), StringSC()]))

    assert result.eClass.name == "PList"
    assert result.elementType.name == "String"


def test_ptuple_heterogeneo_preserva_ordem(builder: USchemaModelBuilder) -> None:
    # `:320-327` — array heterogêneo -> PTuple com um elemento por inner, na
    # ordem. (O bug do `return` dentro do laço colapsaria pra um só.)
    result = builder._plist_or_ptuple_for_array(_array([StringSC(), NumberSC()]))

    assert result.eClass.name == "PTuple"
    assert [e.name for e in result.elements] == ["String", "Number"]


# --- _feature_from_object (:235-247) ---------------------------------------


def test_feature_from_object_aggregate_1_1(builder: USchemaModelBuilder) -> None:
    inner = _obj([("company", StringSC())])
    variation = builder._create("StructuralVariation")
    builder._m_structural_variations[inner] = variation

    aggregate = builder._feature_from_object("shipVia", inner)

    assert aggregate.eClass.name == "Aggregate"
    assert aggregate.name == "shipVia"
    assert aggregate.lowerBound == 1
    assert aggregate.upperBound == 1
    assert list(aggregate.aggregates) == [variation]


# --- _feature_from_array (:249-305) -----------------------------------------


def test_feature_from_array_vazio_nao_estoura_bug_7(builder: USchemaModelBuilder) -> None:
    """**Bug #7** — array vazio não pode indexar ``inners[0]`` (``:255-256``).

    O guarda ``size() == 0`` tem de ser avaliado antes de tocar o primeiro
    inner. Corrigido por construção; este teste trava que não regride pro
    ``IndexError`` do original (patch ``0007``). É o dado ``privileges`` do
    northwind.
    """
    feature = builder._feature_from_array("privileges", ArraySC())

    assert feature.eClass.name == "Attribute"
    assert feature.name == "privileges"
    assert feature.type.eClass.name == "PList"
    assert feature.type.elementType is None


def test_feature_from_array_homogeneo_de_escalares(builder: USchemaModelBuilder) -> None:
    # `:256-260` — homogêneo não-objeto -> Attribute com PList.
    feature = builder._feature_from_array("tags", _array([StringSC(), StringSC()]))

    assert feature.eClass.name == "Attribute"
    assert feature.type.eClass.name == "PList"
    assert feature.type.elementType.name == "String"


def test_feature_from_array_homogeneo_de_objetos(builder: USchemaModelBuilder) -> None:
    # `:262-274` — homogêneo de objetos -> Aggregate 0..-1 apontando pra
    # variação do inner.
    inner = _obj([("qty", NumberSC())])
    array = _array([inner])
    variation = builder._create("StructuralVariation")
    builder._m_structural_variations[inner] = variation

    feature = builder._feature_from_array("details", array)

    assert feature.eClass.name == "Aggregate"
    assert feature.lowerBound == 0
    assert feature.upperBound == -1
    assert list(feature.aggregates) == [variation]


def test_feature_from_array_heterogeneo_de_escalares(builder: USchemaModelBuilder) -> None:
    # `:280-303` — heterogêneo cujo 1º inner não está indexado -> Attribute
    # com PTuple. `.get()` devolve None e manda pro ramo do PList/PTuple.
    feature = builder._feature_from_array("mixed", _array([StringSC(), NumberSC()]))

    assert feature.eClass.name == "Attribute"
    assert feature.type.eClass.name == "PTuple"
    assert [e.name for e in feature.type.elements] == ["String", "Number"]


def test_feature_from_array_heterogeneo_de_objetos(builder: USchemaModelBuilder) -> None:
    # `:283-295` — heterogêneo de objetos -> Aggregate com a variação de CADA
    # inner, na ordem.
    obj_a = _obj([("a", NumberSC())])
    obj_b = _obj([("b", StringSC())])
    array = ArraySC()
    array.add_all([obj_a, obj_b])  # dois objetos distintos -> heterogêneo
    var_a = builder._create("StructuralVariation")
    var_b = builder._create("StructuralVariation")
    builder._m_structural_variations[obj_a] = var_a
    builder._m_structural_variations[obj_b] = var_b

    feature = builder._feature_from_array("items", array)

    assert feature.eClass.name == "Aggregate"
    assert list(feature.aggregates) == [var_a, var_b]


# --- _maybe_reference (:360-386) -------------------------------------------


def test_maybe_reference_sem_casamento_devolve_none(builder: USchemaModelBuilder) -> None:
    builder._ref_matcher = create_reference_matcher([])
    attribute = builder._feature_from_primitive("total", "Number")

    assert builder._maybe_reference("total", attribute) is None


def test_maybe_reference_escalar_1_1(builder: USchemaModelBuilder) -> None:
    # `:378-379` — referência a partir de Attribute escalar -> 1..1.
    customer = builder._create("EntityType")
    customer.name = "Customer"
    customer.root = True
    builder._ref_matcher = create_reference_matcher([customer])
    attribute = builder._feature_from_primitive("customerId", "String")

    reference = builder._maybe_reference("customer", attribute)

    assert reference is not None
    assert reference.eClass.name == "Reference"
    assert reference.refsTo is customer
    assert reference.lowerBound == 1
    assert reference.upperBound == 1
    assert list(reference.attributes) == [attribute]


def test_maybe_reference_plist_0_n(builder: USchemaModelBuilder) -> None:
    # `:373-374` — se o Attribute referenciado é PList -> 0..-1.
    customer = builder._create("EntityType")
    customer.name = "Customer"
    customer.root = True
    builder._ref_matcher = create_reference_matcher([customer])
    attribute = builder._feature_from_array("customerIds", _array([StringSC()]))

    reference = builder._maybe_reference("customer", attribute)

    assert reference is not None
    assert reference.lowerBound == 0
    assert reference.upperBound == -1


# --- _fill_ev (:176-213) ---------------------------------------------------


def test_fill_ev_escalar_vira_attribute(builder: USchemaModelBuilder) -> None:
    builder._ref_matcher = create_reference_matcher([])
    ev = builder._create("StructuralVariation")
    schema = _obj([("freight", NumberSC())])

    builder._fill_ev("Orders", schema, ev)

    [feature] = list(ev.structuralFeatures)
    assert feature.eClass.name == "Attribute"
    assert feature.name == "freight"
    assert feature in ev.features


def test_fill_ev_id_ganha_key(builder: USchemaModelBuilder) -> None:
    # `:201-207` — campo chamado exatamente "_id" e escalar -> ganha um Key,
    # que vai pras logicalFeatures.
    builder._ref_matcher = create_reference_matcher([])
    ev = builder._create("StructuralVariation")
    schema = _obj([("_id", ObjectIdSC())])

    builder._fill_ev("Orders", schema, ev)

    [attribute] = list(ev.structuralFeatures)
    assert attribute.name == "_id"
    assert attribute.key is not None
    logical_kinds = [f.eClass.name for f in ev.logicalFeatures]
    assert "Key" in logical_kinds


def test_fill_ev_referencia_vai_pras_logical_features(builder: USchemaModelBuilder) -> None:
    # `:194-199` — Attribute que casa referência: a Reference entra em
    # features E logicalFeatures.
    customer = builder._create("EntityType")
    customer.name = "Customer"
    customer.root = True
    builder._ref_matcher = create_reference_matcher([customer])
    ev = builder._create("StructuralVariation")
    schema = _obj([("customerId", StringSC())])

    builder._fill_ev("Orders", schema, ev)

    logical_kinds = [f.eClass.name for f in ev.logicalFeatures]
    assert "Reference" in logical_kinds


# --- build (:89-174) — ponta a ponta ---------------------------------------


def test_build_cria_uschema_com_nome(builder: USchemaModelBuilder) -> None:
    model = builder.build("mintest", {})

    assert model.eClass.name == "USchema"
    assert model.name == "mintest"
    assert len(model.entities) == 0


def test_build_entity_root_se_alguma_variacao_e_raiz(builder: USchemaModelBuilder) -> None:
    # `:105` — root = any(variação.is_root).
    raw: dict[str, list[SchemaComponent]] = {
        "Orders": [_obj([("freight", NumberSC())], is_root=True, count=3)],
        "Detail": [_obj([("qty", NumberSC())], is_root=False, count=3)],
    }
    model = builder.build("m", raw)

    by_name = {e.name: e for e in model.entities}
    assert by_name["Orders"].root is True
    assert by_name["Detail"].root is False


def test_build_numera_variation_id_e_propaga_meta(builder: USchemaModelBuilder) -> None:
    # `:117-121` — variationId de 1 em diante; count/timestamps vindos do meta.
    raw: dict[str, list[SchemaComponent]] = {
        "Orders": [
            _obj([("a", NumberSC())], is_root=True, count=5, first=100, last=200),
            _obj([("b", StringSC())], is_root=True, count=2, first=50, last=80),
        ],
    }
    model = builder.build("m", raw)

    [entity] = list(model.entities)
    variations = list(entity.variations)
    assert {v.variationId for v in variations} == {1, 2}
    counts = {v.count for v in variations}
    assert counts == {5, 2}


def test_build_array_vazio_ponta_a_ponta_nao_estoura(builder: USchemaModelBuilder) -> None:
    # #7 no fluxo real: um campo array vazio (privileges) não pode derrubar o
    # build. Nenhum JUnit cobre isso.
    raw: dict[str, list[SchemaComponent]] = {
        "Orders": [_obj([("privileges", ArraySC())], is_root=True, count=1)]
    }

    model = builder.build("m", raw)

    [entity] = list(model.entities)
    [variation] = list(entity.variations)
    [feature] = list(variation.structuralFeatures)
    assert feature.name == "privileges"
    assert feature.type.eClass.name == "PList"


def test_build_objeto_aninhado_vira_aggregate(builder: USchemaModelBuilder) -> None:
    # O objeto interno (já promovido a entidade pela 1.2) vira Aggregate na
    # variação-raiz que o contém.
    inner = _obj([("company", StringSC())], entity_name="Shipvia", count=1)
    raw: dict[str, list[SchemaComponent]] = {
        "Orders": [_obj([("shipVia", inner)], is_root=True, count=1)],
        "Shipvia": [inner],
    }
    model = builder.build("m", raw)

    orders = next(e for e in model.entities if e.name == "Orders")
    [variation] = list(orders.variations)
    [feature] = list(variation.structuralFeatures)
    assert feature.eClass.name == "Aggregate"
    assert feature.name == "shipVia"
    # aponta pra alguma variação de Shipvia
    shipvia = next(e for e in model.entities if e.name == "Shipvia")
    assert next(iter(feature.aggregates)) in list(shipvia.variations)


def test_build_reordena_a_colecao_emf_nao_so_o_id(builder: USchemaModelBuilder) -> None:
    """A ordem das variações na coleção EMF tem de refletir o sort, não só o
    ``variationId``.

    O ``var_sorter`` (1.3b) opera sobre ``list``; ``entity.variations`` é um
    ``EOrderedSet`` sem ``.sort()``. O builder faz snapshot → sort → reescreve
    a ordem na coleção (ver a nota no ``build``). Aqui: a 2ª variação tem
    ``firstTimestamp`` menor, então deve vir primeiro **na coleção**.
    """
    raw: dict[str, list[SchemaComponent]] = {
        "Orders": [
            _obj([("a", NumberSC())], is_root=True, count=1, first=200),
            _obj([("b", StringSC())], is_root=True, count=1, first=100),
        ],
    }
    model = builder.build("m", raw)

    [entity] = list(model.entities)
    ordered = list(entity.variations)
    # ordenado por firstTimestamp asc: o de first=100 vem primeiro, e o
    # variationId renumerado acompanha a posição.
    assert ordered[0].firstTimestamp == 100
    assert ordered[0].variationId == 1
    assert ordered[1].firstTimestamp == 200
    assert ordered[1].variationId == 2
