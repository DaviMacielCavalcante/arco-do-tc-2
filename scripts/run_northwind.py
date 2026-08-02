"""Corretude do Northwind pelos dois caminhos de leitura (Fase 3.1).

Roda o mesmo dataset por **arquivo** (os 17 JSONs, sem banco) e por **banco**
(o MongoDB carregado, pelo cursor do `pymongo`), constrói o USchema em cada
caminho e compara com `resources/mongodb/model_northwind.xmi`. Grava nas
tabelas de `scripts/output.py`, com a coluna `origem` distinguindo os dois.

Por que os dois caminhos: o bug #8 é sensível à **ordem de leitura**, então o
número de divergências muda conforme a origem do dado. O invariante citável não
é esse número, e sim `equivalent=True` mais a fração de coleções cujo `count`
fecha — que este script mede e imprime.

Os JSONs são JSONL em extended JSON (`{"$date": ...}`), então a leitura usa
`bson.json_util.loads`: com `json.load` puro o `$date` viraria um objeto
aninhado e o modelo ganharia uma entidade que o oráculo não tem.

Os JSONs estão versionados em `resources/datasets/northwind/` (BSD 2-Clause,
proveniência no README de lá), então o caminho de arquivo roda sem banco e sem
dependência externa.

    uv run python scripts/run_northwind.py
    uv run python scripts/run_northwind.py --json-dir /outro/caminho
"""

import argparse
import hashlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bson import json_util
from pyecore.ecore import EPackage
from pymongo import MongoClient

from output import Results, run_id
from uschema.extractors.mongo import build_triples, extract_database_triples
from uschema.extractors.triple import triples_from_rows
from uschema.inference.build_uschema import BuildUSchema
from uschema.metamodel.registry import load_metamodel
from uschema.metamodel.xmi import load_model, save_model
from uschema.naming.inflector import Inflector
from uschema.validation.equivalence import ComparisonResult, compare

ROOT = Path(__file__).resolve().parents[1]
ORACLE_XMI = ROOT / "resources" / "mongodb" / "model_northwind.xmi"
XMI_OUTPUT = ROOT / "out" / "porte"
DEFAULT_JSON_DIR = ROOT / "resources" / "datasets" / "northwind"

SCHEMA_NAME = "northwind"


@dataclass(frozen=True)
class Run:
    """Uma leitura completa do Northwind por um caminho."""

    origin: str
    t_extraction: float
    t_inference: float
    triple_rows: int
    counts: dict[str, tuple[int, int]]
    result: ComparisonResult

    @property
    def closing(self) -> int:
        """Quantas coleções têm o `count` do modelo igual ao real."""
        return sum(1 for actual, model in self.counts.values() if actual == model)


def digest(json_dir: Path) -> str:
    """SHA-256 do conteúdo dos JSONs, em ordem de nome.

    Prende a corrida a uma versão do dataset — que é versionado no repo mas não
    tem outro identificador de conteúdo.
    """
    sha = hashlib.sha256()

    for path in sorted(json_dir.glob("*.json")):
        sha.update(path.name.encode())
        sha.update(path.read_bytes())

    return sha.hexdigest()


def read_files(json_dir: Path) -> tuple[list[dict[str, Any]], dict[str, int], float]:
    """Ler os JSONs do disco e montar as triplas, sem banco no meio."""
    rows: list[dict[str, Any]] = []
    actual: dict[str, int] = {}

    start = time.perf_counter()

    for path in sorted(json_dir.glob("*.json")):
        documents = [
            json_util.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]

        actual[path.stem] = len(documents)
        rows.extend(build_triples(documents, path.stem))

    return rows, actual, time.perf_counter() - start


def read_database(uri: str, name: str) -> tuple[list[dict[str, Any]], dict[str, int], float]:
    """Ler o banco pelo cursor do `pymongo` e montar as triplas."""
    # Mapping, não dict: Database é invariante no parâmetro de tipo.
    client: MongoClient[Mapping[str, Any]] = MongoClient(uri)

    try:
        database = client[name]

        collections = sorted(database.list_collection_names())

        actual = {name: database[name].count_documents({}) for name in collections}

        start = time.perf_counter()

        rows = extract_database_triples(database, collections)

        return rows, actual, time.perf_counter() - start

    finally:
        client.close()


def evaluate(
    pkg: EPackage,
    origin: str,
    rows: list[dict[str, Any]],
    actual: dict[str, int],
    t_extraction: float,
) -> Run:
    """Construir o USchema a partir das triplas e comparar com o oráculo."""
    inflector = Inflector()

    start = time.perf_counter()

    port = BuildUSchema(pkg).build_from_rows(SCHEMA_NAME, triples_from_rows(rows))

    t_inference = time.perf_counter() - start

    save_model(port, XMI_OUTPUT / f"mongo_northwind_{origin}.xmi")

    in_model = {entity.name: sum(v.count for v in entity.variations) for entity in port.entities}

    return Run(
        origin=origin,
        t_extraction=t_extraction,
        t_inference=t_inference,
        triple_rows=len(rows),
        counts={
            name: (total, in_model.get(inflector.capitalize(name), 0))
            for name, total in actual.items()
        },
        result=compare(load_model(ORACLE_XMI, pkg), port),
    )


def record(tables: Results, run: Run) -> None:
    """Distribui a corrida pelas quatro tabelas."""
    key = run_id("corretude", "mongodb", SCHEMA_NAME, origin=run.origin)

    tables.add_run(
        {
            "corrida_id": key,
            "bateria": "corretude",
            "paradigma": "mongodb",
            "alvo": SCHEMA_NAME,
            "origem": run.origin,
            "t_extracao": f"{run.t_extraction:.2f}",
            "t_inferencia": f"{run.t_inference:.2f}",
            "linhas_tripla": run.triple_rows,
        }
    )

    for entity, (actual, model) in run.counts.items():
        tables.add_entity(key, entity, actual, model)

    tables.add_comparison(key, "resources", run.result.equivalent, len(run.result.divergences))

    for divergence in run.result.divergences:
        tables.add_divergence(key, "resources", divergence.category.value, divergence.message)


def report(run: Run) -> None:
    """Imprimir o veredito, a fração que fecha e as coleções que não fecham."""
    print(f"\n=== origem: {run.origin} ===")
    print(f"  extracao={run.t_extraction:.2f}s  inferencia={run.t_inference:.2f}s")
    print(f"  linhas de tripla: {run.triple_rows}")
    print(f"  equivalente={run.result.equivalent}  divergências={len(run.result.divergences)}")
    print(f"  coleções fechando a contagem: {run.closing}/{len(run.counts)}")

    for name, (actual, model) in sorted(run.counts.items()):
        if actual != model:
            print(f"    {name}: real={actual} modelo={model}")


def main() -> None:
    """Rodar os dois caminhos e acumular as tabelas."""
    ap = argparse.ArgumentParser(description="Corretude do Northwind (Fase 3.1)")
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    ap.add_argument("--db", default=SCHEMA_NAME)
    ap.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "results")

    args = ap.parse_args()

    if not args.json_dir.is_dir():
        raise SystemExit(f"--json-dir não existe: {args.json_dir}")

    pkg = load_metamodel()

    XMI_OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"dataset: {args.json_dir}\nsha256:  {digest(args.json_dir)}")

    file_rows, file_actual, t_file = read_files(args.json_dir)
    database_rows, database_actual, t_database = read_database(args.uri, args.db)

    runs = [
        evaluate(pkg, "arquivo", file_rows, file_actual, t_file),
        evaluate(pkg, "banco", database_rows, database_actual, t_database),
    ]

    with Results(args.output_dir) as tables:
        for run in runs:
            report(run)
            record(tables, run)

    print(f"\n-> {args.output_dir}")


if __name__ == "__main__":
    main()
