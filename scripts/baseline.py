"""Query de referência da Fase 3 — o divisor da coluna ``normalized``.

Porte da linha de base do artigo do U-Schema (Candel, Sevilla Ruiz e
García-Molina, *A unified metamodel for NoSQL and relational databases*,
Information Systems 104, 2022), §Evaluation:

    "instead of comparing absolute times, we used as a time baseline an
    aggregate query that calculates the average of watched movies by users.
    This query could be representative of those obtaining periodic reports, so
    we suppose that the database is not optimized for it. […] Table 4 show the
    different times for the queries, schema inference, and the normalized value
    (inference time divided by query time)"

Por que a métrica existe
------------------------
Tempo absoluto não é comparável: o baseline do artigo rodou num **i7-6700 de
2015** e o nosso num i9-14900K, e o porte é Python contra JVM. Dividir pelo
tempo de uma query representativa **na mesma máquina e no mesmo banco** cancela
a configuração do ambiente, e é o que torna a nossa curva confrontável com a
Table 4 do artigo.

O que entra no dividendo
------------------------
O que o artigo chama de *inference time* é o **pipeline inteiro** — extração,
inferência e serialização. No nosso esquema isso é ``runs.total_time``, **não**
a coluna ``inference_time``, que fica em ~0,00s porque a redução já acontece na
extração (achado da Fase 3.0). Dividir pela coluna errada daria ~0,0001 em vez
de ~10, e contradiria o artigo em silêncio.

Quando medir
------------
**Depois** do porte e do oráculo, antes da limpeza. Rodá-la antes aqueceria o
cache e aceleraria a extração medida — que é o número que a fase publica. A
contrapartida, declarada: a própria query sai com cache quente.

O artigo descreve a query mas não dá o texto; as duas abaixo são a leitura
literal de "average of watched movies by users" sobre os datasets dos nossos
geradores.
"""

import time
from collections.abc import Mapping
from typing import Any

from neo4j import Driver
from pymongo.database import Database

#: ~15% dos ``User`` do grafo saem isolados (sem ``WATCHED`` nem ``FAVORITE``).
#: O ``OPTIONAL MATCH`` os mantém no denominador: a média é *por usuário*, não
#: *por usuário que assistiu algo*. Sem ele o número sobe e deixa de ser o que o
#: artigo descreve.
NEO4J_QUERY = (
    "MATCH (u:User) OPTIONAL MATCH (u)-[:WATCHED]->(m:Movie) "
    "WITH u, count(m) AS watched RETURN avg(watched) AS average"
)

#: ``watchedMovies`` é sempre gravado pelo gerador — lista vazia em ~15% dos
#: documentos da Rota B, nunca ausente —, então ``$size`` é seguro. Os vazios
#: entram na média, pela mesma razão do ``OPTIONAL MATCH`` acima.
MONGO_PIPELINE: list[dict[str, Any]] = [
    {"$group": {"_id": None, "average": {"$avg": {"$size": "$watchedMovies"}}}}
]


def mongo_query_time(database: Database[Mapping[str, Any]]) -> float:
    """Cronometrar a query de referência no paradigma documento.

    Parameters
    ----------
    database : pymongo.database.Database
        Banco do User Profiles já materializado (``up_a_*``/``up_b_*``).

    Returns
    -------
    float
        Segundos de relógio de parede, com o cursor já consumido.
    """
    start = time.perf_counter()

    list(database["User"].aggregate(MONGO_PIPELINE))

    return time.perf_counter() - start


def neo4j_query_time(driver: Driver, database: str | None = None) -> float:
    """Cronometrar a query de referência no paradigma grafo.

    Parameters
    ----------
    driver : neo4j.Driver
        Driver já conectado; quem abre e fecha é o chamador.
    database : str, optional
        Banco a consultar; ``None`` usa o padrão, como o resto da bateria.

    Returns
    -------
    float
        Segundos de relógio de parede, com os registros já consumidos.
    """
    start = time.perf_counter()

    driver.execute_query(NEO4J_QUERY, database_=database)

    return time.perf_counter() - start
