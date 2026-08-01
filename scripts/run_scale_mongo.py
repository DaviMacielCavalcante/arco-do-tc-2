"""Bateria de escala do paradigma documento (Fase 3.2).

Por rota (A/B) e tamanho: regera o banco com semente fixa, extrai as triplas
pelo driver nativo, alimenta o núcleo da Fase 1 e mede quanto da massa real
sobrevive ao bug #8.

Não há `compare()` aqui: não existe XMI-oráculo do User Profiles em documento.
O gate de corretude do paradigma é o Northwind; esta bateria produz tempo e
contagem. A coluna `capturado` é o número central da 3.3 — `Movie` não tem
array de tamanho variável e serve de controle, tem de dar 100%.

Destrutiva: cada corrida dropa e regera o banco alvo. Não rode concorrente com
a bateria do Neo4j. Contexto em `todolist_fase3.md` §3.2 e §3.3.

    uv run python scripts/run_scale_mongo.py --seed 23
    uv run python scripts/run_scale_mongo.py --seed 69 --routes A --sizes small
"""

import argparse
import csv
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pyecore.ecore import EPackage
from pymongo import MongoClient

from uschema.extractors.mongo import extract_database_triples
from uschema.extractors.triple import triples_from_rows
from uschema.inference.build_uschema import BuildUSchema
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import save_model
from uschema.naming.inflector import Inflector

DEFAULT_SIZES = ["small", "medium", "large", "larger"]
DEFAULT_ROUTES = ["A", "B"]

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "gen_userprofiles.py"
XMI_OUTPUT = ROOT / "out" / "porte"

CSV_HEADER = [
    "seed",
    "banco",
    "rota",
    "tamanho",
    "t_geracao",
    "t_extracao",
    "t_inferencia",
    "linhas_tripla",
    "entidade",
    "real",
    "modelo",
    "capturado",
]


@dataclass(frozen=True)
class DatabaseResult:
    """Uma corrida completa sobre um banco."""

    database: str
    route: str
    size: str
    t_generation: float
    t_extraction: float
    t_inference: float
    triple_rows: int
    counts: dict[str, tuple[int, int]]


def database_name(route: str, size: str) -> str:
    """Monta o nome do banco no padrão já usado no repositório."""
    return f"up_{route.lower()}_{size}"


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


def generate(route: str, size: str, uri: str, seed: int) -> float:
    """Regera o banco da combinação pedida e devolve o tempo gasto."""
    start = time.perf_counter()

    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--route",
            route,
            "--size",
            size,
            "--db",
            database_name(route, size),
            "--uri",
            uri,
            "--seed",
            str(seed),
            "--drop",
        ],
        check=True,
    )

    return time.perf_counter() - start


def measure(route: str, size: str, uri: str, pkg: EPackage) -> DatabaseResult:
    """Extrai as triplas, constrói o USchema e mede o alcance do #8."""
    database = database_name(route, size)

    inflector = Inflector()

    # Mapping, não dict: Database é invariante no parâmetro de tipo.
    client: MongoClient[Mapping[str, Any]] = MongoClient(uri)

    try:
        db = client[database]

        collections = sorted(db.list_collection_names())

        actual = {name: db[name].count_documents({}) for name in collections}

        start = time.perf_counter()

        rows: list[dict[str, Any]] = extract_database_triples(db, collections)

        t_extraction = time.perf_counter() - start

    finally:
        client.close()

    start = time.perf_counter()

    port = BuildUSchema(pkg).build_from_rows(database, triples_from_rows(rows))

    t_inference = time.perf_counter() - start

    save_model(port, XMI_OUTPUT / f"mongo_{database}.xmi")

    in_model = {entity.name: sum(v.count for v in entity.variations) for entity in port.entities}

    return DatabaseResult(
        database=database,
        route=route,
        size=size,
        t_generation=0.0,
        t_extraction=t_extraction,
        t_inference=t_inference,
        triple_rows=len(rows),
        counts={
            name: (actual[name], in_model.get(inflector.capitalize(name), 0))
            for name in collections
        },
    )


def write_rows(writer: Any, seed: int, result: DatabaseResult) -> None:
    """Grava uma linha de CSV por entidade medida."""
    for entity, (actual, model) in result.counts.items():
        writer.writerow(
            [
                seed,
                result.database,
                result.route,
                result.size,
                f"{result.t_generation:.2f}",
                f"{result.t_extraction:.2f}",
                f"{result.t_inference:.2f}",
                result.triple_rows,
                entity,
                actual,
                model,
                f"{model / actual:.4f}" if actual else "",
            ]
        )


def main() -> None:
    """Roda a bateria nas combinações pedidas e acumula o CSV."""
    ap = argparse.ArgumentParser(description="Bateria de escala do MongoDB (Fase 3.2)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    ap.add_argument("--routes", nargs="+", choices=DEFAULT_ROUTES, default=DEFAULT_ROUTES)
    ap.add_argument("--sizes", nargs="+", choices=DEFAULT_SIZES, default=DEFAULT_SIZES)
    ap.add_argument("--output", type=Path, default=ROOT / "resultados" / "escala_mongo.csv")

    args = ap.parse_args()

    pkg = load_metamodel()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    XMI_OUTPUT.mkdir(parents=True, exist_ok=True)

    is_new = check_header(args.output)

    with open(args.output, "a", newline="") as file:
        writer = csv.writer(file)

        if is_new:
            writer.writerow(CSV_HEADER)

        for route in args.routes:
            for size in args.sizes:
                print(f"\n=== seed {args.seed} | rota {route} | {size} ===")

                t_generation = generate(route, size, args.uri, args.seed)

                result = replace(measure(route, size, args.uri, pkg), t_generation=t_generation)

                print(
                    f"  geracao={result.t_generation:.2f}s"
                    f"  extracao={result.t_extraction:.2f}s"
                    f"  inferencia={result.t_inference:.2f}s"
                    f"  triplas={result.triple_rows}"
                )

                for entity, (actual, model) in result.counts.items():
                    print(f"    {entity}: real={actual} modelo={model} ({model / actual:.1%})")

                write_rows(writer, args.seed, result)

                file.flush()

    print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
