"""Esvazia os bancos que as baterias da Fase 3.2 geram.

Destrutivo por definição. No MongoDB apaga só os oito `up_{a,b}_{tamanho}`;
no Neo4j apaga o grafo inteiro, porque o Community tem um banco só. O
`northwind` nunca é tocado. Contexto em `resources/README.md`.
"""

import argparse
from collections.abc import Mapping
from typing import Any

from neo4j import GraphDatabase
from pymongo import MongoClient

SIZES = ("small", "medium", "large", "larger")
ROUTES = ("a", "b")

MONGO_DATABASES = tuple(f"up_{route}_{size}" for route in ROUTES for size in SIZES)

CQL_DELETE = "MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"

CQL_COUNT = "MATCH (n) RETURN count(n) AS total"


def clean_mongo(uri: str) -> list[str]:
    """Dropa os bancos sintéticos existentes e devolve os nomes apagados."""
    client: MongoClient[Mapping[str, Any]] = MongoClient(uri)

    try:
        existing = set(client.list_database_names())

        targets = [name for name in MONGO_DATABASES if name in existing]

        for name in targets:
            client.drop_database(name)

    finally:
        client.close()

    return targets


def clean_neo4j(uri: str) -> int:
    """Apaga o grafo do banco padrão e devolve quantos nós existiam."""
    with GraphDatabase.driver(uri, auth=None) as driver, driver.session() as session:
        record = session.run(CQL_COUNT).single()

        before = int(record["total"]) if record is not None else 0

        # `IN TRANSACTIONS` exige transação implícita: `session.run` é
        # auto-commit, `driver.execute_query` abre uma explícita e o servidor
        # recusa com TransactionStartFailed.
        if before:
            session.run(CQL_DELETE).consume()

    return before


def main() -> None:
    """Limpa os bancos pedidos e relata o que foi apagado."""
    ap = argparse.ArgumentParser(description="Esvazia os bancos das baterias (Fase 3.2)")
    ap.add_argument("--uri-mongo", default="mongodb://localhost:27017")
    ap.add_argument("--uri-neo4j", default="bolt://localhost:7687")
    ap.add_argument("--only", choices=["mongo", "neo4j"], default=None)

    args = ap.parse_args()

    if args.only in (None, "mongo"):
        dropped = clean_mongo(args.uri_mongo)

        detail = f": {', '.join(dropped)}" if dropped else ""

        print(f"mongo: {len(dropped)} banco(s) dropado(s){detail}")

    if args.only in (None, "neo4j"):
        before = clean_neo4j(args.uri_neo4j)

        print(f"neo4j: grafo apagado ({before} nós)" if before else "neo4j: grafo já estava vazio")


if __name__ == "__main__":
    main()
