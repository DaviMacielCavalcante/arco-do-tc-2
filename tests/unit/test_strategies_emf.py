"""Estratégias de nível EMF/PyEcore (Fase 1.3b).

Porte de ``DefaultFeatureAnalyzer``, ``DefaultReferenceMatcher``/
``DefaultReferenceMatcherCreator``, ``DefaultStructuralVariationSorter``/
``NullStructuralVariationSorter`` e ``DefaultOptionalTagger``/
``NullOptionalTagger`` (``doc2uschema/process/util/*.java``). Cada teste
trava um comportamento citado por linha do original; ver
``src/uschema/inference/strategies.py`` pras citações completas.

Os ``EObject`` de ``StructuralVariation``/``Attribute``/``EntityType`` são
montados via API reflexiva do PyEcore (não há classe estática pra importar —
ver ``src/uschema/metamodel/registry.py``), no mesmo estilo de
``test_equivalence.py``.
"""

from __future__ import annotations

import pytest
from pyecore.ecore import EObject, EPackage

from uschema.inference.strategies import (
    NullOptionalTagger,
    OptionalTagger,
    ReferenceMatcher,
    create_reference_matcher,
    null_sort_structural_variations,
    set_optional_properties,
    sort_structural_variations,
)
from uschema.intermediate.metadata import ObjectMetadata
from uschema.intermediate.raw import BooleanSC, ObjectSC, StringSC
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit


@pytest.fixture
def metamodel() -> EPackage:
    """Metamodelo U-Schema carregado (para instanciar EObjects de teste)."""
    return load_metamodel()


def make_attribute(pkg: EPackage, name: str, *, optional: bool = False) -> EObject:
    attribute = pkg.getEClassifier("Attribute")(name=name)
    attribute.type = pkg.getEClassifier("PrimitiveType")(name="String")
    attribute.optional = optional
    return attribute


def make_variation(
    pkg: EPackage,
    structural_features: list[EObject] | None = None,
    *,
    variation_id: int = 1,
    count: int = 0,
    first_timestamp: int = 0,
    last_timestamp: int = 0,
) -> EObject:
    variation = pkg.getEClassifier("StructuralVariation")(variationId=variation_id)
    variation.count = count
    variation.firstTimestamp = first_timestamp
    variation.lastTimestamp = last_timestamp
    for feature in structural_features or []:
        variation.features.append(feature)
        variation.structuralFeatures.append(feature)
    return variation


def make_entity(pkg: EPackage, name: str, *, root: bool = True) -> EObject:
    entity = pkg.getEClassifier("EntityType")(name=name)
    entity.root = root
    return entity


# --- set_optional_properties (DefaultFeatureAnalyzer.java:20-40) -----------


def test_feature_analyzer_campo_ausente_em_uma_variacao_fica_opcional(
    metamodel: EPackage,
) -> None:
    # `:30-32` — "id" está em v1 e v2, "extra" só em v2 -> "extra" é opcional.
    id1 = make_attribute(metamodel, "id")
    id2 = make_attribute(metamodel, "id")
    extra = make_attribute(metamodel, "extra")
    v1 = make_variation(metamodel, [id1])
    v2 = make_variation(metamodel, [id2, extra])

    set_optional_properties([v1, v2])

    assert id1.optional is False
    assert id2.optional is False
    assert extra.optional is True


def test_feature_analyzer_campo_presente_em_todas_as_variacoes_nao_e_opcional(
    metamodel: EPackage,
) -> None:
    v1 = make_variation(metamodel, [make_attribute(metamodel, "id")])
    v2 = make_variation(metamodel, [make_attribute(metamodel, "id")])

    set_optional_properties([v1, v2])

    for variation in (v1, v2):
        [feature] = variation.structuralFeatures
        assert feature.optional is False


def test_feature_analyzer_uma_so_variacao_nada_e_opcional(metamodel: EPackage) -> None:
    v1 = make_variation(metamodel, [make_attribute(metamodel, "id")])

    set_optional_properties([v1])

    [feature] = v1.structuralFeatures
    assert feature.optional is False


# --- ReferenceMatcher (DefaultReferenceMatcher.java:17-64) -----------------


def test_reference_matcher_prefixo_com_afixo_id(metamodel: EPackage) -> None:
    # ":42-43" — prefixo, chave antes do afixo: "customerId" casa "customer".
    entity = make_entity(metamodel, "Customer")
    matcher = ReferenceMatcher([("customer", entity)])

    assert matcher.maybe_match("customerId") is entity


def test_reference_matcher_afixo_antes_da_chave(metamodel: EPackage) -> None:
    # ":44-45" — "hasCustomer" casa "customer" com afixo "has" antes da chave.
    entity = make_entity(metamodel, "Customer")
    matcher = ReferenceMatcher([("customer", entity)])

    assert matcher.maybe_match("hasCustomer") is entity


def test_reference_matcher_e_case_insensitive(metamodel: EPackage) -> None:
    entity = make_entity(metamodel, "Customer")
    matcher = ReferenceMatcher([("customer", entity)])

    assert matcher.maybe_match("CUSTOMERID") is entity


def test_reference_matcher_unlikely_word_count_nunca_casa(metamodel: EPackage) -> None:
    # `_REFERENCE_UNLIKELY_WORDS` — "itemCount" contém "count", rejeitado antes
    # de qualquer regex.
    entity = make_entity(metamodel, "Item")
    matcher = ReferenceMatcher([("item", entity)])

    assert matcher.maybe_match("itemCount") is None


def test_reference_matcher_sem_padrao_correspondente_devolve_none(
    metamodel: EPackage,
) -> None:
    entity = make_entity(metamodel, "Customer")
    matcher = ReferenceMatcher([("customer", entity)])

    assert matcher.maybe_match("totalPrice") is None


def test_create_reference_matcher_ignora_entidades_nao_raiz(metamodel: EPackage) -> None:
    root_entity = make_entity(metamodel, "Customer", root=True)
    inner_entity = make_entity(metamodel, "Address", root=False)

    matcher = create_reference_matcher([root_entity, inner_entity])

    assert matcher.maybe_match("customerId") is root_entity
    assert matcher.maybe_match("addressId") is None


def test_create_reference_matcher_indexa_singular_e_plural(metamodel: EPackage) -> None:
    # `:24-27` — três variantes por entidade raiz: nome, plural, singular.
    entity = make_entity(metamodel, "orders", root=True)

    matcher = create_reference_matcher([entity])

    assert matcher.maybe_match("orderId") is entity
    assert matcher.maybe_match("ordersId") is entity


# --- StructuralVariationSorter (DefaultStructuralVariationSorter.java) -----


def test_sort_por_first_timestamp_quando_algum_e_nao_zero(metamodel: EPackage) -> None:
    v_tarde = make_variation(metamodel, first_timestamp=200, variation_id=1)
    v_cedo = make_variation(metamodel, first_timestamp=100, variation_id=2)
    variations = [v_tarde, v_cedo]

    sort_structural_variations(variations)

    assert variations == [v_cedo, v_tarde]
    assert [v.variationId for v in variations] == [1, 2], "renumerado a partir de 1"


def test_sort_cai_pra_last_timestamp_se_first_e_todo_zero(metamodel: EPackage) -> None:
    v_tarde = make_variation(metamodel, last_timestamp=200)
    v_cedo = make_variation(metamodel, last_timestamp=100)
    variations = [v_tarde, v_cedo]

    sort_structural_variations(variations)

    assert variations == [v_cedo, v_tarde]


def test_sort_m3_ramo_de_count_nao_ordena_so_renumera(metamodel: EPackage) -> None:
    """M3 (``bugs_originais.md``): ``sortByCount`` é um no-op no original.

    Timestamps todos zero, mas count não-zero: o Java entraria no ramo
    `sortByCount`, cujo `ECollections.sort` está comentado — só
    `reOrderVariationIds` roda. O porte replica: a ordem de **entrada**
    sobrevive intacta, só `variationId` é renumerado.
    """
    v_a = make_variation(metamodel, count=5, variation_id=9)
    v_b = make_variation(metamodel, count=1, variation_id=8)
    variations = [v_a, v_b]

    sort_structural_variations(variations)

    assert variations == [v_a, v_b], "M3: não ordenou por count, ordem de entrada preservada"
    assert [v.variationId for v in variations] == [1, 2]


def test_sort_property_number_quando_tudo_e_zero(metamodel: EPackage) -> None:
    v_uma_prop = make_variation(metamodel, [make_attribute(metamodel, "a")])
    v_duas_props = make_variation(
        metamodel, [make_attribute(metamodel, "a"), make_attribute(metamodel, "b")]
    )
    variations = [v_duas_props, v_uma_prop]

    sort_structural_variations(variations)

    assert variations == [v_uma_prop, v_duas_props]


def test_null_sort_structural_variations_nao_faz_nada(metamodel: EPackage) -> None:
    v_tarde = make_variation(metamodel, first_timestamp=200, variation_id=7)
    v_cedo = make_variation(metamodel, first_timestamp=100, variation_id=3)
    variations = [v_tarde, v_cedo]

    null_sort_structural_variations(variations)

    assert variations == [v_tarde, v_cedo]
    assert [v.variationId for v in variations] == [7, 3]


# --- OptionalTagger (DefaultOptionalTagger.java:11-67) — código morto, -----
# --- portado por completude ("fiel e completo"), ver docstring da classe. --


def _pair_schema(name: str, **fields: object) -> ObjectSC:
    obj = ObjectSC(entity_name=name, meta=ObjectMetadata())
    for key, value in fields.items():
        obj.add((key, value))  # type: ignore[arg-type]
    return obj


def test_optional_tagger_uma_so_variacao_nada_e_opcional() -> None:
    tagger = OptionalTagger()
    schema = _pair_schema("Address", street=StringSC())
    tagger.put("Address", schema)

    tagger.calc_optionality()

    [pair] = schema.inners
    assert tagger.is_optional("Address", pair) is False


def test_optional_tagger_campo_presente_em_todas_nao_e_opcional() -> None:
    tagger = OptionalTagger()
    s1 = _pair_schema("Address", street=StringSC())
    s2 = _pair_schema("Address", street=StringSC())
    tagger.put("Address", s1)
    tagger.put("Address", s2)

    tagger.calc_optionality()

    assert tagger.is_optional("Address", s1.inners[0]) is False


def test_optional_tagger_campo_so_em_uma_variacao_e_opcional() -> None:
    tagger = OptionalTagger()
    s1 = _pair_schema("Address", street=StringSC())
    s2 = _pair_schema("Address", street=StringSC(), complement=BooleanSC())
    tagger.put("Address", s1)
    tagger.put("Address", s2)

    tagger.calc_optionality()

    fields2 = dict(s2.inners)
    complement_pair = ("complement", fields2["complement"])
    assert tagger.is_optional("Address", complement_pair) is True


def test_null_optional_tagger_nunca_marca_nada_como_opcional() -> None:
    tagger = NullOptionalTagger()
    schema = _pair_schema("Address", street=StringSC())
    tagger.put("Address", schema)
    tagger.calc_optionality()

    assert tagger.is_optional("Address", schema.inners[0]) is False
