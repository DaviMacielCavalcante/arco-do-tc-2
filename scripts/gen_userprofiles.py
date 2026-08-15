"""Gerador sintético "User Profiles" — versão documento (MongoDB).

Equivalente documento do `gen_userprofiles_neo4j.py`. Reproduz o dataset de
Fernández-Candel, Sevilla-Ruiz, García-Molina, "A unified metamodel for NoSQL
and relational databases", Information Systems 104:101898, 2022 (Tabela 3).

Rota A: `_id` ObjectId nativo, reprodução fiel do artigo.
Rota B: `_id` inteiro e arrays às vezes vazios — cenário relacional para NoSQL,
que exercita os bugs #6 e #7, corrigidos por construção no porte.

Sem `--seed` cada execução produz um dataset diferente: os totais batem, a
divisão entre variações não. Contexto em `todolist_fase3.md` §3.1.

    uv run python scripts/gen_userprofiles.py --route A --size small --db up_a_small --seed 23
"""

import argparse
import random
import sys
import time
from typing import Any

try:
    from bson import ObjectId
    from pymongo import InsertOne, MongoClient
    from pymongo.collection import Collection
except ImportError:
    sys.exit("Falta o pymongo. Rode: uv sync")

SIZES = {
    "small": {"user": 100_000, "movie": 50_000, "rels": 3},
    "medium": {"user": 200_000, "movie": 100_000, "rels": 5},
    "large": {"user": 400_000, "movie": 200_000, "rels": 10},
    "larger": {"user": 800_000, "movie": 400_000, "rels": 20},
}

GENRES = ["Action", "Drama", "SciFi", "Comedy", "Horror", "Documentary"]
CITIES = ["Belem", "Recife", "Sao Paulo", "Lisboa", "Madrid", "Murcia"]
STREETS = ["Main St", "Av Brasil", "Rua das Flores", "Gran Via", "Calle Mayor"]

BATCH = 5_000
EMPTY_FRACTION = 0.15


def movie_id_value(route: str, i: int) -> tuple[Any, Any]:
    """Devolve o `_id` e o valor usado como referência."""
    if route == "A":
        oid = ObjectId()

        return oid, oid

    return i, i


def gen_movies(coll: Collection[dict[str, Any]], route: str, n: int) -> list[Any]:
    """Gera n filmes em lotes e devolve os ids, para os users referenciarem."""
    ids: list[Any] = []
    ops: list[InsertOne[dict[str, Any]]] = []

    start = time.time()

    for i in range(n):
        _id, ref = movie_id_value(route, i)

        ids.append(ref)

        ops.append(
            InsertOne(
                {
                    "_id": _id,
                    "title": f"Movie {i}",
                    "year": random.randint(1950, 2025),
                    "genre": random.choice(GENRES),
                }
            )
        )

        if len(ops) >= BATCH:
            coll.bulk_write(ops, ordered=False)
            ops.clear()

    if ops:
        coll.bulk_write(ops, ordered=False)

    print(f"  movies: {n} inseridos em {time.time() - start:.1f}s")

    return ids


def make_address(variation_postcode: bool) -> dict[str, Any]:
    """Monta o endereço embutido, com ou sem postcode."""
    addr: dict[str, Any] = {
        "street": random.choice(STREETS),
        "number": random.randint(1, 9999),
        "city": random.choice(CITIES),
    }

    if variation_postcode:
        addr["postcode"] = f"{random.randint(10000, 99999)}"

    return addr


def gen_users(
    coll: Collection[dict[str, Any]], route: str, n: int, movie_ids: list[Any], rels: int
) -> None:
    """Gera n usuários com as duas variações de Address e de User."""
    start = time.time()

    ops: list[InsertOne[dict[str, Any]]] = []
    n_movies = len(movie_ids)

    for i in range(n):
        _id, _ = movie_id_value(route, i)

        addr = make_address(variation_postcode=(i % 2 == 0))

        has_favorites = i % 2 == 0

        empty_watched = route == "B" and random.random() < EMPTY_FRACTION

        watched: list[dict[str, Any]] = []

        if not empty_watched:
            k = random.randint(1, max(1, rels))

            for _ in range(k):
                watched.append(
                    {
                        "stars": random.randint(1, 5),
                        "movie_id": random.choice(movie_ids) if n_movies else 0,
                    }
                )

        doc: dict[str, Any] = {
            "_id": _id,
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "address": addr,
            "watchedMovies": watched,
        }

        if has_favorites:
            doc["surname"] = f"Surname {i}"

            empty_fav = route == "B" and random.random() < EMPTY_FRACTION

            if empty_fav:
                doc["favoriteMovies"] = []

            else:
                kf = random.randint(1, max(1, rels))

                doc["favoriteMovies"] = [
                    (random.choice(movie_ids) if n_movies else 0) for _ in range(kf)
                ]

        ops.append(InsertOne(doc))

        if len(ops) >= BATCH:
            coll.bulk_write(ops, ordered=False)
            ops.clear()

        if i and i % 100_000 == 0:
            print(f"    users: {i}/{n} ({time.time() - start:.0f}s)")

    if ops:
        coll.bulk_write(ops, ordered=False)

    print(f"  users: {n} inseridos em {time.time() - start:.1f}s")


def main() -> None:
    """Parseia os argumentos e gera o dataset ponta a ponta."""
    ap = argparse.ArgumentParser(description="Gerador User Profiles (MongoDB)")
    ap.add_argument("--route", choices=["A", "B"], required=True)
    ap.add_argument("--size", choices=list(SIZES), required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    ap.add_argument("--drop", action="store_true")
    ap.add_argument("--seed", type=int, default=None)

    args = ap.parse_args()

    random.seed(args.seed)

    cfg = SIZES[args.size]

    print(
        f"== Rota {args.route} | size {args.size} | db {args.db} | seed {args.seed} | "
        f"User={cfg['user']} Movie={cfg['movie']} rels~{cfg['rels']}/user =="
    )

    client: MongoClient[dict[str, Any]] = MongoClient(args.uri)

    if args.drop:
        client.drop_database(args.db)

    db = client[args.db]

    start = time.time()

    movie_ids = gen_movies(db["Movie"], args.route, cfg["movie"])

    gen_users(db["User"], args.route, cfg["user"], movie_ids, cfg["rels"])

    print(f"== concluído em {time.time() - start:.1f}s ==")

    client.close()


if __name__ == "__main__":
    main()
