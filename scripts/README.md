# scripts/ — baterias de avaliação e geradores (Fase 3)

Scripts de execução das baterias de **corretude** e **escala**, fora do pacote
importável.

## Geradores de dataset (vindos do repo original, autoria do Davi)

- `gen_userprofiles.py` — User Profiles em MongoDB (Rotas A e B). Trazido de
  `~/Documents/teste_uschema/` (repo próprio, não o clone Java) com type hints,
  docstrings NumPy, `pip3` → `uv` e sem a instrução de cronometrar pelo log do
  Spark (não há Spark desde a 2.0).
- `gen_userprofiles_neo4j.py` — User Profiles em grafo. Trazido do original; só
  a instrução de instalação foi ajustada de `pip3` pra `uv`, resto não
  reformatado. Confirma a estrutura dos XMIs-oráculo
  (`resources/neo4j/movies_min.xmi`/`up_*.xmi`).

Os dois aceitam `--seed`, então a bateria é reproduzível por terceiros.

Quatro tamanhos: 100k / 200k / 400k / 800k `User` (50k / 100k / 200k / 400k `Movie`).

> **Sem `--seed`, cada execução produz um dataset diferente** — mesmos totais,
> divisão entre variações diferente (o sorteio de users isolados e favoritos
> muda). Consequência medida em 31/07/2026, antes de a semente existir: regerar
> as escalas `small`/`medium`/`large` do grafo fez o `compare()` contra os
> XMIs-oráculo de `resources/` acusar **7 divergências não-fatais de `count`**
> em cada uma, enquanto o `larger` (não regerado, instância original) fechou com
> **zero**. Não é defeito do porte — é o dataset que mudou. **Provado nas quatro
> escalas em 02/08/2026:** com a semente fixa e o **oráculo Java rodado sobre a
> mesma instância**, o `compare()` dá `equivalent=True` com **zero**
> divergências em todas. Contra `resources/` continuam aparecendo as 7, porque
> aqueles XMIs vêm de uma instância de semente desconhecida — e essa é a
> comparação mais fraca das duas.

- **Rota A**: `_id` ObjectId nativo.
- **Rota B**: `_id` inteiro + ~15% arrays vazios (cenário relacional→NoSQL —
  exercita #6 e #7).

## Corretude do Northwind — `run_northwind.py`

Roda o dataset pelos **dois caminhos de leitura** — os 17 JSONs direto do disco
e o banco pelo cursor do `pymongo` — e compara cada um com
`resources/mongodb/model_northwind.xmi`, gravando as divergências no
`resultados/equivalencia.csv` com a coluna `origem`.

```bash
uv run python scripts/run_northwind.py
```

Os dois caminhos existem porque o **#8 é sensível à ordem de leitura**: dá 15
divergências por arquivo e 12 por cursor, com o mesmo dado. O invariante
citável não é esse número — é `equivalent=True` mais **14/17** coleções
fechando a contagem, que vale nos dois caminhos.

Os JSONs estão versionados em `resources/datasets/northwind/` (BSD 2-Clause, com
o `LICENSE` junto), então o caminho `arquivo` **roda sem banco e sem dependência
externa**. O script imprime o SHA-256 do conjunto a cada corrida, prendendo o
resultado a uma versão do dataset.

Os JSONs são JSONL em extended JSON, então a leitura usa `bson.json_util.loads`
— com `json.load` puro o `{"$date": …}` viraria objeto aninhado e o modelo
ganharia uma entidade que o oráculo não tem.

## Baterias — `run_scale_mongo.py`, `run_scale_neo4j.py`, `run_oracle_neo4j.py`, `run_scale_suite.sh`

`run_oracle_neo4j.py` é a cadeia de **corretude** do grafo (Fase 3.1): por
escala, limpa, regera com a semente, roda o porte, roda o **oráculo Java em
Docker sobre a mesma instância** e compara os dois XMIs — mais uma comparação
contra `resources/`, que serve de contraste. Exige a imagem buildada
(`docker build -t extrator-uschema oracle/`) e o Neo4j no ar.

```bash
uv run python scripts/run_oracle_neo4j.py --seed 23
uv run python scripts/run_oracle_neo4j.py --seed 23 --scales larger --memory 10g
```

O XMI do oráculo é preservado como `out/oraculo/neo4j_<schema>_seed<N>.xmi`
para que a corrida seguinte não sobrescreva a evidência da anterior. O
`t_oraculo` do CSV é **relógio de parede do container** — inclui boot de Maven,
JVM e Spark (~10s fixos), então não é comparável ao cronômetro interno do Java
nem citável em escala pequena.

`run_scale_suite.sh` encadeia N sementes nas duas baterias de escala, **sequencialmente**
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
