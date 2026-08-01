# scripts/ — baterias de avaliação e geradores (Fase 3)

Scripts de execução das baterias de **corretude** e **escala**, fora do pacote
importável.

## Geradores de dataset (já existentes no repo original — trazer para cá)

- `gen_userprofiles.py` — User Profiles em MongoDB (Rotas A e B). **Ainda não
  trazido**, mas **localizado** (31/07/2026): está em
  `~/Documents/teste_uschema/gen_userprofiles.py` (repo próprio, autoria do
  Davi), não no clone Java. Ao trazer: type hints + docstrings NumPy (o
  `mypy --strict`/`ruff` cobre `scripts/`), `pip3` → `uv`, e remover a
  instrução de cronometrar pelo log do Spark (não há Spark desde a 2.0).
  Não bloqueia a bateria — os 8 bancos `up_{a,b}_{small,medium,large,larger}`
  já estão materializados no MongoDB local —, mas o capítulo precisa dele
  para ser reproduzível por terceiros.
- `gen_userprofiles_neo4j.py` — User Profiles em grafo. Trazido do original
  (autoria do Davi); só a instrução de instalação foi ajustada de `pip3` pra
  `uv`, resto não reformatado. Confirma a estrutura dos XMIs-oráculo
  (`resources/neo4j/movies_min.xmi`/`up_*.xmi`).

Quatro tamanhos: 100k / 200k / 400k / 800k `User` (50k / 100k / 200k / 400k `Movie`).

> **Nenhum dos dois geradores tem semente.** Ambos usam `random` sem
> `random.seed` (no do grafo, `:196` e `:207` sorteiam users isolados e
> favoritos), então **cada execução produz um dataset diferente** — mesmos
> totais, divisão entre variações diferente. Consequência medida em 31/07/2026:
> regerar as escalas `small`/`medium`/`large` do grafo fez o `compare()` contra
> os XMIs-oráculo de `resources/` acusar **7 divergências não-fatais de `count`** em cada uma,
> enquanto o `larger` (não regerado, instância original) fechou com **zero**.
> Não é defeito do porte — é o dataset que mudou. **Provado em 01/08/2026:**
> com `--seed` nos dois geradores (já feito) e o **oráculo Java rodado sobre a
> mesma instância semeada**, o `compare()` dá `equivalent=True` com **zero**
> divergências. Contra `resources/` continuam aparecendo as 7, porque aqueles
> XMIs vêm de uma instância de semente desconhecida — e essa é a comparação
> mais fraca das duas.

- **Rota A**: `_id` ObjectId nativo.
- **Rota B**: `_id` inteiro + ~15% arrays vazios (cenário relacional→NoSQL —
  exercita #6 e #7).

## Baterias — `run_scale_mongo.py`, `run_scale_neo4j.py`, `run_scale_suite.sh`

`run_scale_suite.sh` encadeia N sementes nas duas baterias, **sequencialmente**
(padrão: 23 69 207; ou exatamente 3 passadas por argumento). Começa chamando
`clean_databases.py`, que apaga só os 8 bancos `up_*` e o grafo — nunca o
`northwind`.

Não rode as duas em paralelo: os clientes Python não disputam, mas mongod e
Neo4j disputam CPU e disco, e os tempos vão para o capítulo.

Os CSVs vão para `resultados/`, em modo append, com **guarda de cabeçalho** —
se o esquema mudar, a bateria recusa anexar em vez de corromper o arquivo em
silêncio. Os XMIs vão para **`out/porte/`**, separados dos do oráculo
(`out/oraculo/`) e dos de referência (`resources/`) — a convenção está em
`resources/README.md`, "Onde cada XMI mora".

**`t_limpeza` é coluna separada de `t_geracao` no CSV do grafo**, e isso é
lição aprendida: na primeira bateria o gerador rodava com `--drop` e o
cronômetro engolia a deleção do grafo anterior — `small` da semente 23 marcou
7,60s e o das sementes 69/207 marcou ~127s, porque estavam apagando 10,2M
arestas da corrida anterior. Apagar um grafo grande é custo real do paradigma,
mas não é geração.

## Baterias — protocolo

- Corretude: Northwind, Sakila (documento e/ou grafo) → comparar com o oráculo
  via `uschema.validation`.
- Escala: rodar os quatro tamanhos, **cronometrar a inferência em processo**
  (a leitura é por driver nativo desde a 2.0 — não há log de executor Spark),
  confirmar leitura integral (soma dos `count` = volume gerado), comparar a
  **tendência** (não o tempo absoluto).

## Números-alvo

O critério é **casar com o oráculo**, não com o volume real — o **#8** é
replicado de propósito (`bugs_originais.md` §#8), e o oráculo também não o
corrige (não há patch `0008`).

- **Grafo (User Profiles):** soma dos `count` de `User` = volume gerado — 100k/200k/400k/800k. Fecha exato; o núcleo do Neo4j é próprio e o #8 não passa por ele (verificado nos 4 XMIs-oráculo).
- **Documento (User Profiles, Northwind):** a soma **não** fecha, e não deve. Medir a subcontagem e mostrar que é a mesma do oráculo. No Northwind isso aparece como divergências **não-fatais** em `orders`/`products`/`purchase_orders` — a quantidade delas varia com a ordem de leitura (15 por arquivo, 12 por cursor), então cite o invariante (**14/17** coleções fechando), não o número.

> O 50/50 do User Profiles e o "17 de 17" do Northwind são resultados do
> experimento **original com a correção do #8** — contexto do que o bug custa,
> **não** alvo deste porte. Persegui-los quebraria a equivalência.
