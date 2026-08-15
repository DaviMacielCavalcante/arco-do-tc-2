"""Bateria por tamanho do paradigma grafo (Fase 3.2).

Por tamanho: limpa, regera com semente fixa, extrai pelo driver nativo,
constrói pelo núcleo próprio do Neo4j e compara com o XMI-oráculo de
`resources/neo4j/`. Grava nas quatro tabelas de `scripts/output.py`.

Destrutiva: cada tamanho apaga o grafo anterior, e o Community tem um banco só,
então os tamanhos não coexistem nem podem ser paralelizados. Não rode
concorrente com a bateria do Mongo — os servidores disputam CPU e disco, e os
tempos são resultado. Contexto em `todolist_fase3.md` §3.1 e §3.2.

    uv run python scripts/run_size_neo4j.py --seed 23
    uv run python scripts/run_size_neo4j.py --seed 69 --sizes small medium
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from pyecore.ecore import EPackage

from baseline import neo4j_query_time
from output import PORT, RESOURCES, Results, modeled_counts, normalized, run_id
from runs import Neo4jSizeRun
from uschema.extractors.neo4j import extract_database_archetype_counts
from uschema.extractors.neo4j_model import build_uschema_from_archetypes
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model, save_model
from uschema.validation.equivalence import compare

SCHEMA_BY_SIZE = {
    "small": "movies_min",
    "medium": "up_medium",
    "large": "up_large",
    "larger": "up_larger",
}

DEFAULT_SIZES = ["small", "medium", "large", "larger"]

LABELS = ("User", "Movie")

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "gen_userprofiles_neo4j.py"
CLEANER = ROOT / "scripts" / "clean_databases.py"
XMI_OUTPUT = ROOT / "out" / "porte"

#: Semente padrão das baterias. Sobrescrevível com `--seed`; fixa por padrão
#: para que a corrida seja reproduzível sem o operador ter de lembrar do valor.
DEFAULT_SEED = 23


def generate(size: str, uri: str, seed: int) -> tuple[float, float]:
    """Limpa o grafo anterior e regera o do tamanho pedido.

    Returns
    -------
    tuple of (float, float)
        Tempo de limpeza e tempo de geração.
    """
    start = time.perf_counter()

    subprocess.run(
        [sys.executable, str(CLEANER), "--only", "neo4j", "--uri-neo4j", uri],
        check=True,
    )

    t_cleanup = time.perf_counter() - start

    start = time.perf_counter()

    subprocess.run(
        [sys.executable, str(GENERATOR), "--size", size, "--uri", uri, "--seed", str(seed)],
        check=True,
    )

    return t_cleanup, time.perf_counter() - start


def measure(size: str, uri: str, seed: int, pkg: EPackage) -> Neo4jSizeRun:
    """Extrai, constrói e compara com o XMI-oráculo do tamanho."""
    schema = SCHEMA_BY_SIZE[size]

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

    start = time.perf_counter()

    save_model(port, XMI_OUTPUT / f"neo4j_{schema}_seed{seed}.xmi")

    t_write = time.perf_counter() - start

    # A query de referência roda por último: antes, aqueceria o cache e
    # aceleraria a extração medida. Ver `baseline.py`.
    with GraphDatabase.driver(uri, auth=None) as driver:
        t_query = neo4j_query_time(driver)

    in_port = modeled_counts(port)

    return Neo4jSizeRun(
        size=size,
        schema=schema,
        t_extraction=t_extraction,
        t_inference=t_inference,
        t_write=t_write,
        t_query=t_query,
        counts={label: (actual[label], in_port.get(label, 0)) for label in LABELS},
        result=compare(load_model(ROOT / "resources" / "neo4j" / f"{schema}.xmi", pkg), port),
    )


def record(tables: Results, seed: int, run: Neo4jSizeRun) -> None:
    """Distribui a corrida pelas tabelas de resultado.

    Só o porte produz linha aqui: esta bateria compara com o XMI publicado em
    `resources/`, não roda o oráculo.
    """
    key = run_id("size", "neo4j", run.schema, seed=seed)

    tables.add_run(
        {
            "run_id": key,
            "experiment": "size",
            "size": run.size,
            "paradigm": "neo4j",
            "target": run.schema,
            "origin": "database",
            "total_time": f"{run.total:.2f}",
            "extraction_time": f"{run.t_extraction:.2f}",
            "inference_time": f"{run.t_inference:.2f}",
            "write_time": f"{run.t_write:.2f}",
            "query_time": f"{run.t_query:.4f}",
            "normalized": normalized(run.total, run.t_query),
        }
    )

    tables.add_comparison(key, PORT, RESOURCES, run.result)


def main() -> None:
    """Roda a bateria nos tamanhos pedidos e acumula as tabelas."""
    ap = argparse.ArgumentParser(description="Bateria por tamanho do Neo4j (Fase 3.2)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--sizes", nargs="+", choices=list(SCHEMA_BY_SIZE), default=DEFAULT_SIZES)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "results")

    args = ap.parse_args()

    pkg = load_metamodel()

    XMI_OUTPUT.mkdir(parents=True, exist_ok=True)

    with Results(args.output_dir) as tables:
        for size in args.sizes:
            print(f"\n=== seed {args.seed} | tamanho {size} ===", flush=True)

            # Limpeza e geração são cronometradas só para o log: nenhuma das
            # duas é medida do porte nem do oráculo, e as duas saíram dos CSVs.
            t_cleanup, t_generation = generate(size, args.uri, args.seed)

            run = measure(size, args.uri, args.seed, pkg)

            print(
                f"  limpeza={t_cleanup:.2f}s"
                f"  geracao={t_generation:.2f}s"
                f"  extracao={run.t_extraction:.2f}s"
                f"  inferencia={run.t_inference:.2f}s"
                f"  escrita={run.t_write:.2f}s"
                f"  total={run.total:.2f}s"
                f"  query={run.t_query:.2f}s"
                f"  norm={normalized(run.total, run.t_query)}x"
                f"  equivalente={run.result.equivalent}"
                f"  divergencias={len(run.result.divergences)}",
                flush=True,
            )

            for entity, (actual, model) in run.counts.items():
                print(f"    {entity}: real={actual} modelo={model} ({model / actual:.1%})")

            record(tables, args.seed, run)


if __name__ == "__main__":
    main()
