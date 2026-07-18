"""Modelo intermediário raw (Fase 1.1) — igualdade estrutural e ``ArraySC``.

A igualdade destas classes é o que decide o colapso de variações no pipeline
inteiro. Cada teste aqui trava um comportamento do Java citado por linha; se um
deles ficar vermelho, o número de ``StructuralVariation`` no XMI muda.
"""

import pytest

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

pytestmark = pytest.mark.unit

LEAVES = [StringSC, NumberSC, BooleanSC, NullSC, ObjectIdSC]


# --- SchemaComponent: igualdade por classe (SchemaComponent.java:8,14) ------


@pytest.mark.parametrize("leaf", LEAVES)
def test_duas_folhas_do_mesmo_tipo_sao_iguais(leaf: type[SchemaComponent]) -> None:
    # As folhas não têm estado: a base compara só a classe concreta.
    assert leaf() == leaf()


@pytest.mark.parametrize("leaf", LEAVES)
def test_folhas_de_tipos_diferentes_sao_diferentes(leaf: type[SchemaComponent]) -> None:
    outras = [other for other in LEAVES if other is not leaf]
    assert all(leaf() != other() for other in outras)


@pytest.mark.parametrize("leaf", LEAVES)
def test_contrato_hash_eq_das_folhas(leaf: type[SchemaComponent]) -> None:
    # a == b  =>  hash(a) == hash(b); e o set colapsa as duas em uma.
    assert hash(leaf()) == hash(leaf())
    assert len({leaf(), leaf()}) == 1


def test_folhas_distintas_nao_colapsam_em_set() -> None:
    assert len({leaf() for leaf in LEAVES}) == len(LEAVES)


def test_comparar_com_objeto_alheio_da_false_sem_estourar() -> None:
    # O Java não tem guarda de tipo: `getClass().getName()` funciona para
    # qualquer objeto e simplesmente não casa.
    assert StringSC() != "oid"
    assert StringSC() != 42
    assert StringSC() is not None


# --- ObjectSC (ObjectSC.java:23-37) ----------------------------------------


def _obj(name: str | None = "Order", **kwargs: object) -> ObjectSC:
    obj = ObjectSC(entity_name=name)
    for key, value in kwargs.items():
        obj.add((key, value))  # type: ignore[arg-type]
    return obj


def test_objetos_com_mesmos_campos_na_mesma_ordem_sao_iguais() -> None:
    assert _obj(a=NumberSC(), b=StringSC()) == _obj(a=NumberSC(), b=StringSC())


def test_a_ordem_dos_campos_importa() -> None:
    """``inners`` é lista, não mapa (``ObjectSC.java:33-34``).

    Trocar por ``dict`` daria igualdade sem ordem e faria variações colapsarem
    onde o Java não colapsa.
    """
    ordem_a = ObjectSC(entity_name="Order")
    ordem_a.add_all([("a", NumberSC()), ("b", StringSC())])
    ordem_b = ObjectSC(entity_name="Order")
    ordem_b.add_all([("b", StringSC()), ("a", NumberSC())])
    assert ordem_a != ordem_b


def test_entity_name_entra_na_igualdade() -> None:
    assert _obj("Order", a=NumberSC()) != _obj("Customer", a=NumberSC())


def test_is_root_entra_na_igualdade() -> None:
    raiz = _obj(a=NumberSC())
    raiz.is_root = True
    assert raiz != _obj(a=NumberSC())


def test_meta_nao_entra_na_igualdade() -> None:
    """O Java compara só ``entityName``/``isRoot``/``inners`` (``:32-34``).

    É o que permite o colapso de duas triplas com contagens diferentes — e é
    por isso que a correção do #8 tem de combinar o ``meta`` explicitamente.
    """
    com_meta = _obj(a=NumberSC())
    com_meta.meta = ObjectMetadata(count=7, first_timestamp=1, last_timestamp=2)
    assert com_meta == _obj(a=NumberSC())


def test_igualdade_desce_recursivamente() -> None:
    aninhado_a = _obj("Order", item=_obj("Item", price=NumberSC()))
    aninhado_b = _obj("Order", item=_obj("Item", price=NumberSC()))
    aninhado_c = _obj("Order", item=_obj("Item", price=StringSC()))
    assert aninhado_a == aninhado_b
    assert aninhado_a != aninhado_c


def test_contrato_hash_eq_do_object_sc() -> None:
    assert hash(_obj(a=NumberSC())) == hash(_obj(a=NumberSC()))
    assert len({_obj(a=NumberSC()), _obj(a=NumberSC())}) == 1


def test_hash_com_entity_name_nulo_nao_estoura() -> None:
    """Divergência a favor do porte: o Java estoura (``ObjectSC.java:24``).

    ``entityName.hashCode()`` com ``null`` dá ``NullPointerException``. Em
    Python ``hash(None)`` é válido. É guarda faltando, não semântica — mesma
    família do ``I2`` do Inflector. O ``RawSchemaGen`` produz exatamente esse
    caso (``entity_name`` nulo).
    """
    assert isinstance(hash(_obj(None, a=NumberSC())), int)


def test_add_e_add_all_anexam_em_ordem() -> None:
    obj = ObjectSC(entity_name="Order")
    obj.add(("a", NumberSC()))
    obj.add_all([("b", StringSC()), ("c", BooleanSC())])
    assert [name for name, _ in obj.inners] == ["a", "b", "c"]
    assert obj.size() == 3


def test_object_sc_novo_nasce_vazio_e_nao_raiz() -> None:
    # ObjectSC.java:17-20 — isRoot inicializa em FALSE; meta e entityName nulos.
    obj = ObjectSC()
    assert obj.inners == []
    assert obj.is_root is False
    assert obj.meta is None
    assert obj.entity_name is None


def test_dois_object_sc_novos_nao_compartilham_inners() -> None:
    # Regressão do default mutável: `field(default_factory=list)`.
    primeiro, segundo = ObjectSC(), ObjectSC()
    primeiro.add(("a", NumberSC()))
    assert segundo.inners == []


# --- ArraySC (ArraySC.java:38-112) -----------------------------------------


def _array(*elements: SchemaComponent) -> ArraySC:
    arr = ArraySC()
    arr.add_all(list(elements))
    return arr


def test_array_novo_e_homogeneo_e_vazio() -> None:
    """O guarda do bug **#7**: ``size() == 0`` *e* ``inners`` vazio.

    É o que impede indexar ``inners[0]`` num array vazio lá na 1.4.
    """
    arr = ArraySC()
    assert arr.size() == 0
    assert arr.inners == []
    assert arr.homogeneous is True


def test_homogeneo_guarda_um_elemento_e_conta_o_resto() -> None:
    arr = _array(NumberSC(), NumberSC(), NumberSC())
    assert arr.homogeneous is True
    assert len(arr.inners) == 1, "o ramo homogêneo não deve fazer inners crescer"
    assert arr.size() == 3
    assert arr.upper_bounds == 3


def test_lower_bounds_nunca_e_incrementado() -> None:
    # ArraySC.java:118-120 — só existe o setter; o original nunca o incrementa.
    arr = _array(NumberSC(), NumberSC())
    assert arr.lower_bounds == 0


def test_vira_heterogeneo_e_reconstroi_por_extenso() -> None:
    # ArraySC.java:57-62 — nCopies(homogeneous_size, firstSc) + sc.
    arr = _array(NumberSC(), NumberSC(), StringSC())
    assert arr.homogeneous is False
    assert [type(inner).__name__ for inner in arr.inners] == [
        "NumberSC",
        "NumberSC",
        "StringSC",
    ]
    assert arr.size() == 3
    assert arr.upper_bounds == 3


def test_heterogeneo_continua_anexando() -> None:
    arr = _array(NumberSC(), StringSC(), BooleanSC(), NullSC())
    assert arr.homogeneous is False
    assert arr.size() == 4
    assert arr.upper_bounds == 4


def test_arrays_homogeneos_de_tamanhos_diferentes_sao_iguais() -> None:
    """**Origem do bug #8**, replicada de propósito (``ArraySC.java:96-97``).

    A checagem de ``homogeneous_size`` está comentada no original. Sem essa
    igualdade frouxa o #8 nem dispara — e é por isso que a correção do #8 (1.2)
    combina o ``meta`` em vez de mexer aqui.
    """
    tres = _array(*[NumberSC()] * 3)
    sete = _array(*[NumberSC()] * 7)
    assert tres == sete
    assert (tres.size(), sete.size()) == (3, 7)


def test_homogeneo_e_heterogeneo_nunca_sao_iguais() -> None:
    # ArraySC.java:86-87 — compara as duas homogeneidades, não a própria.
    assert _array(NumberSC(), NumberSC()) != _array(NumberSC(), StringSC())


def test_dois_heterogeneos_identicos_sao_iguais() -> None:
    # Regressão do erro de escrever `if not self.homogeneous: return False`,
    # que tornaria todo heterogêneo diferente de tudo, inclusive de si.
    assert _array(NumberSC(), StringSC()) == _array(NumberSC(), StringSC())


def test_heterogeneos_com_ordem_diferente_sao_diferentes() -> None:
    assert _array(NumberSC(), StringSC()) != _array(StringSC(), NumberSC())


def test_arrays_de_conteudo_diferente_sao_diferentes() -> None:
    assert _array(NumberSC()) != _array(StringSC())


def test_array_vazio_e_igual_a_array_vazio() -> None:
    assert ArraySC() == ArraySC()


def test_contrato_hash_eq_do_array_sc() -> None:
    tres = _array(*[NumberSC()] * 3)
    sete = _array(*[NumberSC()] * 7)
    assert hash(tres) == hash(sete), "iguais têm de ter o mesmo hash"
    assert len({tres, sete}) == 1


def test_array_e_object_nao_sao_iguais() -> None:
    assert ArraySC() != ObjectSC()


def test_dois_array_sc_novos_nao_compartilham_inners() -> None:
    primeiro, segundo = ArraySC(), ArraySC()
    primeiro.add(NumberSC())
    assert segundo.inners == []
