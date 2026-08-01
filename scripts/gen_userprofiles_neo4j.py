#!/usr/bin/env python3
"""Gerador sintético "User Profiles" — versão GRAFO (Neo4j).

Para o teste de escalabilidade da ferramenta U-Schema original
(es.um.uschema.neo4j2uschema).

Equivalente grafo do gen_userprofiles.py (que gera a versão documento para o
es.um.uschema.mongodb2uschema). Reproduz o dataset descrito em Fernández-Candel,
Sevilla-Ruiz, García-Molina, "A unified metamodel for NoSQL and relational
databases", Information Systems 104:101898, 2022 (Tabela 3) — usado por eles para
medir tempo de inferência em cada paradigma, inclusive grafo.

DIFERENÇA ESTRUTURAL vs. a versão documento (decisão de modelagem: address ACHATADO):
  - No Mongo, User embutia address{...} e arrays watchedMovies[{stars,movie_id}]
    e favoriteMovies[movie_id].
  - Aqui (grafo), Neo4j não aceita propriedade aninhada, então:
      * address vira propriedades ACHATADAS no nó User
        (address_street, address_number, address_city, address_postcode?).
      * watchedMovies vira aresta  (:User)-[:WATCHED {stars}]->(:Movie)
      * favoriteMovies vira aresta (:User)-[:FAVORITE]->(:Movie)

Estrutura (User Profiles do artigo, §3.2), materializada como grafo:
  - Movie : nó {id, title, year, genre}                       (id inteiro = chave natural)
  - User  : nó {id, name, surname?, email, address_* achatado}
      * 2 variações de endereço : com/sem address_postcode
      * 2 variações de User     : (surname + favoritos) OU (só watched)
  - ~15% dos users saem ISOLADOS (sem WATCHED nem FAVORITE) — equivalente grafo
    do "array vazio" da Rota B; exercita o caminho de nó sem references no builder.

Quatro tamanhos do artigo (--size):
  small  : User 100k, Movie  50k,  ~3  arestas/user
  medium : User 200k, Movie 100k,  ~5  arestas/user
  large  : User 400k, Movie 200k, ~10  arestas/user
  larger : User 800k, Movie 400k, ~20  arestas/user

Uso na máquina do Davi (Neo4j nativo 2026.05, auth DESLIGADA):
    uv sync
    uv run gen_userprofiles_neo4j.py --size small
    # depois aponta a extração para o banco padrão (neo4j) e cronometra pelo log do Spark

OBS: o conector de extração ignora DATABASE_NAME e lê o banco padrão `neo4j`,
então este gerador carrega no banco padrão. Comece pelo `small` e suba um por vez.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Iterator

try:
    from neo4j import GraphDatabase, Session
except ImportError:
    sys.exit("Falta o driver neo4j. Rode: uv sync")

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
EMPTY_FRACTION = 0.15  # ~15% de users isolados (equivalente grafo do array vazio)

CQL_CONSTRAINT_MOVIE = (
    "CREATE CONSTRAINT movie_id IF NOT EXISTS FOR (m:Movie) REQUIRE m.id IS UNIQUE"
)
CQL_CONSTRAINT_USER = "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE"
CQL_MOVIES = "UNWIND $rows AS r CREATE (m:Movie) SET m = r"
CQL_USERS = "UNWIND $rows AS r CREATE (u:User)  SET u = r"
CQL_WATCHED = (
    "UNWIND $rows AS r "
    "MATCH (u:User {id:r.uid}), (m:Movie {id:r.mid}) "
    "CREATE (u)-[:WATCHED {stars:r.stars}]->(m)"
)
CQL_FAVORITE = (
    "UNWIND $rows AS r MATCH (u:User {id:r.uid}), (m:Movie {id:r.mid}) CREATE (u)-[:FAVORITE]->(m)"
)


def run_batches(session: Session, query: str, rows_iter: Iterator[dict[str, object]]) -> int:
    """Executa `query` em lotes de BATCH linhas.

    Parameters
    ----------
    session : neo4j.Session
        Sessão já aberta; quem abre/fecha é o chamador.
    query : str
        Cypher parametrizado por `$rows` (uma das constantes `CQL_*`).
    rows_iter : iterator of dict
        Linhas a enviar, uma por vez — nunca materializado por completo.

    Returns
    -------
    int
        Total de linhas enviadas.
    """
    buf: list[dict[str, object]] = []
    total = 0
    for row in rows_iter:
        buf.append(row)
        if len(buf) >= BATCH:
            session.run(query, rows=buf).consume()
            total += len(buf)
            buf = []
    if buf:
        session.run(query, rows=buf).consume()
        total += len(buf)
    return total


def gen_movie_rows(n: int) -> Iterator[dict[str, object]]:
    """Gera as `n` linhas de nó Movie.

    Parameters
    ----------
    n : int
        Quantidade de filmes a gerar.

    Returns
    -------
    iterator of dict
        Uma linha por filme (`id`, `title`, `year`, `genre`).
    """
    for i in range(n):
        yield {
            "id": i,
            "title": f"Movie {i}",
            "year": random.randint(1950, 2025),
            "genre": random.choice(GENRES),
        }


def gen_user_rows(n: int) -> Iterator[dict[str, object]]:
    """Nós User com address achatado e as 2 variações do artigo.

    Parameters
    ----------
    n : int
        Quantidade de users a gerar.

    Returns
    -------
    iterator of dict
        Uma linha por user; metade ganha `address_postcode` e `surname`
        (as duas variações estruturais do dataset, ver docstring do módulo).
    """
    for i in range(n):
        row: dict[str, object] = {
            "id": i,
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "address_street": random.choice(STREETS),
            "address_number": random.randint(1, 9999),
            "address_city": random.choice(CITIES),
        }
        # variação de endereço: metade com postcode, metade sem
        if i % 2 == 0:
            row["address_postcode"] = f"{random.randint(10000, 99999)}"
        # variação de User: metade tem surname (+ favoritos, criados nas arestas)
        if i % 2 == 0:
            row["surname"] = f"Surname {i}"
        yield row


def gen_edge_rows(n_user: int, n_movie: int, rels: int) -> Iterator[tuple[str, dict[str, object]]]:
    """Gera as linhas de WATCHED e FAVORITE.

    ~15% dos users ficam isolados (sem nenhuma aresta) -> equivalente do array
    vazio. Rende tuplas ("W"/"F", row) em vez de dois geradores separados.

    Parameters
    ----------
    n_user : int
        Quantidade de users (mesmo valor passado a `gen_user_rows`).
    n_movie : int
        Quantidade de filmes (mesmo valor passado a `gen_movie_rows`) — usado
        pra sortear o `mid` de cada aresta.
    rels : int
        Teto de arestas por user (o real é `randint(1, rels)` por tipo).

    Returns
    -------
    iterator of tuple of (str, dict)
        `("W", {uid, mid, stars})` para WATCHED, `("F", {uid, mid})` para
        FAVORITE.
    """
    for i in range(n_user):
        isolated = random.random() < EMPTY_FRACTION
        if isolated:
            continue
        # WATCHED: 1..rels arestas com propriedade stars
        k = random.randint(1, max(1, rels))
        for _ in range(k):
            yield (
                "W",
                {"uid": i, "mid": random.randint(0, n_movie - 1), "stars": random.randint(1, 5)},
            )
        # FAVORITE só para a variação "com surname" (i par), e nem sempre
        if i % 2 == 0 and random.random() >= EMPTY_FRACTION:
            kf = random.randint(1, max(1, rels))
            for _ in range(kf):
                yield ("F", {"uid": i, "mid": random.randint(0, n_movie - 1)})


def run_edges(session: Session, n_user: int, n_movie: int, rels: int) -> tuple[int, int]:
    """Roda WATCHED e FAVORITE em lotes separados, sem acumular tudo em memória.

    Parameters
    ----------
    session : neo4j.Session
        Sessão já aberta; quem abre/fecha é o chamador.
    n_user, n_movie, rels : int
        Repassados direto a :func:`gen_edge_rows`.

    Returns
    -------
    tuple of (int, int)
        `(total de WATCHED, total de FAVORITE)` criados.
    """
    w_buf: list[dict[str, object]] = []
    f_buf: list[dict[str, object]] = []
    n_w = n_f = 0
    for kind, row in gen_edge_rows(n_user, n_movie, rels):
        if kind == "W":
            w_buf.append(row)
            if len(w_buf) >= BATCH:
                session.run(CQL_WATCHED, rows=w_buf).consume()
                n_w += len(w_buf)
                w_buf = []
        else:
            f_buf.append(row)
            if len(f_buf) >= BATCH:
                session.run(CQL_FAVORITE, rows=f_buf).consume()
                n_f += len(f_buf)
                f_buf = []
    if w_buf:
        session.run(CQL_WATCHED, rows=w_buf).consume()
        n_w += len(w_buf)
    if f_buf:
        session.run(CQL_FAVORITE, rows=f_buf).consume()
        n_f += len(f_buf)
    return n_w, n_f


def drop_all(session: Session) -> None:
    """Apaga o grafo em transações em lote (seguro para volumes grandes).

    Parameters
    ----------
    session : neo4j.Session
        Sessão já aberta; quem abre/fecha é o chamador.
    """
    session.run("MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS").consume()


def main() -> None:
    """Parseia os argumentos de linha de comando e roda a geração ponta a ponta.

    Lê `--size` (obrigatório) para escolher a escala, conecta no Neo4j via
    `--uri`/`--user`/`--password`, opcionalmente apaga o grafo existente
    (`--drop`) e gera Movies, Users e as arestas WATCHED/FAVORITE em lotes,
    imprimindo o tempo de cada etapa. Sem parâmetros de função — lê
    `sys.argv` via `argparse`.

    Notes
    -----
    `--seed` fixa o gerador pseudoaleatório e é o que torna o dataset
    **reprodutível**. Sem ela, cada execução sorteia usuários isolados
    (~15%) e favoritos de forma diferente: os totais de nós continuam
    exatos, mas a divisão entre as variações de ``User`` muda — e o
    ``compare()`` contra os XMIs-oráculo passa a acusar divergências de
    ``count`` que **não** são defeito do porte. Ver `todolist_fase3.md` §3.1.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", choices=list(SIZES), required=True)
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--user", default=None, help="usuário (omita se auth desligada)")
    ap.add_argument("--password", default=None, help="senha (omita se auth desligada)")
    ap.add_argument(
        "--drop",
        action="store_true",
        help="apagar o grafo antes de gerar (recomendado entre execuções)",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=None,
        help="semente do RNG; omitir dá um sorteio novo a cada execução (não reprodutível)",
    )
    args = ap.parse_args()

    random.seed(args.seed)

    cfg = SIZES[args.size]
    auth = (args.user, args.password) if args.user else None
    print(f"== size {args.size} | uri {args.uri} | seed {args.seed} ==")
    print(f"   User={cfg['user']}  Movie={cfg['movie']}  arestas~{cfg['rels']}/user")

    t0 = time.time()
    with GraphDatabase.driver(args.uri, auth=auth) as driver, driver.session() as session:
        if args.drop:
            print("   apagando grafo anterior...")
            drop_all(session)
            print("   (grafo apagado)")

        session.run(CQL_CONSTRAINT_MOVIE).consume()
        session.run(CQL_CONSTRAINT_USER).consume()

        tm = time.time()
        n_m = run_batches(session, CQL_MOVIES, gen_movie_rows(cfg["movie"]))
        print(f"  movies: {n_m} criados em {time.time() - tm:.1f}s")

        tu = time.time()
        n_u = run_batches(session, CQL_USERS, gen_user_rows(cfg["user"]))
        print(f"  users:  {n_u} criados em {time.time() - tu:.1f}s")

        te = time.time()
        n_w, n_f = run_edges(session, cfg["user"], cfg["movie"], cfg["rels"])
        print(f"  arestas: WATCHED={n_w} FAVORITE={n_f} em {time.time() - te:.1f}s")

    print(f"== concluído em {time.time() - t0:.1f}s ==")
    print("   Agora rode a extração (Neo4j2USchemaMain) e leia o tempo de")
    print("   inferência no log do Spark ('Job ... finished ... took').")


if __name__ == "__main__":
    main()
