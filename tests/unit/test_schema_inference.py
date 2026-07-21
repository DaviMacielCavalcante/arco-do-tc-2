"""``SchemaInference.infer`` (Fase 1.2) — porte de ``SchemaInference.java``.

Testes sintéticos, unitários (não os de regressão JUnit portados — esses são
da 1.6, cortados na tripla via fixtures do oráculo). Cada teste trava um
comportamento citado por linha do original; ver
``src/uschema/inference/schema_inference.py`` pras citações completas.
"""

from typing import Any

import pytest

from uschema.extractors.triple import SchemaTriple
from uschema.inference.schema_inference import SchemaInference
from uschema.intermediate.raw import ArraySC, ObjectSC

pytestmark = pytest.mark.unit


def _triple(schema: dict[str, Any], count: int = 1, first: int = 0, last: int = 0) -> SchemaTriple:
    return SchemaTriple(schema=schema, count=count, first_timestamp=first, last_timestamp=last)


# --- nomeação de entidade (SchemaInference.java:182-188) -------------------


def test_entidade_raiz_usa_type_marker_so_capitalizado_nao_singularizado() -> None:
    # `:183` — só `capitalize`, sem `singularize`. "orders" vira "Orders",
    # plural mesmo (é o nome real de entidade que o oráculo produz).
    result = SchemaInference().infer([_triple({"_type": "orders", "x": 1})])
    assert "Orders" in result
    assert "Order" not in result


def test_type_marker_nao_aparece_como_campo() -> None:
    # `_type` é o único `ignored_attributes` (DefaultSchemaInferenceConfig).
    result = SchemaInference().infer([_triple({"_type": "orders", "x": 1})])
    [variacao] = result["Orders"]
    assert isinstance(variacao, ObjectSC)
    assert [nome for nome, _ in variacao.inners] == ["x"]


def test_objeto_aninhado_capitaliza_o_nome_do_campo_sem_singularizar() -> None:
    # Objeto (não array) não passa por `singularize` — só `infer(IAJArray,...)`
    # faz isso (`:236`). "endereco" (já singular) vira "Endereco".
    result = SchemaInference().infer([_triple({"_type": "customers", "endereco": {"rua": "A"}})])
    assert "Endereco" in result


def test_campos_ficam_em_ordem_alfabetica() -> None:
    # `:191-194` — TreeSet. Diverge do Java só fora do BMP (irrelevante aqui).
    result = SchemaInference().infer([_triple({"_type": "t", "z": 1, "a": 1, "m": 1})])
    [variacao] = result["T"]
    assert isinstance(variacao, ObjectSC)
    assert [nome for nome, _ in variacao.inners] == ["a", "m", "z"]


def test_entidade_raiz_sem_type_marker_usa_element_name_vazio() -> None:
    # `:188` — `typeName.orElse(capitalize(elementName.orElse("")))`; o
    # objeto raiz nunca tem `elementName`, então cai em `capitalize("")`.
    result = SchemaInference().infer([_triple({"x": 1})])
    assert "" in result
    [variacao] = result[""]
    assert isinstance(variacao, ObjectSC)
    assert variacao.is_root is True


# --- is_root e meta (SchemaInference.java:186-187) -------------------------


def test_objeto_raiz_marca_is_root() -> None:
    result = SchemaInference().infer([_triple({"_type": "t", "x": 1})])
    [variacao] = result["T"]
    assert isinstance(variacao, ObjectSC)
    assert variacao.is_root is True


def test_objeto_aninhado_nao_marca_is_root() -> None:
    result = SchemaInference().infer([_triple({"_type": "t", "endereco": {"rua": "A"}})])
    [variacao] = result["Endereco"]
    assert isinstance(variacao, ObjectSC)
    assert variacao.is_root is False


def test_meta_do_campo_aninhado_nasce_zerado_mas_o_adjust_propaga_da_raiz() -> None:
    # `:198` — `new ObjectMetadata()` pro campo aninhado, na hora do `infer`
    # recursivo. Mas como a entidade-raiz que o contém ("T") tem meta real, o
    # `_inner_count_and_timestamps_adjust` (`:92-113`) acha essa ocorrência via
    # `containsSchemaComponent` e propaga — resultado final não fica zerado.
    result = SchemaInference().infer(
        [_triple({"_type": "t", "endereco": {"rua": "A"}}, count=99, first=10, last=20)]
    )
    [endereco] = result["Endereco"]
    assert isinstance(endereco, ObjectSC)
    assert endereco.meta is not None
    assert (endereco.meta.count, endereco.meta.first_timestamp, endereco.meta.last_timestamp) == (
        99,
        10,
        20,
    )


# --- colapso de variações + #8 (SchemaInference.java:200-215) --------------


def test_bug_8_colapso_descarta_o_meta_inteiro_da_segunda_ocorrencia() -> None:
    """**#8** (``bugs_originais.md``).

    ``SchemaInference.java:207-211``: quando uma variação nova colapsa numa
    já registrada, o código só faz ``retSchema = foundSchema.get();`` — nada
    mais. O ``meta`` inteiro da ocorrência nova (``count`` **e** timestamps,
    não só bounds de array) é descartado, não combinado.
    """
    t1 = _triple({"_type": "orders", "id": 1}, count=3, first=10, last=20)
    t2 = _triple({"_type": "orders", "id": 1}, count=2, first=5, last=30)
    result = SchemaInference().infer([t1, t2])

    assert len(result["Orders"]) == 1, "ArraySC/__eq__ à parte, os dois colapsam (mesmo campo 'id')"
    [orders] = result["Orders"]
    assert isinstance(orders, ObjectSC)
    assert orders.meta is not None
    assert (orders.meta.count, orders.meta.first_timestamp, orders.meta.last_timestamp) == (
        3,
        10,
        20,
    ), "meta é o de t1 (1a ocorrência) — o de t2 sumiu por completo, não foi somado"


def test_ocorrencias_com_campos_diferentes_nao_colapsam() -> None:
    t1 = _triple({"_type": "orders", "id": 1})
    t2 = _triple({"_type": "orders", "id": 1, "total": 2})
    result = SchemaInference().infer([t1, t2])

    assert len(result["Orders"]) == 2


def test_bug_8_tambem_descarta_upper_bounds_do_array_aninhado() -> None:
    """Mesmo achado do #8, só que visível também no campo array aninhado.

    Não é uma perda *separada* do `meta` do objeto — é a mesma: a árvore
    inteira da segunda ocorrência (inclusive o ``ArraySC`` de ``extra``, com
    seu próprio ``upper_bounds``) é descartada, não só o ``meta`` do nível
    mais externo.
    """
    t1 = _triple({"_type": "values", "a": 1, "extra": ["x"]}, count=1, first=1, last=1)
    t2 = _triple({"_type": "values", "a": 1, "extra": ["x", "x", "x"]}, count=1, first=2, last=2)
    result = SchemaInference().infer([t1, t2])

    assert len(result["Values"]) == 1, "ArraySC.__eq__ ignora tamanho — as duas colapsam"
    [values] = result["Values"]
    assert isinstance(values, ObjectSC)
    assert values.meta is not None
    assert values.meta.count == 1, (
        "meta inteiro de t2 descartado — inclusive o count, não só bounds"
    )

    fields = dict(values.inners)
    extra = fields["extra"]
    assert isinstance(extra, ArraySC)
    assert extra.upper_bounds == 1, (
        "upper_bounds da 1a ocorrência — o de t2 nunca chega a existir aqui"
    )


# --- array (SchemaInference.java:230-248) -----------------------------------


def test_campo_array_singulariza_o_nome_da_entidade_interna() -> None:
    # `:236` — só array passa por `singularize`. "items" -> "Item".
    result = SchemaInference().infer([_triple({"_type": "orders", "items": [{"sku": "a"}]})])
    assert "Item" in result


def test_elementos_de_array_estruturalmente_iguais_deduplicam() -> None:
    """LinkedHashSet (``:243-245``) via ``dict.fromkeys`` — dedup por ``__eq__``.

    Simplifica ``Aggr{V1,V2,V2,V2}`` → ``Aggr{V1,V2}`` **antes** mesmo de
    `ArraySC.add` contar qualquer coisa — os 3 elementos estruturalmente
    iguais viram **1** `add()` só. Não é bug: é a mesma simplificação que o
    `SimplifyAggrTest` (1.6) documenta.
    """
    result = SchemaInference().infer(
        [_triple({"_type": "orders", "items": [{"sku": "a"}, {"sku": "a"}, {"sku": "a"}]})]
    )
    [orders] = result["Orders"]
    assert isinstance(orders, ObjectSC)
    fields = dict(orders.inners)
    items = fields["items"]
    assert isinstance(items, ArraySC)
    assert items.size() == 1, "os 3 elementos iguais colapsam num só, antes do add()"
    assert len(items.inners) == 1


def test_elementos_de_array_estruturalmente_diferentes_nao_deduplicam() -> None:
    result = SchemaInference().infer(
        [_triple({"_type": "orders", "items": [{"sku": "a"}, {"nome": "b"}]})]
    )
    [orders] = result["Orders"]
    assert isinstance(orders, ObjectSC)
    fields = dict(orders.inners)
    items = fields["items"]
    assert isinstance(items, ArraySC)
    assert items.homogeneous is False
    assert items.size() == 2


def test_array_de_escalares_nao_vira_entidade() -> None:
    result = SchemaInference().infer([_triple({"_type": "orders", "tags": ["a", "b"]})])
    assert list(result.keys()) == ["Orders"]


# --- innerCountAndTimestampsAdjust (SchemaInference.java:92-113) -----------


def test_inner_count_and_timestamps_adjust_propaga_meta_pra_entidade_interna() -> None:
    """Propagação isolada do #8: as duas raízes têm campos diferentes de propósito.

    Se as duas ocorrências de "Customers" tivessem exatamente os mesmos
    campos (como em versões anteriores deste teste), elas colapsariam entre
    si pelo próprio #8 — e aí o `meta` da segunda raiz já teria sido
    descartado *antes* de chegar em `_inner_count_and_timestamps_adjust`,
    confundindo o que este teste quer isolar. Por isso ``t2`` ganha um campo
    a mais (``vip``): as duas raízes ficam como variações **separadas** de
    "Customers" (campos diferentes = não colapsam), cada uma com seu próprio
    `meta` intacto — só assim dá pra testar a propagação em si, sem o #8
    interferir.
    """
    t1 = _triple(
        {"_type": "customers", "name": "Acme", "address": {"street": "A"}},
        count=1,
        first=100,
        last=100,
    )
    t2 = _triple(
        {"_type": "customers", "name": "Beta", "vip": True, "address": {"street": "B"}},
        count=1,
        first=200,
        last=200,
    )
    result = SchemaInference().infer([t1, t2])

    assert len(result["Customers"]) == 2, "campos diferentes — não colapsam pelo #8"
    assert "Address" in result
    [address] = result["Address"]
    assert isinstance(address, ObjectSC)
    assert address.meta is not None
    assert address.meta.count == 2, "propagado das duas ocorrências-raiz que contêm 'Address'"


# --- integração com o Joiner (Fase 1.3a) ------------------------------------


def test_joiner_bem_sucedido_estoura_key_error_no_passo_seguinte() -> None:
    """Confirma, de ponta a ponta, o NPE latente que a leitura do Java previu.

    Quando o Joiner funde uma entidade interna com outra já existente
    (``join_aggregated_entities``, 1.3a), ele remove a chave de
    ``raw_entities`` — mas **não** atualiza ``inner_schema_names``, que
    ``_inner_count_and_timestamps_adjust`` ainda percorre logo em seguida.
    No Java isso é ``NullPointerException`` (``for``-each sobre ``null``); no
    porte é ``KeyError``. Não é uma falha do porte: é a mesma sequência do
    original, replicada por decisão explícita (não guardar). Na prática, isso
    significa que **qualquer** entrada em que o Joiner ache um match faz o
    `infer()` inteiro estourar — não é um caso raro, é garantido.
    """
    t_root_address = _triple({"_type": "address", "street": "X"}, count=1)
    t_customer = _triple(
        {"_type": "customers", "name": "Acme", "hasAddress": {"street": "Y"}}, count=1
    )

    with pytest.raises(KeyError):
        SchemaInference().infer([t_root_address, t_customer])
