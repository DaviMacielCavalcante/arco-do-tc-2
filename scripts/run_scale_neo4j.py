"""Bateria de escala do paradigma grafo (Fase 3.2).

Por escala: limpa, regera com semente fixa, extrai pelo driver nativo,
constrói pelo núcleo próprio do Neo4j e compara com o XMI-oráculo de
`resources/neo4j/`. Grava nas quatro tabelas de `scripts/output.py`.

Destrutiva: cada escala apaga o grafo anterior, e o Community tem um banco só,
então as escalas não coexistem nem podem ser paralelizadas. Não rode
concorrente com a bateria do Mongo — os servidores disputam CPU e disco, e os
tempos são resultado. Contexto em `todolist_fase3.md` §3.1 e §3.2.

    uv run python scripts/run_scale_neo4j.py --seed 23
    uv run python scripts/run_scale_neo4j.py --seed 69 --scales small medium
"""

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from pyecore.ecore import EPackage

from output import Results, run_id
from uschema.extractors.neo4j import extract_database_archetype_counts
from uschema.extractors.neo4j_model import build_uschema_from_archetypes
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model, save_model
from uschema.validation.equivalence import ComparisonResult, compare

ORACLE = {
    "small": "movies_min",
    "medium": "up_medium",
    "large": "up_large",
    "larger": "up_larger",
}

DEFAULT_SCALES = ["small", "medium", "large", "larger"]

LABELS = ("User", "Movie")

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "gen_userprofiles_neo4j.py"
CLEANER = ROOT / "scripts" / "clean_databases.py"
XMI_OUTPUT = ROOT / "out" / "porte"


@dataclass(frozen=True)
class ScaleResult:
    """Uma corrida completa numa escala."""

    scale: str
    schema: str
    t_cleanup: float
    t_generation: float
    t_extraction: float
    t_inference: float
    archetypes: int
    counts: dict[str, tuple[int, int]]
    result: ComparisonResult


def generate(scale: str, uri: str, seed: int) -> tuple[float, float]:
    """Limpa e regera o grafo, cronometrando as duas etapas separadamente."""
    start = time.perf_counter()

    subprocess.run(
        [sys.executable, str(CLEANER), "--only", "neo4j", "--uri-neo4j", uri],
        check=True,
    )

    t_cleanup = time.perf_counter() - start

    start = time.perf_counter()

    subprocess.run(
        [sys.executable, str(GENERATOR), "--size", scale, "--uri", uri, "--seed", str(seed)],
        check=True,
    )

    return t_cleanup, time.perf_counter() - start


def sum_by_label(rows: list[dict[str, Any]], label: str) -> int:
    """Soma os counts dos arquétipos de nó com exatamente este label."""
    # A extração devolve nós e relacionamentos na mesma lista; sem o filtro por
    # "node" o total misturaria WATCHED/FAVORITE com User.
    return sum(
        row["count"]
        for row in rows
        if row["archetype"]["entity"] == "node" and row["archetype"]["labels"] == [label]
    )


def measure(scale: str, uri: str, seed: int, pkg: EPackage) -> ScaleResult:
    """Extrai, constrói e compara com o XMI-oráculo da escala."""
    schema = ORACLE[scale]

    with GraphDatabase.driver(uri, auth=None) as driver:
        actual = {
            label: int(
                driver.execute_query(f"MATCH (n:{label}) RETURN count(n) AS total").records[0][
                    "total"
                ]
            )
            for label in LABELS
        }

        start = time.perf_counter()

        rows: list[dict[str, Any]] = extract_database_archetype_counts(driver)

        t_extraction = time.perf_counter() - start

    start = time.perf_counter()

    port = build_uschema_from_archetypes(pkg, schema, rows)

    t_inference = time.perf_counter() - start

    save_model(port, XMI_OUTPUT / f"neo4j_{schema}_seed{seed}.xmi")

    return ScaleResult(
        scale=scale,
        schema=schema,
        t_cleanup=0.0,
        t_generation=0.0,
        t_extraction=t_extraction,
        t_inference=t_inference,
        archetypes=len(rows),
        counts={label: (actual[label], sum_by_label(rows, label)) for label in LABELS},
        result=compare(load_model(ROOT / "resources" / "neo4j" / f"{schema}.xmi", pkg), port),
    )


def record(tables: Results, seed: int, run: ScaleResult) -> None:
    """Distribui a corrida pelas quatro tabelas."""
    key = run_id("escala", "neo4j", run.schema, seed=seed)

    tables.add_run(
        {
            "corrida_id": key,
            "bateria": "escala",
            "paradigma": "neo4j",
            "semente": seed,
            "escala": run.scale,
            "alvo": run.schema,
            "origem": "banco",
            "t_limpeza": f"{run.t_cleanup:.2f}",
            "t_geracao": f"{run.t_generation:.2f}",
            "t_extracao": f"{run.t_extraction:.2f}",
            "t_inferencia": f"{run.t_inference:.2f}",
            "arquetipos": run.archetypes,
        }
    )

    for entity, (actual, model) in run.counts.items():
        tables.add_entity(key, entity, actual, model)

    tables.add_comparison(key, "resources", run.result.equivalent, len(run.result.divergences))

    for divergence in run.result.divergences:
        tables.add_divergence(key, "resources", divergence.category.value, divergence.message)


def main() -> None:
    """Roda a bateria nas escalas pedidas e acumula as tabelas."""
    ap = argparse.ArgumentParser(description="Bateria de escala do Neo4j (Fase 3.2)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--scales", nargs="+", choices=list(ORACLE), default=DEFAULT_SCALES)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "results")

    args = ap.parse_args()

    pkg = load_metamodel()

    XMI_OUTPUT.mkdir(parents=True, exist_ok=True)

    with Results(args.output_dir) as tables:
        for scale in args.scales:
            print(f"\n=== seed {args.seed} | escala {scale} ===", flush=True)

            t_cleanup, t_generation = generate(scale, args.uri, args.seed)

            run = replace(
                measure(scale, args.uri, args.seed, pkg),
                t_cleanup=t_cleanup,
                t_generation=t_generation,
            )

            print(
                f"  limpeza={run.t_cleanup:.2f}s"
                f"  geracao={run.t_generation:.2f}s"
                f"  extracao={run.t_extraction:.2f}s"
                f"  inferencia={run.t_inference:.2f}s"
                f"  arquetipos={run.archetypes}"
                f"  equivalente={run.result.equivalent}"
                f"  divergencias={len(run.result.divergences)}",
                flush=True,
            )

            for entity, (actual, model) in run.counts.items():
                print(f"    {entity}: real={actual} modelo={model} ({model / actual:.1%})")

            record(tables, args.seed, run)

    print(f"\n-> {args.output_dir}")


if __name__ == "__main__":
    main()
