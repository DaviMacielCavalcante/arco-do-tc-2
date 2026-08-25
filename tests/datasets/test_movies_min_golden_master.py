"""Golden-master do dataset **User Profile / Neo4j** (Fase 2.2) — camada de construção.

Roda :func:`~uschema.extractors.neo4j_model.build_uschema_from_archetypes`
sobre um conjunto de arquétipos e compara o ``USchema`` resultante com os
quatro XMIs-oráculo do Neo4j (``resources/neo4j/movies_min.xmi``,
``up_medium.xmi``, ``up_large.xmi``, ``up_larger.xmi``) pelo harness de
equivalência da Fase 0.3 (:func:`~uschema.validation.equivalence.compare`).

É o **gate de integração** da 2.2 no caso da camada de construção — exercita,
de uma vez: herança multi-label (não presente aqui, ver ressalva abaixo),
dedup/merge de `Reference` (`WATCHED` compartilhado entre 3 variações de
`User`), opcionalidade cross-variação (`surname`/`address_postcode`
presentes só em 3 das 5 variações de `User`) e fusão de variações
estruturalmente idênticas (nenhuma ocorre aqui — as 5 variações de `User`
são todas distintas na estrutura, então nenhuma é fundida).

Proveniência da fixture (honestidade sobre o que isto valida)
------------------------------------------------------------
Os quatro XMIs são o **mesmo** dataset "User Profile" em quatro tamanhos
(confirmado: mesmos nomes de entidade/relacionamento/atributo nos quatro,
só o ``count`` e o nome do schema mudam). As linhas de arquétipo abaixo
foram **reconstruídas lendo a própria estrutura do XMI-oráculo**
(`movies_min.xmi`) — quais atributos existem em cada variação de `User`,
quais são opcionais, quais referências cada uma tem — **não** extraídas de
um Neo4j real (a Fase 2 não tem um Neo4j populado disponível neste
ambiente; o dataset "userprofile" original também não está versionado no
repo Java, só o `map.js`/`reduce.js` de um pipeline MongoDB antigo e
não-relacionado). Os `count` usados por variação são os do próprio
XMI-oráculo (o `compare()` os ignora no veredito, mas usá-los faz o teste
bater **sem nenhuma divergência**, não só sem divergência fatal).

Isto valida a camada de **construção** (`neo4j_model.py`) contra os quatro
oráculos reais — não a camada de **extração** (`neo4j.py`, já testada à
parte contra fakes em `tests/unit/test_extractors_neo4j.py`) nem o
encadeamento ponta a ponta contra um Neo4j de verdade. Também **não**
confirma a assimetria de ordenação de labels catalogada em `neo4j.py`
(`node_archetype` ordena os labels próprios; `_relationship_archetype` não
ordena `refsTo`) — nenhum nó destes datasets tem múltiplos labels, então o
caso que exercitaria essa assimetria nunca aparece aqui. Ver
`todolist_fase2.md` §2.2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pyecore.ecore import EPackage

from uschema.extractors.neo4j_model import build_uschema_from_archetypes
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model
from uschema.validation.equivalence import compare

pytestmark = pytest.mark.unit

_RESOURCES_DIR = Path(__file__).resolve().parents[2] / "resources" / "neo4j"

_FULL_PROPS = {
    "address_street": "s",
    "surname": "s",
    "name": "s",
    "address_postcode": "s",
    "id": 0,
    "email": "s",
    "address_city": "s",
    "address_number": 0,
}
_REDUCED_PROPS = {
    "address_street": "s",
    "name": "s",
    "id": 0,
    "email": "s",
    "address_city": "s",
    "address_number": 0,
}
_MOVIE_PROPS = {"year": 0, "genre": "s", "id": 0, "title": "s"}
_WATCHED_PROPS = {"stars": 0}
_FAVORITE_PROPS: dict[str, Any] = {}

# Contagens por (arquivo, variação) — lidas direto de cada XMI-oráculo.
# Ordem: User.1 (WATCHED), User.2 (WATCHED+FAVORITE), User.3 (sem refs),
# User.4 (reduzido+WATCHED), User.5 (reduzido, sem refs), Movie.1, WATCHED.1,
# FAVORITE.1.
_COUNTS_BY_DATASET = {
    "movies_min": (6393, 36106, 7501, 42592, 7408, 50000, 85091, 36106),
    "up_medium": (12741, 72339, 14920, 85172, 14828, 100000, 170252, 72339),
    "up_large": (25546, 144562, 29892, 169749, 30251, 200000, 339857, 144562),
    "up_larger": (50733, 289205, 60062, 339953, 60047, 400000, 679891, 289205),
}


@pytest.fixture(scope="module")
def pkg() -> EPackage:
    return load_metamodel()


def _node(
    labels: list[str],
    properties: dict[str, Any],
    count: int,
    references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    archetype: dict[str, Any] = {"entity": "node", "labels": labels, "properties": properties}
    if references is not None:
        archetype["references"] = references
    return {"archetype": archetype, "count": count}


def _rel_archetype(rel_type: str, properties: dict[str, Any], refs_to: list[str]) -> dict[str, Any]:
    return {"type": rel_type, "properties": properties, "refsTo": refs_to}


def _rows_for(
    user1: int,
    user2: int,
    user3: int,
    user4: int,
    user5: int,
    movie1: int,
    watched: int,
    favorite: int,
) -> list[dict[str, Any]]:
    watched_ref = _rel_archetype("WATCHED", _WATCHED_PROPS, ["Movie"])
    favorite_ref = _rel_archetype("FAVORITE", _FAVORITE_PROPS, ["Movie"])

    return [
        _node(["User"], _FULL_PROPS, user1, references=[watched_ref]),
        _node(["User"], _FULL_PROPS, user2, references=[watched_ref, favorite_ref]),
        _node(["User"], _FULL_PROPS, user3),
        _node(["User"], _REDUCED_PROPS, user4, references=[watched_ref]),
        _node(["User"], _REDUCED_PROPS, user5),
        _node(["Movie"], _MOVIE_PROPS, movie1),
        {
            "archetype": {
                "entity": "relationship",
                "type": "WATCHED",
                "properties": _WATCHED_PROPS,
                "refsTo": ["Movie"],
            },
            "count": watched,
        },
        {
            "archetype": {
                "entity": "relationship",
                "type": "FAVORITE",
                "properties": _FAVORITE_PROPS,
                "refsTo": ["Movie"],
            },
            "count": favorite,
        },
    ]


@pytest.mark.parametrize("dataset", sorted(_COUNTS_BY_DATASET))
def test_reproduz_xmi_oraculo_sem_divergencia(pkg: EPackage, dataset: str) -> None:
    counts = _COUNTS_BY_DATASET[dataset]
    port = build_uschema_from_archetypes(pkg, dataset, _rows_for(*counts))
    oracle = load_model(_RESOURCES_DIR / f"{dataset}.xmi", pkg)

    result = compare(oracle, port)

    assert result.equivalent, [f"{d.category}: {d.message}" for d in result.divergences]
    assert result.divergences == []


def test_movies_min_estrutura_esperada(pkg: EPackage) -> None:
    # Contraparte legível: as 5 variações de User que o oráculo tem, e por quê.
    counts = _COUNTS_BY_DATASET["movies_min"]
    port = build_uschema_from_archetypes(pkg, "movies_min", _rows_for(*counts))

    by_name = {e.name: e for e in port.entities}
    assert set(by_name) == {"User", "Movie"}
    assert len(by_name["User"].variations) == 5
    assert len(by_name["Movie"].variations) == 1

    # surname/address_postcode só existem nas variações "full profile"
    # (1, 2, 3) -- ausentes (não "opcionais": ausentes) nas "reduced" (4, 5).
    full_profile_variations = [
        v for v in by_name["User"].variations if v.count in (6393, 36106, 7501)
    ]
    assert len(full_profile_variations) == 3
    for variation in full_profile_variations:
        surname = next(f for f in variation.features if f.name == "surname")
        postcode = next(f for f in variation.features if f.name == "address_postcode")
        assert surname.optional is True
        assert postcode.optional is True

    reduced_variations = [v for v in by_name["User"].variations if v.count in (42592, 7408)]
    assert len(reduced_variations) == 2
    for variation in reduced_variations:
        names = {f.name for f in variation.features}
        assert "surname" not in names
        assert "address_postcode" not in names

    # WATCHED: uma única StructuralVariation de RelationshipType compartilhada
    # pelas 3 variações de User que a referenciam (1, 2 e 4).
    watched_type = next(r for r in port.relationships if r.name == "WATCHED")
    assert len(watched_type.variations) == 1
