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

# Uma linha por corrida: tempos dos dois lados sobre a mesma instância.
RUN_HEADER = [
    "seed",
    "escala",
    "schema",
    "t_limpeza",
    "t_geracao",
    "t_extracao_porte",
    "t_inferencia_porte",
    "t_oraculo",
    "arquetipos",
    "user_real",
    "user_modelo",
    "movie_real",
    "movie_modelo",
    "equivalente_oraculo",
    "divergencias_oraculo",
    "equivalente_resources",
    "divergencias_resources",
]

# Uma linha por divergência (ou uma linha vazia quando não houve nenhuma). O
# formato de `roteiro_experimental.md` §6-7 nunca chegou a este repositório
# (`todolist_fase3.md` §3.0); este é o esquema que passa a valer, com `origem`,
# `semente` e `referencia` acrescentados — sem eles a linha não é rastreável até
# a corrida que a produziu, e o #8 é sensível ao caminho de leitura.
EQUIVALENCE_HEADER = [
    "dataset",
    "paradigma",
    "origem",
    "semente",
    "referencia",
    "equivalente",
    "n_divergencias",
    "categoria",
    "mensagem",
]


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


def check_header(output: Path, header: list[str]) -> bool:
    """Recusa append num CSV de esquema antigo; True se o arquivo é novo.

    Arquivo de zero byte conta como novo: não tem esquema com que conflitar, e
    é o que sobra de uma corrida interrompida antes do primeiro `flush`.
    """
    if not output.exists() or output.stat().st_size == 0:
        return True

    with open(output, newline="") as file:
        current = next(csv.reader(file), [])

    if current != header:
        raise SystemExit(
            f"{output} tem cabeçalho incompatível.\n"
            f"  esperado: {','.join(header)}\n"
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


def write_run(writer: Any, seed: int, run: OracleRun) -> None:
    """Grava a linha de corrida no CSV de tempos."""
    writer.writerow(
        [
            seed,
            run.scale,
            run.schema,
            f"{run.t_cleanup:.2f}",
            f"{run.t_generation:.2f}",
            f"{run.t_extraction:.2f}",
            f"{run.t_inference:.2f}",
            f"{run.t_oracle:.2f}",
            run.archetypes,
            run.counts["User"][0],
            run.counts["User"][1],
            run.counts["Movie"][0],
            run.counts["Movie"][1],
            run.vs_oracle.equivalent,
            len(run.vs_oracle.divergences),
            run.vs_resources.equivalent,
            len(run.vs_resources.divergences),
        ]
    )


def write_equivalence(writer: Any, seed: int, run: OracleRun) -> None:
    """Grava uma linha por divergência, para cada referência comparada."""
    for reference, result in (("oraculo_semeado", run.vs_oracle), ("resources", run.vs_resources)):
        head = [
            run.schema,
            "neo4j",
            "banco",
            seed,
            reference,
            result.equivalent,
            len(result.divergences),
        ]

        if not result.divergences:
            writer.writerow([*head, "", ""])
            continue

        for divergence in result.divergences:
            writer.writerow([*head, divergence.category.value, divergence.message])


def main() -> None:
    """Roda a cadeia porte x oráculo nas escalas pedidas e acumula os CSVs."""
    ap = argparse.ArgumentParser(description="Porte x oráculo semeado, Neo4j (Fase 3.1)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--scales", nargs="+", choices=list(ORACLE), default=DEFAULT_SCALES)
    ap.add_argument("--memory", default="6g", help="limite de memória do container")
    ap.add_argument("--output", type=Path, default=ROOT / "resultados" / "oraculo_neo4j.csv")
    ap.add_argument(
        "--output-equivalencia",
        type=Path,
        default=ROOT / "resultados" / "equivalencia.csv",
    )

    args = ap.parse_args()

    pkg = load_metamodel()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    PORT_OUTPUT.mkdir(parents=True, exist_ok=True)

    runs_new = check_header(args.output, RUN_HEADER)
    equivalence_new = check_header(args.output_equivalencia, EQUIVALENCE_HEADER)

    with (
        open(args.output, "a", newline="") as runs_file,
        open(args.output_equivalencia, "a", newline="") as equivalence_file,
    ):
        runs = csv.writer(runs_file)
        equivalence = csv.writer(equivalence_file)

        if runs_new:
            runs.writerow(RUN_HEADER)
            runs_file.flush()

        if equivalence_new:
            equivalence.writerow(EQUIVALENCE_HEADER)
            equivalence_file.flush()

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

            write_run(runs, args.seed, run)
            write_equivalence(equivalence, args.seed, run)

            runs_file.flush()
            equivalence_file.flush()

    print(f"\n-> {args.output}\n-> {args.output_equivalencia}")


if __name__ == "__main__":
    main()
