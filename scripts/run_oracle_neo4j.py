"""Bateria porte x oráculo semeado, paradigma grafo (Fase 3.1).

Por escala: limpa, regera o grafo com semente fixa, roda o **porte** (driver
nativo -> núcleo próprio do Neo4j) e o **oráculo Java em Docker** sobre a
**mesma instância**, e compara os dois XMIs. Também compara contra o XMI de
`resources/neo4j/`, que veio de uma instância de semente desconhecida — a
diferença entre as duas comparações é o resultado que a fase quer registrar.

Isto é o padrão-ouro da corretude do grafo: mesma entrada, duas implementações.
A comparação contra `resources/` acusa divergências não-fatais de `count` que
são ruído de amostragem do gerador, não defeito do porte (`todolist_fase3.md`
§3.1).

Destrutiva: cada escala apaga o grafo anterior, e o Community tem um banco só,
então as escalas não coexistem nem podem ser paralelizadas. Exige a imagem
`extrator-uschema` buildada (`docker build -t extrator-uschema oracle/`).

    uv run python scripts/run_oracle_neo4j.py --seed 23
    uv run python scripts/run_oracle_neo4j.py --seed 23 --scales larger --memory 10g
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
PORT_OUTPUT = ROOT / "out" / "porte"
ORACLE_OUTPUT = ROOT / "out" / "oraculo"
IMAGE = "extrator-uschema"


@dataclass(frozen=True)
class OracleRun:
    """Uma corrida completa numa escala, com os dois lados medidos."""

    scale: str
    schema: str
    t_cleanup: float
    t_generation: float
    t_extraction: float
    t_inference: float
    t_oracle: float
    archetypes: int
    counts: dict[str, tuple[int, int]]
    vs_oracle: ComparisonResult
    vs_resources: ComparisonResult


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


def run_oracle(schema: str, seed: int, memory: str) -> tuple[float, Path]:
    """Roda o extrator Java no container sobre o grafo já materializado.

    O `--db` é o nome do **schema**, não do banco a conectar: o
    `Neo4j2USchema.java` só o repassa para `Json2USchemaModel`, e o conector lê
    sempre o banco padrão (`oracle/README.md`). Ele precisa casar com o nome que
    o porte usa — divergência de `SCHEMA_NAME` é fatal no harness.

    Parameters
    ----------
    schema : str
        Nome do schema no modelo, e do arquivo de saída (`movies_min`, ...).
    seed : int
        Semente da instância medida; entra no nome do XMI preservado.
    memory : str
        Limite de memória do container, no formato do Docker (ex.: ``6g``).

    Returns
    -------
    tuple of (float, Path)
        Tempo de parede do container e o XMI já renomeado por semente.
    """
    ORACLE_OUTPUT.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=host",
            f"--memory={memory}",
            "-v",
            f"{ORACLE_OUTPUT}:/output",
            IMAGE,
            "--db",
            schema,
            "--kind",
            "neo4j",
        ],
        check=True,
    )

    elapsed = time.perf_counter() - start

    # O container escreve como root; renomear só exige permissão no diretório,
    # que é nosso. A semente no nome evita que a próxima corrida sobrescreva a
    # evidência desta.
    written = ORACLE_OUTPUT / f"{schema}.xmi"
    target = ORACLE_OUTPUT / f"neo4j_{schema}_seed{seed}.xmi"
    written.replace(target)

    return elapsed, target


def sum_by_label(rows: list[dict[str, Any]], label: str) -> int:
    """Soma os counts dos arquétipos de nó com exatamente este label."""
    return sum(
        row["count"]
        for row in rows
        if row["archetype"]["entity"] == "node" and row["archetype"]["labels"] == [label]
    )


def measure(scale: str, uri: str, seed: int, pkg: EPackage, memory: str) -> OracleRun:
    """Roda porte e oráculo sobre a mesma instância e compara os três XMIs."""
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

    save_model(port, PORT_OUTPUT / f"neo4j_{schema}_seed{seed}.xmi")

    t_oracle, oracle_xmi = run_oracle(schema, seed, memory)

    return OracleRun(
        scale=scale,
        schema=schema,
        t_cleanup=0.0,
        t_generation=0.0,
        t_extraction=t_extraction,
        t_inference=t_inference,
        t_oracle=t_oracle,
        archetypes=len(rows),
        counts={label: (actual[label], sum_by_label(rows, label)) for label in LABELS},
        vs_oracle=compare(load_model(oracle_xmi, pkg), port),
        vs_resources=compare(load_model(ROOT / "resources" / "neo4j" / f"{schema}.xmi", pkg), port),
    )


def record(tables: Results, seed: int, run: OracleRun) -> None:
    """Distribui a corrida pelas quatro tabelas."""
    key = run_id("oraculo", "neo4j", run.schema, seed=seed)

    tables.add_run(
        {
            "corrida_id": key,
            "bateria": "oraculo",
            "paradigma": "neo4j",
            "semente": seed,
            "escala": run.scale,
            "alvo": run.schema,
            "origem": "banco",
            "t_limpeza": f"{run.t_cleanup:.2f}",
            "t_geracao": f"{run.t_generation:.2f}",
            "t_extracao": f"{run.t_extraction:.2f}",
            "t_inferencia": f"{run.t_inference:.2f}",
            "t_oraculo": f"{run.t_oracle:.2f}",
            "arquetipos": run.archetypes,
        }
    )

    for entity, (actual, model) in run.counts.items():
        tables.add_entity(key, entity, actual, model)

    for reference, result in (
        ("oraculo_semeado", run.vs_oracle),
        ("resources", run.vs_resources),
    ):
        tables.add_comparison(key, reference, result.equivalent, len(result.divergences))

        for divergence in result.divergences:
            tables.add_divergence(key, reference, divergence.category.value, divergence.message)


def main() -> None:
    """Roda a cadeia porte x oráculo nas escalas pedidas e acumula as tabelas."""
    ap = argparse.ArgumentParser(description="Porte x oráculo semeado, Neo4j (Fase 3.1)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--scales", nargs="+", choices=list(ORACLE), default=DEFAULT_SCALES)
    ap.add_argument("--memory", default="6g", help="limite de memória do container")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "results")

    args = ap.parse_args()

    pkg = load_metamodel()

    PORT_OUTPUT.mkdir(parents=True, exist_ok=True)

    with Results(args.output_dir) as tables:
        for scale in args.scales:
            print(f"\n=== seed {args.seed} | escala {scale} ===", flush=True)

            t_cleanup, t_generation = generate(scale, args.uri, args.seed)

            run = replace(
                measure(scale, args.uri, args.seed, pkg, args.memory),
                t_cleanup=t_cleanup,
                t_generation=t_generation,
            )

            print(
                f"  limpeza={run.t_cleanup:.2f}s"
                f"  geracao={run.t_generation:.2f}s"
                f"  extracao={run.t_extraction:.2f}s"
                f"  inferencia={run.t_inference:.2f}s"
                f"  oraculo={run.t_oracle:.2f}s"
                f"  arquetipos={run.archetypes}",
                flush=True,
            )

            for entity, (actual, model) in run.counts.items():
                print(f"    {entity}: real={actual} modelo={model} ({model / actual:.1%})")

            print(
                f"    vs oráculo semeado: equivalente={run.vs_oracle.equivalent}"
                f" divergências={len(run.vs_oracle.divergences)}\n"
                f"    vs resources/:      equivalente={run.vs_resources.equivalent}"
                f" divergências={len(run.vs_resources.divergences)}",
                flush=True,
            )

            record(tables, args.seed, run)

    print(f"\n-> {args.output_dir}")


if __name__ == "__main__":
    main()
