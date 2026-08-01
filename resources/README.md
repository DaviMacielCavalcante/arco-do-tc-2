# resources/

Artefatos de referência versionados, consumidos pelo porte e pelos testes.

## Onde cada XMI mora

Três produtores, três lugares. **Não misturar** — foi por isso que a separação
existe: um XMI de referência e um XMI gerado pelo porte são indistinguíveis pelo
conteúdo, e confundi-los invalida qualquer comparação.

| Diretório | Quem produziu | Versionado? |
|---|---|---|
| **`resources/`** (este) | os **autores originais** do U-Schema, sobre o dataset deles | **sim** — é a amarra com o experimento publicado, e é imutável |
| **`out/oraculo/`** | o **oráculo Java** (Docker, `oracle/`) rodando sobre **os nossos** dados | não (`.gitignore`) — regenerável pela imagem + semente |
| **`out/porte/`** | o **porte Python** (baterias da Fase 3) | não (`.gitignore`) — regenerável pelo script + semente |

**Nunca sobrescrever `resources/` com saída nossa.** Os XMIs daqui vêm de
uma instância de dataset que não temos e não conseguimos reconstruir (os
geradores só ganharam `--seed` em 31/07/2026). Substituí-los perderia
definitivamente a ligação com o experimento do artigo. XMI-oráculo gerado por
nós vai para `out/oraculo/`; se algum dia um deles precisar virar referência
permanente de teste, entra aqui por **promoção deliberada**, com a proveniência
(semente, escala, SHA da imagem) registrada.

A comparação mais forte que o projeto pode fazer é `out/oraculo/` × `out/porte/`
sobre **a mesma instância semeada** — mesma entrada, duas implementações. O que
existe contra `resources/` é o porte sobre o nosso dado × o Java sobre o dado
deles, e é exatamente por isso que sobram divergências de `count`.

**Executada em 01/08/2026, escala `small` (seed 23):** `equivalent=True`, **zero
divergências**. Contra `resources/neo4j/movies_min.xmi` a mesma corrida acusava
7 não-fatais. A variável isolada é o dataset, não a implementação — e é por isso
que a distinção entre estes três diretórios não é organização, é método.

| Arquivo | Papel |
|---|---|
| `uschema.ecore` | Metamodelo (19 EClasses, sem OCL). Carregado por `uschema.metamodel` (Fase 0.1). |
| `model_northwind.xmi` | XMI-oráculo do Northwind (19 `EntityType`, agregado `Detail`). Round-trip da Fase 0.2 e golden-master das Fases 2.3/3.1. |
| `model_mintest.xmi` | XMI-oráculo do `mintest` — golden-master da Fase 1.7 (0 divergências). |
| `model.xmi` | Modelo mínimo MongoDB (round-trip Fase 0.2). |
| `movies_min.xmi` | **Não é um "modelo mínimo"** — é o **User Profiles / Neo4j na escala `small`**: 100.000 `User` (5 variações) + 50.000 `Movie`. O nome engana. |
| `up_medium.xmi` · `up_large.xmi` · `up_larger.xmi` | Mesmo dataset nas escalas `medium`/`large`/`larger` — 200k/400k/**800k** `User` e 100k/200k/**400k** `Movie`. As quatro escalas **dobram exatamente**. |

Os quatro XMIs do Neo4j são o **mesmo** dataset, gerado por
`scripts/gen_userprofiles_neo4j.py`; só mudam o `count` e o nome do schema. A
soma dos `count` das variações de `User` bate o volume gerado nas quatro (o
paradigma grafo tem núcleo próprio e o bug #8 não passa por ele) — é o que
torna a leitura integral verificável no grafo, e não no documento.

> Copie estes arquivos do repositório Java original / do oráculo em Docker
> (`oracle/`). São **entrada** do porte, não gerados por ele.
