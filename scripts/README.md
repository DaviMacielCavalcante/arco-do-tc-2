# scripts/ — baterias de avaliação e geradores (Fase 3)

Scripts de execução das baterias de **corretude** e **escala**, fora do pacote
importável.

## Geradores de dataset (já existentes no repo original — trazer para cá)

- `gen_userprofiles.py` — User Profiles em MongoDB (Rotas A e B).
- `gen_userprofiles_neo4j.py` — User Profiles em grafo.

Quatro tamanhos: 100k / 200k / 400k / 800k `User` (50k / 100k / 200k / 400k `Movie`).

- **Rota A**: `_id` ObjectId nativo.
- **Rota B**: `_id` inteiro + ~15% arrays vazios (cenário relacional→NoSQL —
  exercita #6 e #7).

## Baterias

- Corretude: Northwind, Sakila (documento e/ou grafo) → comparar com o oráculo
  via `uschema.validation`.
- Escala: rodar os quatro tamanhos, ler o tempo de inferência do log do Spark,
  confirmar leitura integral (soma dos `count` = volume gerado), comparar a
  **tendência** (não o tempo absoluto).

## Números-alvo (com a correção do #8)

- User Profiles: divisão **50/50** entre as duas variações de `User`.
- Northwind: as **17 coleções** batem (com o bug, só 14 batiam).
