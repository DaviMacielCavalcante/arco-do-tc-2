"""Bateria de escala do paradigma grafo (Fase 3.2).

Por escala: limpa, regera com semente fixa, extrai pelo driver nativo,
constrói pelo núcleo próprio do Neo4j e compara com o XMI-oráculo. Uma linha
de CSV por entidade.

Destrutiva: cada escala apaga o grafo anterior, e o Community tem um banco só,
então as escalas não coexistem nem podem ser paralelizadas. Não rode
concorrente com a bateria do Mongo — os servidores disputam CPU e disco, e os
tempos vão para o capítulo. Contexto em `todolist_fase3.md` §3.1 e §3.2.

    uv run python scripts/run_scale_neo4j.py --seed 23
    uv run python scripts/run_scale_neo4j.py --seed 69 --scales small medium
"""

import argparse
import csv
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from pyecore.ecore import EPackage

from uschema.extractors.neo4j import extract_database_archetype_counts
from uschema.extractors.neo4j_model import build_uschema_from_archetypes
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model, save_model
from uschema.validation.equivalence import compare

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

CSV_HEADER = [
    "seed",
    "escala",
    "t_limpeza",
    "t_geracao",
    "t_extracao",
    "t_inferencia",
    "arquetipos",
    "entidade",
    "real",
    "modelo",
    "capturado",
    "equivalente",
    "divergencias",
]


@dataclass(frozen=True)
class ScaleResult:
    """Uma corrida completa numa escala."""

    scale: str
    t_cleanup: float
    t_generation: float
    t_extraction: float
    t_inference: float
    archetypes: int
    counts: dict[str, tuple[int, int]]
    equivalent: bool
    divergences: int


def check_header(output: Path) -> bool:
    """Recusa append num CSV de esquema antigo; True se o arquivo é novo."""
    if not output.exists():
        return True

    with open(output, newline="") as file:
        current = next(csv.reader(file), [])

    if current != CSV_HEADER:
        raise SystemExit(
            f"{output} tem cabeçalho incompatível.\n"
            f"  esperado: {','.join(CSV_HEADER)}\n"
            f"  achado:   {','.join(current)}\n"
            "Renomeie o arquivo antigo ou use --output."
        )

    return False


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


def measure(scale: str, uri: str, pkg: EPackage) -> ScaleResult:
    """Extrai, constrói e compara com o XMI-oráculo da escala."""
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

    name = ORACLE[scale]

    start = time.perf_counter()

    port = build_uschema_from_archetypes(pkg, name, rows)

    t_inference = time.perf_counter() - start

    save_model(port, XMI_OUTPUT / f"neo4j_{name}.xmi")

    result = compare(load_model(ROOT / "resources" / "neo4j" / f"{name}.xmi", pkg), port)

    return ScaleResult(
        scale=scale,
        t_cleanup=0.0,
        t_generation=0.0,
        t_extraction=t_extraction,
        t_inference=t_inference,
        archetypes=len(rows),
        counts={label: (actual[label], sum_by_label(rows, label)) for label in LABELS},
        equivalent=result.equivalent,
        divergences=len(result.divergences),
    )


def write_rows(writer: Any, seed: int, result: ScaleResult) -> None:
    """Grava uma linha de CSV por entidade medida."""
    for entity, (actual, model) in result.counts.items():
        writer.writerow(
            [
                seed,
                result.scale,
                f"{result.t_cleanup:.2f}",
                f"{result.t_generation:.2f}",
                f"{result.t_extraction:.2f}",
                f"{result.t_inference:.2f}",
                result.archetypes,
                entity,
                actual,
                model,
                f"{model / actual:.4f}" if actual else "",
                result.equivalent,
                result.divergences,
            ]
        )


def main() -> None:
    """Roda a bateria nas escalas pedidas e acumula o CSV."""
    ap = argparse.ArgumentParser(description="Bateria de escala do Neo4j (Fase 3.2)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--scales", nargs="+", choices=list(ORACLE), default=DEFAULT_SCALES)
    ap.add_argument("--output", type=Path, default=ROOT / "resultados" / "escala_neo4j.csv")

    args = ap.parse_args()

    pkg = load_metamodel()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    XMI_OUTPUT.mkdir(parents=True, exist_ok=True)

    is_new = check_header(args.output)

    with open(args.output, "a", newline="") as file:
        writer = csv.writer(file)

        if is_new:
            writer.writerow(CSV_HEADER)

        for scale in args.scales:
            print(f"\n=== seed {args.seed} | escala {scale} ===")

            t_cleanup, t_generation = generate(scale, args.uri, args.seed)

            result = replace(
                measure(scale, args.uri, pkg), t_cleanup=t_cleanup, t_generation=t_generation
            )

            print(
                f"  limpeza={result.t_cleanup:.2f}s"
                f"  geracao={result.t_generation:.2f}s"
                f"  extracao={result.t_extraction:.2f}s"
                f"  inferencia={result.t_inference:.2f}s"
                f"  arquetipos={result.archetypes}"
                f"  equivalente={result.equivalent}"
                f"  divergencias={result.divergences}"
            )

            for entity, (actual, model) in result.counts.items():
                print(f"    {entity}: real={actual} modelo={model} ({model / actual:.1%})")

            write_rows(writer, args.seed, result)

            file.flush()

    print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
