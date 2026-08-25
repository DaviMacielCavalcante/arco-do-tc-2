"""Invariantes estruturais do Northwind (Fase 3.1).

Afirma sobre o XMI o que `fase3_validacao_volume.md:43-44` lista como
"casos que o porte tem de reproduzir": 19 `EntityType` (17 raiz + `_id` e
`Detail`) e o `Aggregate` de `Orders`/`Purchase_orders` para `Detail` com
`upperBound=-1` e `optional=true`.

Complementa o `compare()`, não repete: o harness afirma que porte e oráculo
são iguais; isto afirma **o que** o modelo contém. Se as duas pontas
perdessem `Detail` juntas, o `compare()` seguiria dando `equivalent=True`.

Não precisa de banco — lê o XMI de `resources/`, que é versionado. Por padrão
verifica o oráculo; `--xmi` aponta para outro (ex.: a saída do porte em
`out/porte/mongo_northwind.xmi`).

    uv run python scripts/check_northwind_invariants.py
    uv run python scripts/check_northwind_invariants.py --xmi out/porte/mongo_northwind.xmi
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from pyecore.ecore import EObject

from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XMI = ROOT / "resources" / "mongodb" / "model_northwind.xmi"

EXPECTED_ENTITIES = 19
EXPECTED_ROOTS = 17
EXPECTED_NON_ROOT = frozenset({"_id", "Detail"})

AGGREGATING = ("Orders", "Purchase_orders")
AGGREGATED = "Detail"


@dataclass(frozen=True)
class Check:
    """Uma afirmação verificada.

    Parameters
    ----------
    name : str
        O invariante, em uma linha.
    passed : bool
        Se a afirmação se sustentou no modelo lido.
    detail : str
        O que se esperava e o que se achou — é o que vai para o relatório,
        então tem de ser legível sem abrir o XMI.
    """

    name: str
    passed: bool
    detail: str


def check_entities(schema: EObject) -> list[Check]:
    """Verificar a contagem de entidades e a partição raiz / não-raiz.

    Parameters
    ----------
    schema : EObject
        Raiz ``USchema`` já carregada.

    Returns
    -------
    list of Check
        Três afirmações: total de entidades, quantas são raiz, e quais são os
        nomes das não-raiz.
    """
    entities: list[EObject] = list(schema.entities)

    roots = [entity for entity in entities if bool(entity.root)]
    non_root_names = sorted(str(entity.name) for entity in entities if not bool(entity.root))

    return [
        Check(
            name="total de EntityType",
            passed=len(entities) == EXPECTED_ENTITIES,
            detail=f"esperado {EXPECTED_ENTITIES}, achado {len(entities)}",
        ),
        Check(
            name="EntityType raiz",
            passed=len(roots) == EXPECTED_ROOTS,
            detail=f"esperado {EXPECTED_ROOTS}, achado {len(roots)}",
        ),
        Check(
            name="EntityType não-raiz",
            passed=set(non_root_names) == set(EXPECTED_NON_ROOT),
            detail=f"esperado {sorted(EXPECTED_NON_ROOT)}, achado {non_root_names}",
        ),
    ]


def find_entity(schema: EObject, name: str) -> EObject | None:
    """Achar uma entidade pelo nome exato, ou ``None`` se não existir."""
    return next((entity for entity in schema.entities if str(entity.name) == name), None)


def aggregates_to(entity: EObject, target: str) -> list[EObject]:
    """Listar os ``Aggregate`` de ``entity`` que agregam variações de ``target``.

    Um ``Aggregate`` não aponta para o ``EntityType``: ele guarda em
    ``aggregates`` as **StructuralVariation** agregadas (``upperBound=-1`` no
    ecore, então são várias). Quem devolve a entidade é o ``container`` da
    variação — o mesmo caminho que ``_same_container`` percorre no harness da
    Fase 0.3.

    Parameters
    ----------
    entity : EObject
        A entidade agregadora (``Orders``, ``Purchase_orders``).
    target : str
        Nome da entidade agregada (``Detail``).

    Returns
    -------
    list of EObject
        Os ``Aggregate`` encontrados, em ordem de variação.
    """
    return [
        feature
        for variation in entity.variations
        for feature in variation.features
        if feature.eClass.name == "Aggregate"
        and any(
            aggregated.container is not None and str(aggregated.container.name) == target
            for aggregated in feature.aggregates
        )
    ]


def check_detail_aggregate(schema: EObject) -> list[Check]:
    """Verificar o ``Aggregate`` de ``Orders``/``Purchase_orders`` para ``Detail``.

    Parameters
    ----------
    schema : EObject
        Raiz ``USchema`` já carregada.

    Returns
    -------
    list of Check
        Uma afirmação por entidade agregadora: existe um ``Aggregate`` que
        chega em ``Detail``, e ele é ``upperBound == -1`` e ``optional``.
    """
    checks = []

    for name in AGGREGATING:
        entity = find_entity(schema, name)

        if entity is None:
            checks.append(
                Check(
                    name=f"{name} agrega {AGGREGATED}",
                    passed=False,
                    detail=f"entidade {name} não existe no modelo",
                )
            )
            continue

        found = aggregates_to(entity, AGGREGATED)

        # (upperBound, optional) de cada Aggregate achado — é o que o
        # invariante afirma, e o que o relatório precisa mostrar quando falha.
        shapes = [(int(feature.upperBound), bool(feature.optional)) for feature in found]

        checks.append(
            Check(
                name=f"{name} agrega {AGGREGATED} com upperBound=-1 e optional=true",
                passed=bool(shapes) and all(shape == (-1, True) for shape in shapes),
                detail=(
                    f"{len(found)} Aggregate(s) para {AGGREGATED}; "
                    f"(upperBound, optional) = {shapes}"
                ),
            )
        )

    return checks


def main() -> None:
    """Ler o XMI, rodar as checagens e sair diferente de zero se alguma falhar."""
    ap = argparse.ArgumentParser(description="Invariantes do Northwind (Fase 3.1)")
    ap.add_argument("--xmi", type=Path, default=DEFAULT_XMI)

    args = ap.parse_args()

    schema = load_model(args.xmi, load_metamodel())

    print(f"== {args.xmi} ==")

    checks = [*check_entities(schema), *check_detail_aggregate(schema)]

    for check in checks:
        print(f"  [{'ok ' if check.passed else 'FALHA'}] {check.name}: {check.detail}")

    failed = [check for check in checks if not check.passed]

    if failed:
        raise SystemExit(f"\n{len(failed)} de {len(checks)} invariantes não se sustentaram.")

    print(f"\n{len(checks)} invariantes confirmados.")


if __name__ == "__main__":
    main()
