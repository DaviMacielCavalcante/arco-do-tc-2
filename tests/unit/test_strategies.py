"""Estratégias de nível raw (Fase 1.3a) — Joiner e Merger.

Porte de ``DefaultAliasedAggregatedEntityJoiner``/``DefaultEVariationMerger``
(``doc2uschema/process/util/*.java``). Cada teste trava um comportamento citado
por linha do original; ver ``src/uschema/inference/strategies.py`` pras
citações completas.
"""

import itertools

import pytest

from uschema.inference.strategies import join_aggregated_entities, merge_equivalent_evs
from uschema.intermediate.metadata import ObjectMetadata
from uschema.intermediate.raw import (
    ArraySC,
    BooleanSC,
    NumberSC,
    ObjectSC,
    SchemaComponent,
    StringSC,
)

pytestmark = pytest.mark.unit


def _obj(name: str | None = "Order", **kwargs: SchemaComponent) -> ObjectSC:
    # `meta` nunca é `None` numa variação de verdade: raiz recebe o dela
    # (SchemaInference.java:187), não-raiz nasce com um `ObjectMetadata`
    # zerado (`:198`). O helper replica essa invariante por padrão.
    obj = ObjectSC(entity_name=name, meta=ObjectMetadata())
    for key, value in kwargs.items():
        obj.add((key, value))
    return obj


def _array(*elements: SchemaComponent) -> ArraySC:
    arr = ArraySC()
    arr.add_all(list(elements))
    return arr


# --- join_aggregated_entities (DefaultAliasedAggregatedEntityJoiner.java) --


def test_join_prefixo_de_hint_word_funde_na_entidade_existente() -> None:
    # hint "has" + entidade "Address" == "HasAddress" (:21-23, prefixo)
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [_obj("Address", street=StringSC())],
        "HasAddress": [_obj("HasAddress", street=StringSC())],
    }
    join_aggregated_entities(raw_entities, {"HasAddress"})

    assert "HasAddress" not in raw_entities
    assert len(raw_entities["Address"]) == 2


def test_join_sufixo_de_hint_word_tambem_funde() -> None:
    # entidade "Address" + hint "list" == "Addresslist" (:21-23, sufixo)
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [_obj("Address", street=StringSC())],
        "Addresslist": [_obj("Addresslist", street=StringSC())],
    }
    join_aggregated_entities(raw_entities, {"Addresslist"})

    assert "Addresslist" not in raw_entities
    assert len(raw_entities["Address"]) == 2


def test_join_e_case_insensitive() -> None:
    # equalsIgnoreCase (:23) — "HASADDRESS" tem de bater com "Address"+"has".
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [_obj("Address", street=StringSC())],
        "HASADDRESS": [_obj("HASADDRESS", street=StringSC())],
    }
    join_aggregated_entities(raw_entities, {"HASADDRESS"})

    assert "HASADDRESS" not in raw_entities
    assert len(raw_entities["Address"]) == 2


def test_join_renomeia_entity_name_das_variacoes_movidas() -> None:
    # ":30" — `((ObjectSC)sc).entityName = v` antes de mover.
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [_obj("Address", street=StringSC())],
        "HasAddress": [_obj("HasAddress", street=StringSC())],
    }
    join_aggregated_entities(raw_entities, {"HasAddress"})

    movida = raw_entities["Address"][-1]
    assert isinstance(movida, ObjectSC)
    assert movida.entity_name == "Address"


def test_join_sem_entidade_correspondente_nao_altera_nada() -> None:
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [_obj("Address", street=StringSC())],
        "Unrelated": [_obj("Unrelated", x=NumberSC())],
    }
    original = dict(raw_entities)

    join_aggregated_entities(raw_entities, {"Unrelated"})

    assert raw_entities == original


def test_join_so_pega_a_primeira_entidade_que_bate_ordem_do_dict() -> None:
    """``findFirst`` (`:26`) para no primeiro `entity` que bate.

    ``"listoflist"`` decompõe em mais de uma forma válida: `entity="oflist"`
    via hint ``"list"`` (prefixo), OU `entity="list"` via hint ``"listof"``
    (prefixo). Qual delas "ganha" depende só da ordem de iteração de
    `raw_entities` — é a limitação que o autor original documentou
    (`DefaultAliasedAggregatedEntityJoiner.java:24-25`), não um bug a corrigir.
    """
    raw_entities: dict[str, list[SchemaComponent]] = {
        "oflist": [_obj("Oflist", x=NumberSC())],
        "list": [_obj("List", y=StringSC())],
        "listoflist": [_obj("Listoflist", z=BooleanSC())],
    }
    join_aggregated_entities(raw_entities, {"listoflist"})

    assert "listoflist" not in raw_entities
    assert "oflist" in raw_entities and "list" in raw_entities
    assert len(raw_entities["oflist"]) == 2, "a primeira entidade do dict ganhou o join"
    assert len(raw_entities["list"]) == 1, "esta não deveria receber nada"


# --- merge_equivalent_evs (DefaultEVariationMerger.java) -------------------


def test_merge_funde_variacoes_com_mesma_forma_ignorando_entity_name() -> None:
    """``walkAndMerge`` não compara `entityName`/`isRoot` (`:72-91`) — mais frouxo que `__eq__`."""
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [
            _obj("Address", street=StringSC()),
            _obj("EnderecoAlternativo", street=StringSC()),
        ],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Address"]) == 1


def test_merge_combina_metadata_no_sobrevivente() -> None:
    from uschema.intermediate.metadata import ObjectMetadata

    perdedor = _obj("Address", street=StringSC())
    perdedor.meta = ObjectMetadata(count=3, first_timestamp=10, last_timestamp=20)
    sobrevivente = _obj("Address", street=StringSC())
    sobrevivente.meta = ObjectMetadata(count=5, first_timestamp=5, last_timestamp=30)

    raw_entities: dict[str, list[SchemaComponent]] = {"Address": [perdedor, sobrevivente]}
    merge_equivalent_evs(raw_entities)

    [restante] = raw_entities["Address"]
    assert isinstance(restante, ObjectSC)
    assert restante.meta is not None
    meta = restante.meta
    assert (meta.count, meta.first_timestamp, meta.last_timestamp) == (8, 5, 30)


def test_merge_nao_funde_campos_com_nomes_diferentes() -> None:
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [
            _obj("Address", street=StringSC()),
            _obj("Address", city=StringSC()),
        ],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Address"]) == 2


def test_merge_nao_funde_numero_de_campos_diferente() -> None:
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [
            _obj("Address", street=StringSC()),
            _obj("Address", street=StringSC(), city=StringSC()),
        ],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Address"]) == 2


def test_merge_arrays_heterogeneos_comparam_por_posicao() -> None:
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Order": [
            _obj("Order", items=_array(NumberSC(), StringSC())),
            _obj("PedidoAlternativo", items=_array(NumberSC(), StringSC())),
        ],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Order"]) == 1


def test_merge_nao_funde_homogeneo_com_heterogeneo() -> None:
    # ArraySC.java:86-87 replicado no walkAndMerge (:95) — mesma checagem.
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Order": [
            _obj("Order", items=_array(NumberSC(), NumberSC())),  # homogêneo
            _obj("Order", items=_array(NumberSC(), StringSC())),  # heterogêneo
        ],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Order"]) == 2


def test_merge_homogeneo_empresta_elemento_do_lado_nao_vazio() -> None:
    """``homogeneousArraysMerge`` (`:120-143`) reconcilia vazio x não-vazio.

    O array vazio "ganha" o elemento do outro lado (`sc.add(...)`), e os
    bounds reconciliam por `min`/`max` — é aqui que `lower_bounds` deixa de
    ser sempre `0`.
    """
    cheio = _obj("Order", items=_array(NumberSC()))
    vazio = _obj("Order", items=ArraySC())  # homogêneo e vazio por padrão

    raw_entities: dict[str, list[SchemaComponent]] = {"Order": [cheio, vazio]}
    merge_equivalent_evs(raw_entities)

    [restante] = raw_entities["Order"]
    assert isinstance(restante, ObjectSC)
    [(_, items)] = restante.inners
    assert isinstance(items, ArraySC)
    assert items.size() == 1
    assert items.upper_bounds == 1
    assert items.lower_bounds == 0


def test_merge_atualiza_referencia_por_identidade_ao_remover_o_perdedor() -> None:
    """``updateReferences`` (`:145-177`) — o perdedor pode estar referenciado alhures.

    Se outro campo apontava (por identidade de objeto, não por igualdade)
    pro nó que a fusão descarta, esse ponteiro precisa seguir pro sobrevivente
    — senão fica órfão.
    """
    perdedor = _obj("Address", street=StringSC())
    sobrevivente = _obj("Address", street=StringSC())
    pedido = _obj("Order", shipping=perdedor)

    raw_entities: dict[str, list[SchemaComponent]] = {
        "Order": [pedido],
        "Address": [perdedor, sobrevivente],
    }
    merge_equivalent_evs(raw_entities)

    assert raw_entities["Address"] == [sobrevivente]
    [(nome, valor)] = pedido.inners
    assert nome == "shipping"
    assert valor is sobrevivente


def test_merge_estabiliza_em_cadeia_de_tres_variacoes_iguais() -> None:
    # do/while até não haver mais fusão (:21-47) — não para na primeira.
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [
            _obj("A1", street=StringSC()),
            _obj("A2", street=StringSC()),
            _obj("A3", street=StringSC()),
        ],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Address"]) == 1


@pytest.mark.parametrize("ordem", list(itertools.permutations(["A", "B", "C"])))
def test_merge_remove_por_identidade_mesmo_com_duplicatas_exatas(
    ordem: tuple[str, str, str],
) -> None:
    """``list.remove()`` usa ``__eq__``; ``Iterator.remove()`` do Java usa o cursor.

    São mecânicas diferentes: se duas variações forem **estritamente** iguais
    (mesmo `entity_name`/`is_root`/`inners` — plausível depois que o Joiner
    renomeia coisas), ``variations.remove(to_consider)`` poderia, em tese,
    apagar a primeira que bate por igualdade em vez do objeto `to_consider`
    específico. Na prática isso não acontece: o algoritmo sempre resolve o
    elemento ainda-não-casado **mais antigo** da lista primeiro (reinicia a
    varredura a cada fusão), então no momento da remoção nenhum elemento
    *anterior* a `to_consider` pode ser igual a ele — se fosse, já teria
    disparado a própria fusão antes. Testado nas 6 ordens possíveis de 3
    duplicatas exatas (``meta.count`` diferente só pra rastrear identidade,
    já que `meta` não entra na igualdade) + um decoy de forma diferente: a
    contagem total nunca se perde, em nenhuma ordem.
    """
    valores = {"A": 10, "B": 20, "C": 30}
    duplicatas = {tag: _obj("Address", street=StringSC()) for tag in valores}
    for tag, count in valores.items():
        meta = duplicatas[tag].meta
        assert meta is not None
        meta.count = count

    decoy = _obj("Address", street=StringSC(), city=StringSC())  # forma diferente, não casa
    variations: list[SchemaComponent] = [decoy, *(duplicatas[tag] for tag in ordem)]
    raw_entities: dict[str, list[SchemaComponent]] = {"Address": variations}

    merge_equivalent_evs(raw_entities)

    resultado = raw_entities["Address"]
    assert len(resultado) == 2, "decoy + 1 sobrevivente combinado"
    contagens = sorted(
        sc.meta.count for sc in resultado if isinstance(sc, ObjectSC) and sc.meta is not None
    )
    assert contagens == [0, 60], "decoy (count=0) + soma das 3 duplicatas (10+20+30)"


def test_merge_nao_mexe_em_entidade_sem_duplicata() -> None:
    raw_entities: dict[str, list[SchemaComponent]] = {
        "Address": [_obj("Address", street=StringSC())],
        "Order": [_obj("Order", total=NumberSC())],
    }
    merge_equivalent_evs(raw_entities)

    assert len(raw_entities["Address"]) == 1
    assert len(raw_entities["Order"]) == 1
