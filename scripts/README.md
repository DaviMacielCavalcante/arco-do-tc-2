# scripts/ — baterias de avaliação e geradores (Fase 3)

Scripts de execução das baterias de **corretude** e **escala**, fora do pacote
importável.

## Geradores de dataset (já existentes no repo original — trazer para cá)

- `gen_userprofiles.py` — User Profiles em MongoDB (Rotas A e B). **Ainda não trazido.**
- `gen_userprofiles_neo4j.py` — User Profiles em grafo. Trazido do original
  (autoria do Davi); só a instrução de instalação foi ajustada de `pip3` pra
  `uv`, resto não reformatado. Confirma a estrutura dos XMIs-oráculo
  (`resources/neo4j/movies_min.xmi`/`up_*.xmi`).

Quatro tamanhos: 100k / 200k / 400k / 800k `User` (50k / 100k / 200k / 400k `Movie`).

- **Rota A**: `_id` ObjectId nativo.
- **Rota B**: `_id` inteiro + ~15% arrays vazios (cenário relacional→NoSQL —
  exercita #6 e #7).

## Baterias

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
- **Documento (User Profiles, Northwind):** a soma **não** fecha, e não deve. Medir a subcontagem e mostrar que é a mesma do oráculo. No Northwind isso aparece como as 15 divergências **não-fatais** da Fase 2.3, em `orders`/`products`/`purchase_orders`.

> O 50/50 do User Profiles e o "17 de 17" do Northwind são resultados do
> experimento **original com a correção do #8** — contexto do que o bug custa,
> **não** alvo deste porte. Persegui-los quebraria a equivalência.
