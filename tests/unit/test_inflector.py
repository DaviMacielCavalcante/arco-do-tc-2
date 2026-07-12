"""Regressão portada do ``InflectorTest`` (Fase 0.6).

Porte de ``es.um.uschema.doc2uschema/test/regression/InflectorTest.java`` (394
linhas). É o **único** teste de regressão do original que não depende da
inferência (Fase 1) nem de um banco de pé — e é o critério de aceite da 0.6.

Estrutura do original, e o que muda no porte
--------------------------------------------
O JUnit concentra tudo em 7 ``@Test`` que chamam *helpers* (``singularToPlural``,
``upperCamelCase``, …) uma vez por caso. Aqui cada tabela de casos vira um
``@pytest.mark.parametrize``: um caso que falha aponta o par exato, em vez de
derrubar o bloco inteiro na primeira asserção.

As tabelas abaixo são transcritas **literalmente** do Java, na mesma ordem — os
pares repetidos (``quiz``, ``bus``, ``status``, ``axis``, ``octopus``, ``virus``,
``buffalo``, ``tomato``, ``half``) estão lá no original e ficam aqui também, para
o porte ser comparável linha a linha.

Além do JUnit, dois testes fixam bugs do original (ver ``bugs_originais.md``):
``ordinalize(111)`` e ``title_case(None)``.
"""

from __future__ import annotations

import pytest

from uschema.naming.inflector import Inflector, get_instance, replace_all_with_uppercase

pytestmark = pytest.mark.unit


@pytest.fixture
def inflector() -> Inflector:
    """Um Inflector com as regras default, refeito a cada teste (o ``@Before`` do JUnit).

    Returns
    -------
    Inflector
        Instância nova — os testes de ``clear``/``add_*`` mutam o objeto, e o
        singleton de módulo não pode ser contaminado.
    """
    return Inflector()


SINGULAR_TO_PLURAL: list[tuple[str, str]] = [
    ("class", "classes"),
    ("glass", "glasses"),
    ("package", "packages"),
    ("setting", "settings"),
    ("sample", "samples"),
    ("message", "messages"),
    ("content", "contents"),
    ("ball", "balls"),
    ("axis", "axes"),
    ("octopus", "octopi"),
    ("virus", "viri"),
    ("alien", "aliens"),
    ("status", "statuses"),
    ("bus", "buses"),
    ("buffalo", "buffaloes"),
    ("tomato", "tomatoes"),
    ("quiz", "quizzes"),
    ("party", "parties"),
    ("half", "halves"),
    ("stadium", "stadiums"),
    ("search", "searches"),
    ("switch", "switches"),
    ("fix", "fixes"),
    ("box", "boxes"),
    ("process", "processes"),
    ("address", "addresses"),
    ("case", "cases"),
    ("stack", "stacks"),
    ("wish", "wishes"),
    ("fish", "fish"),
    ("category", "categories"),
    ("query", "queries"),
    ("ability", "abilities"),
    ("agency", "agencies"),
    ("movie", "movies"),
    ("archive", "archives"),
    ("index", "indices"),
    ("wife", "wives"),
    ("safe", "saves"),
    ("half", "halves"),
    ("move", "moves"),
    ("salesperson", "salespeople"),
    ("person", "people"),
    ("spokesman", "spokesmen"),
    ("man", "men"),
    ("woman", "women"),
    ("basis", "bases"),
    ("diagnosis", "diagnoses"),
    ("datum", "data"),
    ("medium", "media"),
    ("analysis", "analyses"),
    ("node_child", "node_children"),
    ("child", "children"),
    ("experience", "experiences"),
    ("day", "days"),
    ("comment", "comments"),
    ("foobar", "foobars"),
    ("newsletter", "newsletters"),
    ("old_news", "old_news"),
    ("news", "news"),
    ("series", "series"),
    ("species", "species"),
    ("quiz", "quizzes"),
    ("perspective", "perspectives"),
    ("ox", "oxen"),
    ("photo", "photos"),
    ("buffalo", "buffaloes"),
    ("tomato", "tomatoes"),
    ("dwarf", "dwarves"),
    ("elf", "elves"),
    ("information", "information"),
    ("equipment", "equipment"),
    ("bus", "buses"),
    ("status", "statuses"),
    ("status_code", "status_codes"),
    ("mouse", "mice"),
    ("louse", "lice"),
    ("house", "houses"),
    ("octopus", "octopi"),
    ("virus", "viri"),
    ("alias", "aliases"),
    ("portfolio", "portfolios"),
    ("vertex", "vertices"),
    ("matrix", "matrices"),
    ("axis", "axes"),
    ("testis", "testes"),
    ("crisis", "crises"),
    ("rice", "rice"),
    ("shoe", "shoes"),
    ("horse", "horses"),
    ("prize", "prizes"),
    ("edge", "edges"),
]

LOWER_CAMEL_CASE: list[tuple[str, str, tuple[str, ...]]] = [
    ("edge", "edge", ()),
    ("active_record", "activeRecord", ()),
    ("product", "product", ()),
    ("special_guest", "specialGuest", ()),
    ("application_controller", "applicationController", ()),
    ("area51_controller", "area51Controller", ()),
    ("the-first_name", "theFirstName", ("-",)),
]

UPPER_CAMEL_CASE: list[tuple[str, str, tuple[str, ...]]] = [
    ("edge", "Edge", ()),
    ("active_record", "ActiveRecord", ()),
    ("product", "Product", ()),
    ("special_guest", "SpecialGuest", ()),
    ("application_controller", "ApplicationController", ()),
    ("area51_controller", "Area51Controller", ()),
    ("the-first_name", "TheFirstName", ("-",)),
]

UNDERSCORE: list[tuple[str, str, tuple[str, ...]]] = [
    ("activeRecord", "active_record", ()),
    ("ActiveRecord", "active_record", ()),
    ("ACTIVERecord", "active_record", ()),
    ("firstName", "first_name", ()),
    ("FirstName", "first_name", ()),
    ("name", "name", ()),
    ("The.firstName", "the_first_name", (".",)),
]

CAPITALIZE: list[tuple[str, str]] = [
    ("active record", "Active record"),
    ("first name", "First name"),
    ("name", "Name"),
    ("the first name", "The first name"),
    ("employee_salary", "Employee_salary"),
    ("underground", "Underground"),
]

HUMANIZE: list[tuple[str, str, tuple[str, ...]]] = [
    ("active_record", "Active record", ()),
    ("first_name", "First name", ()),
    ("name", "Name", ()),
    ("the_first_name", "The first name", ()),
    ("employee_salary", "Employee salary", ()),
    ("underground", "Underground", ()),
    ("id", "Id", ()),
    ("employee_id", "Employee", ()),
    ("employee_value_string", "Employee string", ("value",)),
]

TITLE_CASE: list[tuple[str, str, tuple[str, ...]]] = [
    ("active_record", "Active Record", ()),
    ("first_name", "First Name", ()),
    ("name", "Name", ()),
    ("the_first_name", "The First Name", ()),
    ("employee_salary", "Employee Salary", ()),
    ("underground", "Underground", ()),
    ("id", "Id", ()),
    ("employee_id", "Employee", ()),
    ("employee_value_string", "Employee String", ("value",)),
]

ORDINALIZE: list[tuple[int, str]] = [
    (1, "1st"),
    (2, "2nd"),
    (3, "3rd"),
    (4, "4th"),
    (5, "5th"),
    (6, "6th"),
    (7, "7th"),
    (8, "8th"),
    (9, "9th"),
    (10, "10th"),
    (11, "11th"),
    (12, "12th"),
    (13, "13th"),
    (14, "14th"),
    (15, "15th"),
    (16, "16th"),
    (17, "17th"),
    (18, "18th"),
    (19, "19th"),
    (20, "20th"),
    (21, "21st"),
    (22, "22nd"),
    (23, "23rd"),
    (24, "24th"),
    (25, "25th"),
    (26, "26th"),
    (27, "27th"),
    (28, "28th"),
    (29, "29th"),
    (30, "30th"),
    (31, "31st"),
    (32, "32nd"),
    (33, "33rd"),
    (34, "34th"),
    (35, "35th"),
    (36, "36th"),
    (37, "37th"),
    (38, "38th"),
    (39, "39th"),
    (100, "100th"),
    (101, "101st"),
    (102, "102nd"),
    (103, "103rd"),
    (104, "104th"),
    (200, "200th"),
    (201, "201st"),
    (202, "202nd"),
    (203, "203rd"),
    (204, "204th"),
    (1000, "1000th"),
    (1001, "1001st"),
    (1002, "1002nd"),
    (1003, "1003rd"),
    (1004, "1004th"),
    (10000, "10000th"),
    (10001, "10001st"),
    (10002, "10002nd"),
    (10003, "10003rd"),
    (10004, "10004th"),
    (100000, "100000th"),
    (100001, "100001st"),
    (100002, "100002nd"),
    (100003, "100003rd"),
    (100004, "100004th"),
]


def test_replace_all_with_uppercase() -> None:
    """``replaceAllWithUppercase`` sobe o grupo pedido (InflectorTest:124-129)."""
    assert replace_all_with_uppercase("hello", "([aeiou])", 1) == "hEllO"
    # O grupo 2 é o `l`; a vogal, casada mas FORA do grupo, é descartada.
    assert replace_all_with_uppercase("hello", "([aeiou])(l)", 2) == "hLlo"


@pytest.mark.parametrize(("singular", "plural"), SINGULAR_TO_PLURAL)
def test_singular_to_plural(inflector: Inflector, singular: str, plural: str) -> None:
    """Ida, volta e idempotência dos dois lados (o helper ``singularToPlural``, :42-57)."""
    assert inflector.pluralize(singular) == plural
    assert inflector.singularize(plural) == singular
    assert inflector.singularize(singular) == singular
    assert inflector.pluralize(plural) == plural


@pytest.mark.parametrize(("word", "expected", "delimiters"), LOWER_CAMEL_CASE)
def test_lower_camel_case(
    inflector: Inflector, word: str, expected: str, delimiters: tuple[str, ...]
) -> None:
    """``camelCase(w, False)``, a fachada, e o round-trip do ``underscore`` (:74-87)."""
    assert inflector.camel_case(word, False, *delimiters) == expected
    assert inflector.lower_camel_case(word, *delimiters) == expected

    if not delimiters:
        assert inflector.underscore(expected) == word


@pytest.mark.parametrize(("word", "expected", "delimiters"), UPPER_CAMEL_CASE)
def test_upper_camel_case(
    inflector: Inflector, word: str, expected: str, delimiters: tuple[str, ...]
) -> None:
    """``camelCase(w, True)``, a fachada, e o round-trip do ``underscore`` (:59-72)."""
    assert inflector.camel_case(word, True, *delimiters) == expected
    assert inflector.upper_camel_case(word, *delimiters) == expected

    if not delimiters:
        assert inflector.underscore(expected) == word


@pytest.mark.parametrize(("word", "expected", "delimiters"), UNDERSCORE)
def test_underscore(
    inflector: Inflector, word: str, expected: str, delimiters: tuple[str, ...]
) -> None:
    """``underscore`` desfaz o camelCase e aplica os delimitadores (:89-94)."""
    assert inflector.underscore(word, *delimiters) == expected


@pytest.mark.parametrize(("words", "expected"), CAPITALIZE)
def test_capitalize(inflector: Inflector, words: str, expected: str) -> None:
    """``capitalize`` — a regra de nomeação de ``EntityType`` (:96-101)."""
    assert inflector.capitalize(words) == expected


@pytest.mark.parametrize(("word", "expected", "removable_tokens"), HUMANIZE)
def test_humanize(
    inflector: Inflector, word: str, expected: str, removable_tokens: tuple[str, ...]
) -> None:
    """``humanize`` (:103-108)."""
    assert inflector.humanize(word, *removable_tokens) == expected


@pytest.mark.parametrize(("word", "expected", "removable_tokens"), TITLE_CASE)
def test_title_case(
    inflector: Inflector, word: str, expected: str, removable_tokens: tuple[str, ...]
) -> None:
    """``title_case`` (:110-115)."""
    assert inflector.title_case(word, *removable_tokens) == expected


@pytest.mark.parametrize(("number", "expected"), ORDINALIZE)
def test_ordinalize(inflector: Inflector, number: int, expected: str) -> None:
    """``ordinalize`` (:117-122)."""
    assert inflector.ordinalize(number) == expected


def test_ordinalize_replica_o_bug_i1(inflector: Inflector) -> None:
    """``ordinalize(111)`` devolve ``"111st"`` — o bug I1, replicado (bugs_originais.md).

    O guarda de 11..13 do Java testa o **número**, não ``number % 100``: 111 escapa
    dele e cai no ``% 10`` → sufixo ``"st"``. O valor correto seria ``"111th"``. O
    JUnit do original não cobre a casa das centenas terminada em 11..13, e por isso
    o bug passou. Fixamos o valor **errado** porque é o que o oráculo produz.
    """
    assert inflector.ordinalize(111) == "111st"
    assert inflector.ordinalize(112) == "112nd"
    assert inflector.ordinalize(113) == "113rd"


def test_title_case_none_nao_replica_o_npe_i2(inflector: Inflector) -> None:
    """``title_case(None)`` devolve ``None`` — desvio deliberado do porte (bug I2).

    O Java estoura ``NullPointerException`` porque o ``titleCase`` não testa o
    ``null`` que o ``humanize`` devolve. É guarda faltando, não semântica: o porte
    devolve ``None``. Único desvio de comportamento do módulo.
    """
    assert inflector.title_case(None) is None


def test_title_case_nao_trata_hifen_bug_i3(inflector: Inflector) -> None:
    """``title_case`` mantém o hífen — o javadoc do Java mente (bug I3).

    O javadoc do ``titleCase`` promete ``"x-men: the last stand"`` →
    ``"X Men: The Last Stand"``, mas o exemplo veio do ``titleize`` do Rails, que
    chama ``underscore`` antes do ``humanize``. O método do ModeShape não faz esse
    passo, e o ``humanize`` não toca em ``-`` — o Java real devolve ``"X-Men: …"``.

    Este teste existe para falhar se alguém "consertar" o ``humanize`` para tratar
    hífen: isso mudaria a nomeação de entidade (``order-details`` → ``Order details``
    em vez de ``Order-details``).
    """
    assert inflector.title_case("x-men: the last stand") == "X-Men: The Last Stand"
    assert inflector.humanize("order-details") == "Order-details"


def test_get_instance_devolve_sempre_o_mesmo_inflector() -> None:
    """O singleton de módulo é o ``Inflector.getInstance()`` do Java."""
    assert get_instance() is get_instance()
