"""Testes do núcleo de construção do modelo Neo4j (``extractors/neo4j_model.py``).

Complementa ``test_extractors_neo4j.py`` (camada de extração). Aqui: a
camada de construção — dado arquétipos+contagem já extraídos, o ``USchema``
resultante bate com o que ``USchemaBuilder``/``StructuralVariationBuilder``/
``AttributeOptionalsChecker``/``IgnoreSimilarReferenceBoundsProcessor``
produziriam.
"""

from __future__ import annotations

from typing import Any

import pytest
from pyecore.ecore import EObject, EPackage

from uschema.extractors.neo4j_model import (
    _compare_references,
    _process_optionals,
    _properties_key,
    _string_type_for_optionality,
    _type_representation,
    build_uschema_from_archetypes,
)
from uschema.metamodel.registry import load_metamodel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def pkg() -> EPackage:
    return load_metamodel()


def _node(
    labels: list[str],
    properties: dict[str, Any],
    references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    archetype: dict[str, Any] = {"entity": "node", "labels": labels, "properties": properties}
    if references is not None:
        archetype["references"] = references
    return archetype


def _rel(rel_type: str, properties: dict[str, Any], refs_to: list[str]) -> dict[str, Any]:
    return {"type": rel_type, "properties": properties, "refsTo": refs_to}


# --- fim-a-fim: build_uschema_from_archetypes --------------------------------


def test_grafo_minimo_usuario_assiste_filme(pkg: EPackage) -> None:
    # Um nó User com uma referência WATCHED->Movie, um nó Movie solto.
    rows = [
        {
            "archetype": _node(
                ["User"],
                {"name": "Ana"},
                references=[_rel("WATCHED", {"rating": 5}, ["Movie"])],
            ),
            "count": 3,
        },
        {
            "archetype": _node(["Movie"], {"title": "Matrix"}),
            "count": 2,
        },
    ]

    schema = build_uschema_from_archetypes(pkg, "movies_min", rows)

    assert schema.name == "movies_min"
    entity_names = {e.name for e in schema.entities}
    assert entity_names == {"User", "Movie"}
    assert {r.name for r in schema.relationships} == {"WATCHED"}

    user = next(e for e in schema.entities if e.name == "User")
    assert user.root is True
    assert len(user.variations) == 1
    user_variation = user.variations[0]
    assert user_variation.count == 3
    assert user_variation.variationId == 1

    attrs = [f for f in user_variation.features if f.eClass.name == "Attribute"]
    assert {a.name for a in attrs} == {"name"}

    refs = [f for f in user_variation.features if f.eClass.name == "Reference"]
    assert len(refs) == 1
    watched = refs[0]
    assert watched.name == "WATCHED"
    assert watched.refsTo.name == "Movie"
    assert watched.lowerBound == 1
    assert watched.upperBound == 1

    movie = next(e for e in schema.entities if e.name == "Movie")
    assert movie.variations[0].count == 2


def test_no_multi_label_ganha_pais_por_label(pkg: EPackage) -> None:
    rows = [
        {"archetype": _node(["Person", "Actor"], {"name": "Neo"}), "count": 1},
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)

    combined = next(e for e in schema.entities if e.name == "Person_AND_Actor")
    parent_names = {p.name for p in combined.parents}
    assert parent_names == {"Person", "Actor"}
    # Person e Actor viram EntityType próprios (via get_or_create_entity_type),
    # mas sem variação própria (nenhum arquétipo os produziu isolados).
    assert {e.name for e in schema.entities} == {"Person_AND_Actor", "Person", "Actor"}


def test_referencia_repetida_na_mesma_variacao_upper_bound_vira_ilimitado(pkg: EPackage) -> None:
    # Um User que assistiu dois filmes diferentes na mesma variação de nó:
    # duas linhas "relationship" com o mesmo type/propriedades mas destinos
    # diferentes viram a MESMA StructuralVariation de RelationshipType
    # (chave é só o properties.toString()); a segunda ocorrência entra pelo
    # ramo "senão" de _get_or_create_reference -> upperBound = -1.
    rows = [
        {
            "archetype": _node(
                ["User"],
                {"name": "Ana"},
                references=[
                    _rel("WATCHED", {"rating": 5}, ["Movie"]),
                    _rel("WATCHED", {"rating": 5}, ["Movie"]),
                ],
            ),
            "count": 1,
        },
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    user = next(e for e in schema.entities if e.name == "User")
    refs = [f for f in user.variations[0].features if f.eClass.name == "Reference"]
    assert len(refs) == 1
    assert refs[0].upperBound == -1
    assert refs[0].lowerBound == 1


def test_propriedades_de_relacionamento_com_ordem_diferente_agrupam_igual(pkg: EPackage) -> None:
    # properties.toString() é order-independent (ver docstring de
    # _get_or_create_variation) -> mesma StructuralVariation mesmo com
    # dicts Python construídos em ordem de chaves diferente.
    rows = [
        {
            "archetype": _node(["A"], {}, references=[_rel("REL", {"x": 1, "y": 2}, ["B"])]),
            "count": 1,
        },
        {
            "archetype": _node(["A"], {}, references=[_rel("REL", {"y": 2, "x": 1}, ["B"])]),
            "count": 1,
        },
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    rel_type = next(r for r in schema.relationships if r.name == "REL")
    assert len(rel_type.variations) == 1


# --- _process_optionals -------------------------------------------------------


def test_atributo_ausente_em_uma_variacao_fica_opcional(pkg: EPackage) -> None:
    rows = [
        {"archetype": _node(["User"], {"name": "Ana", "age": 30}), "count": 1},
        {"archetype": _node(["User"], {"name": "Bea"}), "count": 1},
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    user = next(e for e in schema.entities if e.name == "User")
    assert len(user.variations) == 2

    for variation in user.variations:
        for feature in variation.features:
            if feature.name == "name":
                assert feature.optional is False
            elif feature.name == "age":
                assert feature.optional is True


def test_atributo_presente_em_todas_variacoes_nao_fica_opcional(pkg: EPackage) -> None:
    rows = [
        {"archetype": _node(["User"], {"name": "Ana"}), "count": 1},
        {"archetype": _node(["User"], {"name": "Bea"}), "count": 1},
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    user = next(e for e in schema.entities if e.name == "User")
    for variation in user.variations:
        for feature in variation.features:
            assert feature.optional is False


def test_atributo_array_colide_na_chave_de_opcionalidade_independente_do_tipo(
    pkg: EPackage,
) -> None:
    # Achado documentado no módulo: getStringType não reconhece PList, então
    # "tags:string[]" e "tags:integer[]" produzem a MESMA chave ("tags:") ->
    # contam como o mesmo atributo pro MapCounter, e como aparece em toda
    # variação (2 de 2), NENHUMA fica opcional -- mesmo sendo, na prática,
    # dois tipos diferentes.
    rows = [
        {"archetype": _node(["User"], {"tags": ["a", "b"]}), "count": 1},
        {"archetype": _node(["User"], {"tags": [1, 2]}), "count": 1},
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    user = next(e for e in schema.entities if e.name == "User")
    for variation in user.variations:
        tags_attr = next(f for f in variation.features if f.name == "tags")
        assert tags_attr.optional is False


def test_entidade_sem_variacoes_nao_quebra(pkg: EPackage) -> None:
    schema = pkg.getEClassifier("USchema")()
    schema.name = "vazio"
    _process_optionals(schema)  # não deve levantar exceção


# --- _join_variations_ignoring_bounds -----------------------------------------


def test_variacoes_com_mesma_estrutura_mas_bounds_diferentes_sao_fundidas(pkg: EPackage) -> None:
    # Duas variações de User, cada uma com uma referência WATCHED->Movie, mas
    # uma com a referência repetida (upperBound -1) e outra não (upperBound
    # 1) -- generateSimilarVariationsMap ignora bounds na chave (usa só
    # nome+refsTo), então caem no mesmo grupo e são fundidas: contagem
    # somada, uma sobrevive, upperBound vira o mínimo.
    rows = [
        {
            "archetype": _node(
                ["User"], {"name": "Ana"}, references=[_rel("WATCHED", {}, ["Movie"])]
            ),
            "count": 2,
        },
        {
            "archetype": _node(
                ["User"],
                {"name": "Bea"},
                references=[_rel("WATCHED", {}, ["Movie"]), _rel("WATCHED", {}, ["Movie"])],
            ),
            "count": 5,
        },
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    user = next(e for e in schema.entities if e.name == "User")

    assert len(user.variations) == 1
    survivor = user.variations[0]
    assert survivor.count == 7
    assert survivor.variationId == 1

    refs = [f for f in survivor.features if f.eClass.name == "Reference"]
    assert len(refs) == 1
    # min(1, -1) == -1 aqui (um lado era ilimitado) -- não prova o caso "min
    # não é sempre ilimitado"; ver teste seguinte pra isso.
    assert refs[0].upperBound == -1


def test_min_de_dois_upper_bounds_finitos_nao_vira_sempre_ilimitado(pkg: EPackage) -> None:
    # IgnoreSimilarReferenceBoundsProcessor: o nome sugere "sempre
    # ilimitado", mas compareReferences faz min(upperBound1, upperBound2).
    # Regressão direta contra esse mal-entendido de nome.
    def make_ref(name: str, target_name: str, upper_bound: int) -> EObject:
        ref = pkg.getEClassifier("Reference")()
        ref.name = name
        entity = pkg.getEClassifier("EntityType")()
        entity.name = target_name
        ref.refsTo = entity
        ref.upperBound = upper_bound
        variation = pkg.getEClassifier("StructuralVariation")()
        variation.variationId = 1
        ref.isFeaturedBy.append(variation)
        return ref

    r1 = make_ref("REL", "Target", 3)
    r2 = make_ref("REL", "Target", 7)
    _compare_references(r1, r2)

    assert r1.upperBound == 3
    assert r2.upperBound == 3


def test_variacoes_com_features_diferentes_nao_sao_fundidas(pkg: EPackage) -> None:
    rows = [
        {"archetype": _node(["User"], {"name": "Ana"}), "count": 1},
        {
            "archetype": _node(
                ["User"], {"name": "Bea"}, references=[_rel("WATCHED", {}, ["Movie"])]
            ),
            "count": 1,
        },
    ]
    schema = build_uschema_from_archetypes(pkg, "s", rows)
    user = next(e for e in schema.entities if e.name == "User")
    assert len(user.variations) == 2
    assert {v.variationId for v in user.variations} == {1, 2}


# --- _string_type_for_optionality vs. _type_representation --------------------
# As duas funções de "tipo como string" divergem de propósito -- ver docstring
# do módulo.


def test_string_type_for_optionality_nao_reconhece_plist(pkg: EPackage) -> None:
    primitive = pkg.getEClassifier("PrimitiveType")()
    primitive.name = "string"
    plist = pkg.getEClassifier("PList")()
    plist.elementType = primitive

    assert _string_type_for_optionality(plist) == ""


def test_string_type_for_optionality_reconhece_primitive_type(pkg: EPackage) -> None:
    primitive = pkg.getEClassifier("PrimitiveType")()
    primitive.name = "integer"

    assert _string_type_for_optionality(primitive) == "integer"


def test_type_representation_reconhece_plist_recursivo(pkg: EPackage) -> None:
    primitive = pkg.getEClassifier("PrimitiveType")()
    primitive.name = "integer"
    plist = pkg.getEClassifier("PList")()
    plist.elementType = primitive

    assert _type_representation(plist) == "integer[]"


def test_type_representation_reconhece_pset_e_pmap(pkg: EPackage) -> None:
    primitive = pkg.getEClassifier("PrimitiveType")()
    primitive.name = "string"
    pset = pkg.getEClassifier("PSet")()
    pset.elementType = primitive
    assert _type_representation(pset) == "string{}"

    key_type = pkg.getEClassifier("PrimitiveType")()
    key_type.name = "string"
    value_type = pkg.getEClassifier("PrimitiveType")()
    value_type.name = "integer"
    pmap = pkg.getEClassifier("PMap")()
    pmap.keyType = key_type
    pmap.valueType = value_type
    assert _type_representation(pmap) == "{string:integer}"


# --- _properties_key -----------------------------------------------------------


def test_properties_key_ordem_nao_importa() -> None:
    assert _properties_key({"a": 1, "b": 2}) == _properties_key({"b": 2, "a": 1})


def test_properties_key_valores_diferentes_geram_chaves_diferentes() -> None:
    assert _properties_key({"a": 1}) != _properties_key({"a": 2})
