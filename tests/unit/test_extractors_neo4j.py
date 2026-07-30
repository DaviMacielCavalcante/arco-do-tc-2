"""Extrator Neo4j — porte de TypeUtils/IdArchetypeMapping/ReduceByIdArchetype/SplitMapping.

Cada teste trava um comportamento citado por linha do original; ver
``src/uschema/extractors/neo4j.py`` pras citações completas e a derivação dos
dois achados do round-trip de JSON (``Long``→``"integer"``, lista
heterogênea/vazia→``"string[]"``, nunca ``"long"``/``"any[]"``).

Usa fakes de ``Node``/``Relationship`` (não os reais de ``neo4j.graph``) pelo
mesmo motivo de ``test_extractors_mongo.py`` usar um ``Database`` falso: o
real exige um ``Graph`` e resolve ``.type`` pela **classe** do objeto (uma
peculiaridade do driver, não do nosso código) — os fakes só implementam a
superfície que o módulo usa (``.labels``/``.keys()``/``__getitem__``/
``.element_id`` em ``Node``; ``.type``/``.keys()``/``__getitem__`` em
``Relationship``).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from uschema.extractors.neo4j import (
    build_archetype_counts,
    extract_archetype_counts,
    extract_database_archetype_counts,
    get_type_name,
    node_archetype,
    obtain_type,
    reduce_archetypes_by_node,
)

pytestmark = pytest.mark.unit


class _FakeNode:
    def __init__(self, element_id: str, labels: list[str], properties: dict[str, Any]) -> None:
        self.element_id = element_id
        self.labels = labels
        self._properties = properties

    def keys(self) -> Iterator[str]:
        return iter(self._properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self._properties[key]


class _FakeRelationship:
    def __init__(self, rel_type: str, properties: dict[str, Any]) -> None:
        self.type = rel_type
        self._properties = properties

    def keys(self) -> Iterator[str]:
        return iter(self._properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self._properties[key]


# --- obtain_type: escalares (TypeUtils.java:34-48) --------------------------


def test_obtain_type_bool_vira_sentinela_false() -> None:
    assert obtain_type(True) is False
    assert obtain_type(False) is False


def test_obtain_type_string_vira_sentinela_s() -> None:
    assert obtain_type("qualquer coisa") == "s"


def test_obtain_type_float_vira_sentinela_zero_ponto_zero() -> None:
    assert obtain_type(3.14) == 0.0


def test_obtain_type_int_vira_sentinela_zero() -> None:
    assert obtain_type(42) == 0


def test_obtain_type_tipo_nao_mapeado_vira_string_null() -> None:
    # TypeUtils.java:47 — Duration/Point/Date/ByteArray etc. caem aqui.
    # Comportamento observável do oráculo: não lança, vira sentinela textual.
    class _Duration:
        pass

    assert obtain_type(_Duration()) == "null"
    assert isinstance(obtain_type(_Duration()), str)


# --- obtain_type: ordem de despacho bool -> int (armadilha Python) ----------


def test_obtain_type_bool_nao_e_confundido_com_int() -> None:
    resultado = obtain_type(True)

    assert type(resultado) is bool
    assert resultado is False


def test_obtain_type_int_puro_continua_int() -> None:
    resultado = obtain_type(7)

    assert type(resultado) is int
    assert not isinstance(resultado, bool)


# --- obtain_type: listas (TypeUtils.java:51-59) ------------------------------


def test_obtain_type_lista_homogenea_de_int() -> None:
    assert obtain_type([1, 2, 3]) == [0]


def test_obtain_type_lista_homogenea_de_string() -> None:
    assert obtain_type(["a", "b"]) == ["s"]


def test_obtain_type_lista_homogenea_de_bool() -> None:
    assert obtain_type([True, False]) == [False]


def test_obtain_type_lista_vazia_vira_any() -> None:
    # TypeUtils.java:58 — 0 tipos distintos, mesmo ramo da lista heterogênea.
    assert obtain_type([]) == ["any"]


def test_obtain_type_lista_heterogenea_vira_any() -> None:
    assert obtain_type([1, "x"]) == ["any"]


def test_obtain_type_lista_heterogenea_bool_int_nao_colapsa() -> None:
    # False == 0 em Python — sem cuidado, [True, 5] pareceria homogêneo.
    # Java: Boolean.equals(Long) é sempre false, então isso é ["any"] lá
    # também; a dedup por (type, valor) preserva isso aqui.
    assert obtain_type([True, 5]) == ["any"]


def test_obtain_type_lista_aninhada_e_recursiva() -> None:
    assert obtain_type([[1, 2], [3, 4]]) == [[0]]


def test_obtain_type_lista_aninhada_tres_niveis_nao_quebra_dedup() -> None:
    """Regressão: a chave de deduplicação de `_list_sentinel` precisa ser
    hasheável em qualquer profundidade.

    Neo4j não permite lista de lista como propriedade — este caso é só
    defensivo —, mas uma versão anterior convertia só o nível externo pra
    tupla (`tuple(sentinel)`), deixando uma lista aninhada de nível 3+
    destravada dentro da chave e estourando `TypeError: unhashable type`
    no primeiro `dict.setdefault`, mesmo com um único elemento.
    """
    assert obtain_type([[[1]]]) == [[[0]]]


# --- get_type_name: escalares (TypeUtils.java:62-90) -------------------------


def test_get_type_name_boolean() -> None:
    assert get_type_name(False) == "boolean"


def test_get_type_name_string() -> None:
    assert get_type_name("s") == "string"


def test_get_type_name_double() -> None:
    assert get_type_name(0.0) == "double"


def test_get_type_name_integer_nao_long() -> None:
    """O achado central do módulo: sentinela `int` sempre vira "integer".

    Derivação completa no docstring do módulo — o `Long` sentinela (`0L` no
    Java) sempre serializa pro texto "0", que `org.json` (`20180130`,
    verificado no fonte de `stringToValue`) sempre relê como `Integer`, nunca
    `Long`. O ramo "long" de `geetSimpleType` é código morto no caminho real.
    """
    assert get_type_name(0) == "integer"


# --- get_type_name: listas ----------------------------------------------------


def test_get_type_name_lista_de_integer() -> None:
    assert get_type_name([0]) == "integer[]"


def test_get_type_name_lista_de_string() -> None:
    assert get_type_name(["s"]) == "string[]"


def test_get_type_name_lista_de_boolean() -> None:
    assert get_type_name([False]) == "boolean[]"


def test_get_type_name_marcador_any_vira_string_array_nao_any_array() -> None:
    """O segundo achado: lista heterogênea/vazia vira "string[]", nunca "any[]".

    O marcador `"any"` que `obtain_type` produz é, ele mesmo, uma `str` — e
    `get_type_name` despacha por *tipo* Python, não por conteúdo, então
    qualquer string (mesmo a que se chama "any") vira "string".
    """
    assert get_type_name(["any"]) == "string[]"
    assert get_type_name(obtain_type([])) == "string[]"
    assert get_type_name(obtain_type([1, "x"])) == "string[]"


# --- node_archetype (IdArchetypeMapping.java:57-68) --------------------------


def test_node_archetype_ordena_os_proprios_labels() -> None:
    node = _FakeNode("n1", ["Zebra", "Ana"], {})

    arquetipo = node_archetype(node, None, None)

    assert arquetipo["labels"] == ["Ana", "Zebra"]


def test_node_archetype_sem_relacionamento_tem_references_vazio() -> None:
    node = _FakeNode("n1", ["Person"], {"nome": "x"})

    arquetipo = node_archetype(node, None, None)

    assert arquetipo == {
        "labels": ["Person"],
        "entity": "node",
        "properties": {"nome": "s"},
        "references": [],
    }


def test_node_archetype_com_relacionamento_tem_uma_referencia() -> None:
    node = _FakeNode("n1", ["Person"], {})
    rel = _FakeRelationship("FRIEND", {"since": 2020})

    arquetipo = node_archetype(node, rel, ["Person"])

    assert arquetipo["references"] == [
        {
            "type": "FRIEND",
            "refsTo": ["Person"],
            "entity": "relationship",
            "properties": {"since": 0},
        }
    ]


def test_node_archetype_refs_to_nao_e_ordenado() -> None:
    """Assimetria do oráculo: `refsTo` usa a ordem crua de `labels(m)`.

    Diferente dos labels próprios do nó (sempre ordenados) — ver "Uma
    assimetria do oráculo a preservar" no docstring do módulo.
    """
    node = _FakeNode("n1", ["Person"], {})
    rel = _FakeRelationship("KNOWS", {})

    arquetipo = node_archetype(node, rel, ["Zebra", "Ana"])

    assert arquetipo["references"][0]["refsTo"] == ["Zebra", "Ana"]


# --- reduce_archetypes_by_node (ReduceByIdArchetype.java:16-23) -------------


def test_reduce_funde_linhas_do_mesmo_no() -> None:
    node = _FakeNode("n1", ["Person"], {})
    rel_a = _FakeRelationship("FRIEND", {})
    rel_b = _FakeRelationship("LIKES", {})

    rows = [
        ("n1", node_archetype(node, rel_a, ["Person"])),
        ("n1", node_archetype(node, rel_b, ["Movie"])),
    ]

    [merged] = reduce_archetypes_by_node(rows).values()

    tipos = {ref["type"] for ref in merged["references"]}
    assert tipos == {"FRIEND", "LIKES"}


def test_reduce_deduplica_referencias_estruturalmente_iguais() -> None:
    node = _FakeNode("n1", ["Person"], {})
    rel1 = _FakeRelationship("FRIEND", {})
    rel2 = _FakeRelationship("FRIEND", {})  # mesmo tipo/propriedades/refsTo

    rows = [
        ("n1", node_archetype(node, rel1, ["Person"])),
        ("n1", node_archetype(node, rel2, ["Person"])),
    ]

    [merged] = reduce_archetypes_by_node(rows).values()

    assert len(merged["references"]) == 1


def test_reduce_no_sem_relacionamento_fica_com_references_vazio() -> None:
    node = _FakeNode("n1", ["Person"], {})

    rows = [("n1", node_archetype(node, None, None))]

    [merged] = reduce_archetypes_by_node(rows).values()

    assert merged["references"] == []


def test_reduce_nos_diferentes_ficam_em_entradas_separadas() -> None:
    n1 = _FakeNode("n1", ["Person"], {})
    n2 = _FakeNode("n2", ["Person"], {})

    rows = [("n1", node_archetype(n1, None, None)), ("n2", node_archetype(n2, None, None))]

    assert set(reduce_archetypes_by_node(rows).keys()) == {"n1", "n2"}


# --- build_archetype_counts (SplitMapping.java:30-41 + countByValue) --------


def test_build_archetype_counts_conta_nos_de_mesmo_esqueleto() -> None:
    n1 = _FakeNode("n1", ["Person"], {"nome": "a"})
    n2 = _FakeNode("n2", ["Person"], {"nome": "b"})
    merged = reduce_archetypes_by_node(
        [("n1", node_archetype(n1, None, None)), ("n2", node_archetype(n2, None, None))]
    )

    linhas = build_archetype_counts(merged)

    assert len(linhas) == 1
    assert linhas[0]["count"] == 2
    assert linhas[0]["archetype"]["entity"] == "node"


def test_build_archetype_counts_relacionamento_conta_nos_de_origem_nao_arestas_brutas() -> None:
    """O ponto sutil da fase: count de `RelationshipType` = fontes distintas.

    `n1` tem **2** relacionamentos FRIEND (mesmo tipo/props/alvo) — mas eles
    deduplicam em `reduce_archetypes_by_node` antes de chegar aqui, então
    contam como **1** ocorrência da referência isolada, não 2.
    """
    n1 = _FakeNode("n1", ["Person"], {})
    rel_a = _FakeRelationship("FRIEND", {})
    rel_b = _FakeRelationship("FRIEND", {})
    merged = reduce_archetypes_by_node(
        [
            ("n1", node_archetype(n1, rel_a, ["Person"])),
            ("n1", node_archetype(n1, rel_b, ["Person"])),
        ]
    )

    linhas = build_archetype_counts(merged)
    relacionamentos = [linha for linha in linhas if linha["archetype"]["entity"] == "relationship"]

    assert len(relacionamentos) == 1
    assert relacionamentos[0]["count"] == 1


def test_build_archetype_counts_relacionamento_soma_entre_nos_de_origem_distintos() -> None:
    n1 = _FakeNode("n1", ["Person"], {})
    n2 = _FakeNode("n2", ["Person"], {})
    rel1 = _FakeRelationship("FRIEND", {})
    rel2 = _FakeRelationship("FRIEND", {})
    merged = reduce_archetypes_by_node(
        [("n1", node_archetype(n1, rel1, ["Person"])), ("n2", node_archetype(n2, rel2, ["Person"]))]
    )

    linhas = build_archetype_counts(merged)
    relacionamentos = [linha for linha in linhas if linha["archetype"]["entity"] == "relationship"]

    assert len(relacionamentos) == 1
    assert relacionamentos[0]["count"] == 2


def test_build_archetype_counts_vazio_devolve_lista_vazia() -> None:
    assert build_archetype_counts({}) == []


# --- extract_archetype_counts (pipeline sem I/O) -----------------------------


def test_extract_archetype_counts_ponta_a_ponta() -> None:
    n1 = _FakeNode("n1", ["Person"], {"nome": "a"})
    n2 = _FakeNode("n2", ["Person"], {"nome": "b"})
    rel = _FakeRelationship("FRIEND", {})

    rows: list[tuple[Any, Any, Any]] = [
        (n1, rel, ["Person"]),
        (n2, None, None),
    ]

    linhas = extract_archetype_counts(rows)

    nos = [linha for linha in linhas if linha["archetype"]["entity"] == "node"]
    relacionamentos = [linha for linha in linhas if linha["archetype"]["entity"] == "relationship"]
    assert len(nos) == 2  # esqueletos diferentes: com e sem referência
    assert len(relacionamentos) == 1
    assert relacionamentos[0]["count"] == 1


# --- extract_database_archetype_counts: validação (SparkProcess.java:43) ----


def test_extract_database_archetype_counts_rejeita_sampling_rate_invalido() -> None:
    with pytest.raises(ValueError, match="Sampling rate"):
        extract_database_archetype_counts(driver=None, sampling_rate=0.0)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Sampling rate"):
        extract_database_archetype_counts(driver=None, sampling_rate=1.5)  # type: ignore[arg-type]


# --- conexão: driver falso ----------------------------------------------------


class _FakeEagerResult:
    def __init__(self, records: list[Any]) -> None:
        self.records = records


class _FakeDriver:
    """Driver falso: devolve respostas pré-fabricadas por query, e grava as
    queries recebidas — o suficiente para testar `_distinct_label_combinations`/
    `_read_label_combination` sem um Neo4j de verdade.
    """

    def __init__(self, responses: Mapping[str, _FakeEagerResult]) -> None:
        self._responses = responses
        self.queries: list[str] = []

    def execute_query(self, query: str, **kwargs: Any) -> _FakeEagerResult:
        self.queries.append(query)
        for prefix, response in self._responses.items():
            if query.startswith(prefix):
                return response
        raise AssertionError(f"query inesperada: {query!r}")


def test_extract_database_archetype_counts_usa_driver_falso() -> None:
    n1 = _FakeNode("n1", ["Person"], {"nome": "a"})
    rel = _FakeRelationship("FRIEND", {})

    driver = _FakeDriver(
        {
            "MATCH (n) RETURN DISTINCT labels(n)": _FakeEagerResult([[["Person"]]]),
            "MATCH (n:`Person`)": _FakeEagerResult([[n1, rel, ["Person"]]]),
        }
    )

    linhas = extract_database_archetype_counts(driver)  # type: ignore[arg-type]

    assert any(linha["archetype"]["entity"] == "relationship" for linha in linhas)
    assert any(":`Person`" in q for q in driver.queries)
