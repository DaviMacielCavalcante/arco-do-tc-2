#!/usr/bin/env python3
r"""Verificação manual da extração MongoDB (Fase 2.1) contra um banco real.

Por quê este script existe
---------------------------
``extract_database_triples``/``extract_triples`` (``uschema.extractors.mongo``)
— as funções que **abrem** um ``pymongo.MongoClient`` de verdade — nunca
rodaram contra um MongoDB real. `simplify`/`build_triples` (a lógica pura) já
foram validadas contra o Northwind real na Fase 2.3, mas lendo os JSONs direto
com ``bson.json_util.loads`` — sem passar pelo cursor `pymongo`. Este script
fecha essa lacuna, igual ``verificar_extracao_neo4j.py`` fechou pro Neo4j.

Três coisas testadas
----------------------
1. **Fumaça geral**: uma coleção pequena semeada via ``MongoClient`` de
   verdade, lida de volta via ``extract_triples`` — confirma que o cursor real
   (não um ``Iterable[Mapping]`` sintético) funciona ponta a ponta.
2. **`Int64`/`bool`/`int`** (a armadilha catalogada em ``extractors/mongo.py``
   — ``bson.Int64`` e ``bool`` são subclasses de ``int`` em Python, então a
   ordem de despacho do ``simplify`` importa): insere um documento com um
   campo ``Int64`` de verdade (não um int Python comum) e confirma que ele
   sai como ``{"$numberLong": ...}``, não como sentinela `0` de inteiro
   comum — o caso que a documentação já sinalizava como "sem fixture ainda".
3. **Northwind real, via `MongoClient`** (opcional, ``--northwind-dir``): se
   apontado pra uma cópia local de ``mongodb-northwind`` (a mesma usada na
   Fase 2.3), importa os 17 JSONs de verdade num banco real e roda
   ``extract_triples`` → ``BuildUSchema`` → ``compare()`` contra
   ``resources/mongodb/model_northwind.xmi``. Já sabemos o resultado esperado
   (``equivalent=True``, 15 divergências não-fatais, assinatura do #8) — isso
   confirma que o mesmo resultado se mantém passando pelo `MongoClient`
   real, não só pela leitura direta de arquivo.

Como rodar
----------
Precisa do pacote ``uschema`` (este repo) no ``PYTHONPATH``, e um MongoDB
acessível (local, ou um cluster grátis do MongoDB Atlas)::

    cd arco-do-tc-2  # raiz do repo, onde fica src/
    PYTHONPATH=src python3 scripts/verificar_extracao_mongo.py \
        --uri "mongodb://localhost:27017" --db verificacao_manual --drop

    # com o Northwind real também:
    PYTHONPATH=src python3 scripts/verificar_extracao_mongo.py \
        --uri "mongodb://localhost:27017" --db verificacao_manual --drop \
        --northwind-dir /caminho/para/mongodb-northwind/json

``--drop`` apaga o banco antes de semear — recomendado, já que o script
assume que só os dados dele existem lá.

O que fazer com a saída
-------------------------
Cola a saída completa de volta — em especial as seções 2 (`Int64`) e 3
(Northwind, se rodada).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from bson import Int64, json_util
    from pymongo import MongoClient
except ImportError:
    sys.exit("Falta o driver. Rode: pip3 install pymongo --break-system-packages")

from uschema.extractors.mongo import extract_database_triples, extract_triples

_SMOKE_DOCS = [
    {"_id": 1, "name": "Ana", "tags": ["a", "b"]},
    {"_id": 2, "name": "Bea"},
]

_INT64_DOC = {"_id": 100, "big_number": Int64(9_000_000_000)}


def _run_smoke(client: MongoClient[Any], db_name: str) -> None:
    print("\n=== 1. Fumaça geral (extract_triples, MongoClient real) ===")
    database = client[db_name]
    database["smoke"].insert_many(_SMOKE_DOCS)

    rows = extract_database_triples(database, ["smoke"])
    print(f"{len(rows)} linhas de tripla (esqueletos distintos).")
    for row in rows:
        print(f"  count={row['count']} schema={row['schema']}")


def _run_int64_check(client: MongoClient[Any], db_name: str) -> None:
    print("\n=== 2. Int64/bool/int (armadilha de despacho do simplify) ===")
    database = client[db_name]
    database["int64_check"].insert_one(_INT64_DOC)

    rows = extract_database_triples(database, ["int64_check"])
    [row] = rows
    schema = row["schema"]
    big_number = schema.get("big_number")
    print(f"schema produzido: {schema}")

    if isinstance(big_number, dict) and "$numberLong" in big_number:
        print(
            "OK: Int64 real virou {'$numberLong': ...} — despacho "
            "Int64→bool→int está correto contra dado real do driver."
        )
    else:
        print(
            f"PROBLEMA: esperava um dict com '$numberLong', veio {big_number!r} "
            "— confira a ordem de despacho em extractors/mongo.py."
        )


def _run_northwind(client: MongoClient[Any], db_name: str, northwind_dir: Path) -> None:
    print(f"\n=== 3. Northwind real via MongoClient ({northwind_dir}) ===")
    database = client[db_name]

    json_files = sorted(northwind_dir.glob("*.json"))
    if not json_files:
        print(f"PROBLEMA: nenhum .json encontrado em {northwind_dir}")
        return

    collections = []
    for json_file in json_files:
        collection_name = json_file.stem
        collections.append(collection_name)
        documents = [
            json_util.loads(line) for line in json_file.read_text().splitlines() if line.strip()
        ]
        database[collection_name].insert_many(documents)
        print(f"  {collection_name}: {len(documents)} documentos importados")

    rows = extract_database_triples(database, collections)
    print(f"\n{len(rows)} linhas de tripla no total.")

    from uschema.extractors.triple import triples_from_rows
    from uschema.inference.build_uschema import BuildUSchema
    from uschema.metamodel.registry import load_metamodel
    from uschema.metamodel.xmi import load_model
    from uschema.validation.equivalence import compare

    pkg = load_metamodel()
    triples = triples_from_rows(rows)
    port = BuildUSchema(pkg).build_from_rows("northwind", triples)
    oracle_path = (
        Path(__file__).resolve().parents[1] / "resources" / "mongodb" / "model_northwind.xmi"
    )
    oracle = load_model(oracle_path, pkg)

    result = compare(oracle, port)
    print(f"\nequivalent: {result.equivalent}")
    print(f"divergências: {len(result.divergences)}")
    for divergence in result.divergences:
        print(f"  - {divergence.category} | fatal={divergence.fatal} | {divergence.message}")

    print(
        "\nEsperado (já confirmado via leitura direta de arquivo na Fase 2.3): "
        "equivalent=True, 15 divergências não-fatais em "
        "Orders/Purchase_orders/Products/Detail."
    )


def main() -> None:
    """Semear os dados de verificação e rodar a extração real via MongoClient."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    ap.add_argument("--db", default="verificacao_manual")
    ap.add_argument("--drop", action="store_true", help="apagar o banco antes de semear")
    ap.add_argument(
        "--northwind-dir",
        type=Path,
        default=None,
        help="caminho pra mongodb-northwind/json (opcional, roda a seção 3)",
    )
    args = ap.parse_args()

    client: MongoClient[Any] = MongoClient(args.uri)

    if args.drop:
        print(f"Apagando banco {args.db!r}...")
        client.drop_database(args.db)

    _run_smoke(client, args.db)
    _run_int64_check(client, args.db)

    if args.northwind_dir is not None:
        _run_northwind(client, args.db, args.northwind_dir)
    else:
        print("\n(--northwind-dir não informado — seção 3 pulada)")

    # extract_triples também exercitado aqui (abre/fecha seu próprio
    # MongoClient) — confirma o caminho ponta a ponta, não só
    # extract_database_triples com cliente já aberto.
    print("\n=== 4. extract_triples (abre/fecha MongoClient próprio) ===")
    rows = extract_triples(args.uri, args.db, ["smoke"])
    print(f"{len(rows)} linhas de tripla lidas via extract_triples.")

    client.close()


if __name__ == "__main__":
    main()
