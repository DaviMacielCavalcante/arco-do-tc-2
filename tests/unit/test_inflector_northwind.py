"""O Inflector reproduz os nomes de ``EntityType`` do XMI-oráculo (Fase 0.6).

Os 205 casos de ``test_inflector.py`` provam fidelidade ao ``InflectorTest`` — a
*unidade*. Este arquivo prova a única coisa que importa para o porte: que as
regras de nomeação do pipeline, aplicadas às coleções do Northwind, produzem
**exatamente** os nomes que o oráculo Java gravou em
``resources/mongodb/model_northwind.xmi``.

As três regras de nomeação, e onde o Java as chama
--------------------------------------------------
1. **Entidade raiz** — ``capitalize(<nome da coleção>)`` (``SchemaInference:183,188``).
   Repare que ``capitalize`` **não** faz camelCase: ``inventory_transaction_types``
   vira ``Inventory_transaction_types``, com o ``_`` preservado e o resto em
   minúscula. Um ``title_case`` no lugar daria ``Inventory_Transaction_Types`` e
   renomearia entidade.
2. **Entidade agregada** — ``capitalize(singularize(<nome do array>))``
   (``SchemaInference:233``, ``USchemaModelBuilder:194``). O array ``details``
   dentro de ``orders`` vira a entidade ``Detail``.
3. O ``_id`` embutido (o ``$oid``) vira entidade por ``capitalize("_id")``, que é
   **ponto fixo** — o ``_`` não tem maiúscula, e ``id`` já está em minúscula.

O XMI tem 19 ``EntityType``: as 17 coleções (todas ``root``) + ``Detail`` + ``_id``
(as duas agregadas, ``root=false``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pyecore.ecore import EPackage

from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model
from uschema.naming.inflector import get_instance

pytestmark = pytest.mark.unit

RESOURCES_DIR = Path(__file__).resolve().parents[2] / "resources"

# As 17 coleções do dump MongoDB do Northwind — a ENTRADA do pipeline. Não são
# derivadas do XMI (isso seria circular): são os nomes das coleções que o oráculo
# leu para produzir o XMI de referência.
COLECOES_NORTHWIND: list[str] = [
    "customers",
    "employees",
    "inventory_transaction_types",
    "inventory_transactions",
    "invoices",
    "order_details_status",
    "orders",
    "orders_status",
    "orders_tax_status",
    "privileges",
    "products",
    "purchase_order_status",
    "purchase_orders",
    "sales_reports",
    "shippers",
    "strings",
    "suppliers",
]

# O array `details`, dentro de `orders`, é o que dá origem à entidade agregada.
ARRAY_AGREGADO = "details"


@pytest.fixture
def metamodel() -> EPackage:
    """Metamodelo U-Schema carregado e registrado."""
    return load_metamodel()


@pytest.fixture
def nomes_do_oraculo(metamodel: EPackage) -> set[str]:
    """Nomes das ``EntityType`` do XMI de referência do Northwind.

    Returns
    -------
    set of str
        Os 19 nomes que o Java gravou.
    """
    schema = load_model(RESOURCES_DIR / "mongodb" / "model_northwind.xmi", metamodel)
    return {entity.name for entity in schema.entities}


def test_capitalize_das_colecoes_da_as_entidades_raiz(nomes_do_oraculo: set[str]) -> None:
    """``capitalize`` de cada coleção reproduz o nome da entidade raiz no XMI."""
    inflector = get_instance()

    nomes_inferidos = {inflector.capitalize(colecao) for colecao in COLECOES_NORTHWIND}

    assert nomes_inferidos <= nomes_do_oraculo
    assert len(nomes_inferidos) == len(COLECOES_NORTHWIND)


def test_entidade_agregada_vem_de_capitalize_singularize(nomes_do_oraculo: set[str]) -> None:
    """O array ``details`` vira a entidade ``Detail`` — ``capitalize(singularize(...))``."""
    inflector = get_instance()

    assert inflector.singularize(ARRAY_AGREGADO) == "detail"
    assert inflector.capitalize(inflector.singularize(ARRAY_AGREGADO)) == "Detail"
    assert "Detail" in nomes_do_oraculo


def test_id_embutido_e_ponto_fixo_do_capitalize(nomes_do_oraculo: set[str]) -> None:
    """``capitalize("_id")`` devolve ``"_id"`` — a entidade do ``$oid`` do XMI."""
    inflector = get_instance()

    assert inflector.capitalize("_id") == "_id"
    assert "_id" in nomes_do_oraculo


def test_o_inflector_reproduz_as_19_entidades_do_oraculo(nomes_do_oraculo: set[str]) -> None:
    """Fecho: as 3 regras de nomeação, juntas, dão exatamente os 19 nomes do XMI.

    É o gate da 0.6. Se uma regra do Inflector divergir do Java, algum nome sai
    diferente e o conjunto deixa de bater — que é como o harness da Fase 0.3
    acusaria a divergência, só que aqui o erro aponta a palavra exata.
    """
    inflector = get_instance()

    inferidos = {inflector.capitalize(colecao) for colecao in COLECOES_NORTHWIND}
    inferidos.add(inflector.capitalize(inflector.singularize(ARRAY_AGREGADO)))
    inferidos.add(inflector.capitalize("_id"))

    assert inferidos == nomes_do_oraculo


def test_title_case_renomearia_entidade(nomes_do_oraculo: set[str]) -> None:
    """Guarda de regressão: trocar ``capitalize`` por ``title_case`` quebra os nomes.

    Existe para documentar por que ``capitalize`` não é ``str.title()`` — e para
    falhar ruidosamente se alguém "melhorar" o método.
    """
    inflector = get_instance()

    assert inflector.title_case("inventory_transaction_types") == "Inventory Transaction Types"
    assert "Inventory Transaction Types" not in nomes_do_oraculo
    assert "Inventory_transaction_types" in nomes_do_oraculo
