#!/usr/bin/env python3
r"""Verificação manual da extração Neo4j (Fase 2.2) contra um banco real.

Por quê este script existe
---------------------------
A camada de extração (``uschema.extractors.neo4j``) e a de construção
(``uschema.extractors.neo4j_model``) só foram testadas até agora contra
fakes de ``Node``/``Relationship`` (unit) e contra arquétipos reconstruídos
à mão a partir dos XMIs-oráculo (``tests/datasets/test_movies_min_golden_master.py``).
Nenhuma delas rodou ainda contra um Neo4j **de verdade**, falando bolt de
verdade. Este script fecha essa lacuna — sem precisar de Docker nem de rede
liberada (roda na sua máquina, contra o seu Neo4j).

Duas coisas testadas
---------------------
1. **Fumaça geral**: um grafo pequeno (User/Movie/WATCHED/FAVORITE, a mesma
   forma do dataset "User Profiles" que gerou os XMIs de referência — ver
   ``gen_userprofiles_neo4j.py`` neste mesmo `scripts/`) — confirma que
   ``execute_query``, a construção das duas *cypher*, e o parsing do
   resultado real (não fake) funcionam ponta a ponta.
2. **A assimetria de ordenação de labels** (catalogada em
   ``extractors/neo4j.py``, seção "Uma assimetria do oráculo a preservar",
   e em ``todolist_fase2.md`` §2.2): ``node_archetype`` ordena os labels
   *próprios* de um nó (``sorted(node.labels)``) antes de montar o nome do
   ``EntityType``; ``_relationship_archetype`` **não** ordena os labels do
   alvo (``refsTo``) de uma referência. Se o Neo4j real devolver
   ``labels()`` na ordem de inserção (não alfabética) — o que o próprio
   oráculo Java parece assumir, já que só ele faz o `.sorted()` explícito —
   um nó multi-label que é ao mesmo tempo (a) lido em seu próprio direito e
   (b) alvo de uma relação de outro nó pode gerar **dois** ``EntityType``
   diferentes pro mesmo nó físico: um pelo nome com labels ordenados, outro
   pelo nome com labels na ordem de inserção. O grafo semeado aqui cria
   exatamente esse caso (``:Zebra:Apple``, nessa ordem de inserção) pra
   observar se o bug se manifesta de verdade.

Como rodar
----------
Precisa do pacote ``uschema`` (este repo) instalável/no ``PYTHONPATH``, e um
Neo4j acessível (local, Desktop, Aura free etc.)::

    cd arco-do-tc-2  # raiz do repo, onde fica src/
    PYTHONPATH=src python3 scripts/verificar_extracao_neo4j.py \\
        --uri bolt://localhost:7687 --user neo4j --password sua_senha --drop

Sem ``--user``/``--password`` assume auth desligada (mesma convenção de
``gen_userprofiles_neo4j.py``). ``--drop`` apaga o grafo antes de semear —
recomendado, já que o script assume que só os dados dele existem no banco
(senão os arquétipos/counts vêm misturados com o que já estava lá).

O que fazer com a saída
-------------------------
Cole a saída completa de volta — em especial a seção "3. Veredito da
assimetria de labels", que já resume se o bug apareceu ou não.
"""

from __future__ import annotations

import argparse
import sys

try:
    from neo4j import GraphDatabase
except ImportError:
    sys.exit("Falta o driver neo4j. Rode: uv sync")

from uschema.extractors.neo4j import extract_database_archetype_counts
from uschema.extractors.neo4j_model import build_uschema_from_archetypes
from uschema.metamodel.registry import load_metamodel

CQL_DROP = "MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"

# --- 1. Grafo de fumaça geral: mesma forma do dataset "User Profiles" -------
CQL_SEED_SMOKE = """
CREATE (:Movie {id: 100, title: 'The Matrix', year: 1999, genre: 'SciFi'})
CREATE (:Movie {id: 101, title: 'Amelie', year: 2001, genre: 'Drama'})
CREATE (:User {id: 1, name: 'Ana', surname: 'Silva', email: 'ana@example.com',
               address_street: 'Av Brasil', address_number: 123,
               address_city: 'Belem', address_postcode: '66000'})
CREATE (:User {id: 2, name: 'Bea', email: 'bea@example.com',
               address_street: 'Rua das Flores', address_number: 45,
               address_city: 'Recife'})
CREATE (:User {id: 3, name: 'Caio', email: 'caio@example.com',
               address_street: 'Gran Via', address_number: 7,
               address_city: 'Madrid'})
WITH 1 AS _
MATCH (u1:User {id: 1}), (u2:User {id: 2}), (m1:Movie {id: 100}), (m2:Movie {id: 101})
CREATE (u1)-[:WATCHED {stars: 5}]->(m1)
CREATE (u1)-[:FAVORITE]->(m1)
CREATE (u2)-[:WATCHED {stars: 3}]->(m2)
"""
# u3 fica isolado de propósito (sem WATCHED/FAVORITE) — mesmo caso dos ~15%
# de users isolados do gerador de escala, exercita o nó sem `references`.

# --- 2. Grafo da assimetria de labels ---------------------------------------
CQL_SEED_LABEL_ASYMMETRY = """
CREATE (:Zebra:Apple {id: 1, name: 'Zed'})
CREATE (:Referencer {id: 1, name: 'Caio2'})
WITH 1 AS _
MATCH (r:Referencer {id: 1}), (z:Zebra:Apple {id: 1})
CREATE (r)-[:LIKES {since: 2020}]->(z)
"""


def main() -> None:
    """Semear os dois grafos de verificação e rodar extração+construção reais."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--user", default=None, help="usuário (omita se auth desligada)")
    ap.add_argument("--password", default=None, help="senha (omita se auth desligada)")
    ap.add_argument(
        "--drop", action="store_true", help="apagar o grafo antes de semear (recomendado)"
    )
    args = ap.parse_args()

    auth = (args.user, args.password) if args.user else None

    with GraphDatabase.driver(args.uri, auth=auth) as driver:
        with driver.session() as session:
            if args.drop:
                print("Apagando grafo anterior...")
                session.run(CQL_DROP).consume()

            print("Semeando grafo de fumaça (User/Movie/WATCHED/FAVORITE)...")
            session.run(CQL_SEED_SMOKE).consume()

            print("Semeando grafo da assimetria de labels (:Zebra:Apple)...")
            session.run(CQL_SEED_LABEL_ASYMMETRY).consume()

        print("\n=== 1. Extração real (extract_database_archetype_counts) ===")
        rows = extract_database_archetype_counts(driver)
        print(f"{len(rows)} arquétipos distintos lidos.")
        for row in rows:
            archetype = row["archetype"]
            if archetype["entity"] == "node":
                print(f"  nó   labels={archetype['labels']!r:30} count={row['count']}")
            else:
                print(
                    f"  rel  type={archetype['type']!r:15} "
                    f"refsTo={archetype.get('refsTo')!r:20} count={row['count']}"
                )

        print("\n=== 2. Construção do USchema (build_uschema_from_archetypes) ===")
        pkg = load_metamodel()
        schema = build_uschema_from_archetypes(pkg, "verificacao_manual", rows)

        print("EntityTypes construídos:")
        for entity in schema.entities:
            variation_counts = [v.count for v in entity.variations]
            print(
                f"  {entity.name!r:30} variações={len(entity.variations)} counts={variation_counts}"
            )

        print("RelationshipTypes construídos:")
        for relationship in schema.relationships:
            variation_counts = [v.count for v in relationship.variations]
            print(
                f"  {relationship.name!r:30} variações={len(relationship.variations)} "
                f"counts={variation_counts}"
            )

        print("\n=== 3. Veredito da assimetria de labels ===")
        entity_names = {e.name for e in schema.entities}
        apple_zebra_variants = {n for n in entity_names if "Apple" in n and "Zebra" in n}
        print(f"EntityTypes envolvendo Apple/Zebra encontrados: {sorted(apple_zebra_variants)}")

        if len(apple_zebra_variants) >= 2:
            print(
                "BUG CONFIRMADO: mais de um EntityType pro mesmo nó físico "
                "(:Zebra:Apple) -- a assimetria de ordenação de labels é real "
                "e observável com dados reais. Ver extractors/neo4j.py e "
                "todolist_fase2.md §2.2 pra registrar o achado como confirmado."
            )
        elif len(apple_zebra_variants) == 1:
            print(
                "BUG NÃO OBSERVADO: só um EntityType apareceu -- ou o Neo4j "
                "real devolve labels() já ordenado (refutando a premissa do "
                "oráculo de que precisava do .sorted() explícito), ou algo no "
                "grafo semeado não disparou o caso. Vale investigar mais antes "
                "de fechar o achado como refutado."
            )
        else:
            print(
                "Nenhum EntityType Apple/Zebra encontrado -- algo deu errado no seed "
                "ou na extração."
            )


if __name__ == "__main__":
    main()
