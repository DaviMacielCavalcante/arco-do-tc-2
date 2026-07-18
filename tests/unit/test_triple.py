"""Contrato da tripla (Fase 1.0) — classificação de valores, validação e conversão."""

import pytest

from uschema.extractors.triple import (
    OBJECT_ID_SENTINEL,
    JsonKind,
    SchemaTriple,
    classify,
    triples_from_rows,
    validate_rows,
)

pytestmark = pytest.mark.unit


# --- classify: a cascata de SchemaInference.java:150-171 --------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, JsonKind.OBJECT),
        ({"a": 1}, JsonKind.OBJECT),
        ([], JsonKind.ARRAY),
        ([1, 2], JsonKind.ARRAY),
        (True, JsonKind.BOOLEAN),
        (False, JsonKind.BOOLEAN),
        (0, JsonKind.NUMBER),
        (0.0, JsonKind.NUMBER),
        (-17, JsonKind.NUMBER),
        (None, JsonKind.NULL),
        ("", JsonKind.TEXTUAL),
        ("s", JsonKind.TEXTUAL),
        ("string", JsonKind.TEXTUAL),
        ("oid", JsonKind.OBJECT_ID),
    ],
)
def test_classify(value: object, expected: JsonKind) -> None:
    assert classify(value) is expected


def test_bool_nao_e_numero() -> None:
    # `bool` é subclasse de `int` no Python; no Java os ramos são disjuntos.
    # Sem o teste de bool antes do de número, `True` viraria NumberSC.
    assert classify(True) is JsonKind.BOOLEAN
    assert classify(False) is JsonKind.BOOLEAN


def test_object_id_e_so_a_sentinela_exata() -> None:
    # JacksonElement.java:93 / GsonElement.java:120 — igualdade com "oid",
    # não "contém" nem case-insensitive.
    assert classify(OBJECT_ID_SENTINEL) is JsonKind.OBJECT_ID
    for quase in ("OID", "oid ", " oid", "objectid", "$oid", "oids"):
        assert classify(quase) is JsonKind.TEXTUAL


def test_extended_json_do_spark_e_objeto_nao_object_id() -> None:
    """A divergência deliberada: no caminho do oráculo o ObjectId vira agregado.

    `Document.toJson()` serializa a sentinela do Spark como `{"$oid": "..."}`,
    que casa em `isObject()` antes de chegar ao ramo do ObjectId — daí a
    entidade `_id` com atributo `$oid` em `resources/mongodb/model_mintest.xmi`.
    Reconhecer isso como ObjectId "consertaria" o porte para longe do oráculo.
    """
    extended = {"$oid": "000000000000000000000000"}
    assert classify(extended) is JsonKind.OBJECT
    assert classify(extended["$oid"]) is JsonKind.TEXTUAL


def test_classify_rejeita_valor_nao_json() -> None:
    # Desvio deliberado: o Java devolve null (assert desligado) e estoura longe.
    with pytest.raises(TypeError, match="não representável em JSON"):
        classify(object())


# --- validate_rows: SchemaInference.java:78-90 ------------------------------


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "schema": {"_type": "orders", "_id": "oid"},
        "count": 3,
        "firstTimestamp": 1781470615,
        "lastTimestamp": 1781470620,
    }
    row.update(overrides)
    return row


def test_lista_vazia_e_valida() -> None:
    assert validate_rows([]) is True


def test_sequence_vazia_nao_lista_e_valida() -> None:
    # A assinatura aceita Sequence: `() == []` é False, mas as duas são vazias.
    assert validate_rows(()) is True


def test_linha_bem_formada() -> None:
    assert validate_rows([_row()]) is True


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"schema": "s"}, id="schema-nao-objeto"),
        pytest.param({"schema": []}, id="schema-array"),
        pytest.param({"count": "3"}, id="count-string"),
        pytest.param({"firstTimestamp": None}, id="first-nulo"),
        pytest.param({"lastTimestamp": {}}, id="last-objeto"),
    ],
)
def test_linha_com_tipo_errado(overrides: dict[str, object]) -> None:
    assert validate_rows([_row(**overrides)]) is False


@pytest.mark.parametrize("faltante", ["schema", "count", "firstTimestamp", "lastTimestamp"])
def test_chave_ausente_reprova_sem_estourar(faltante: str) -> None:
    # `Optional.ofNullable` do Java absorve a chave ausente: mesmo resultado
    # que tipo errado (False), nunca uma exceção.
    row = _row()
    del row[faltante]
    assert validate_rows([row]) is False


def test_valida_so_a_primeira_linha() -> None:
    """Fiel ao comentário do autor na :80 — o resto é presumido correto."""
    rows: list[dict[str, object]] = [_row(), {"lixo": True}, {"count": "não é número"}]
    assert validate_rows(rows) is True


def test_primeira_linha_ruim_reprova_apesar_do_resto_bom() -> None:
    assert validate_rows([{"lixo": True}, _row(), _row()]) is False


# --- triples_from_rows ------------------------------------------------------


def test_converte_camel_case_para_snake_case() -> None:
    (triple,) = triples_from_rows([_row()])
    assert triple == SchemaTriple(
        schema={"_type": "orders", "_id": "oid"},
        count=3,
        first_timestamp=1781470615,
        last_timestamp=1781470620,
    )


def test_preserva_a_ordem_de_entrada() -> None:
    # A ordem decide qual variação é a primeira de cada entidade (:204-211).
    rows = [_row(count=n) for n in (5, 1, 9)]
    assert [t.count for t in triples_from_rows(rows)] == [5, 1, 9]


def test_lista_vazia_vira_lista_vazia() -> None:
    assert triples_from_rows([]) == []


def test_entrada_invalida_levanta_value_error() -> None:
    with pytest.raises(ValueError, match=r"JSON rows do not follow the expected schema"):
        triples_from_rows([_row(count="3")])


def test_numeros_sao_coagidos_para_int() -> None:
    # O Java lê com asLong() (:135); um 1.0 do JSON não pode vazar como float.
    (triple,) = triples_from_rows([_row(count=3.0, firstTimestamp=10.0, lastTimestamp=20.0)])
    assert (triple.count, triple.first_timestamp, triple.last_timestamp) == (3, 10, 20)
    assert isinstance(triple.count, int)


def test_timestamp_zero_e_sentinela_valida() -> None:
    # map-reduce v1 emite 0 fixo; o Spark emite 0 quando o _id não é ObjectId.
    (triple,) = triples_from_rows([_row(firstTimestamp=0, lastTimestamp=0)])
    assert (triple.first_timestamp, triple.last_timestamp) == (0, 0)


def test_schema_e_referenciado_nao_copiado() -> None:
    row = _row()
    (triple,) = triples_from_rows([row])
    assert triple.schema is row["schema"]
