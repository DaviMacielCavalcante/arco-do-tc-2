# Fase 3 — Ponta a ponta + escala + correções por construção (guia detalhado)

**Parte de:** `roadmap_portabilidade.md` · **Validação:** `roteiro_experimental.md` · **Resultados de referência:** `resultado_mongodb.md`, `resultado_neo4j.md`, `resultado_bug8_subcontagem_user.md`
**Responsáveis:** Davi + João · **Pré-requisito:** Fases 1 e 2 com gates fechados

## Objetivo

Validar o porte completo de ponta a ponta — extrator PySpark → núcleo de inferência → PyEcore → XMI — em **corretude** (datasets reais) e **escala** (datasets sintéticos), confirmando que os bugs do código original ficam tratados **por construção**. É a fase de avaliação experimental do TCC.

---

## 3.1 Corretude (datasets reais)

### Northwind (relacional → documento)
17 coleções, `_id` inteiros, `order_details` embutido como `details` em `orders`. Casos que o porte tem de reproduzir (confirmados no XMI-oráculo de 109262 bytes):
- **19 `EntityType`** (17 raiz + 2 não-raiz: `_id` e `Detail`).
- **`Aggregate` aninhado**: `Detail` ligada a `Orders`/`Purchase_orders` por `Aggregate` (`upperBound="-1"`, `optional="true"`).
- **Variação estrutural** sobre o aninhado.
- **Contagens corretas nas 17 coleções** (ver 3.3 / bug #8).

**Tarefas:** rodar o pipeline Python sobre o Northwind; comparar o XMI com o oráculo pelo harness; diagnosticar e fechar divergências.

### Sakila (segundo dataset real)
Replicar o protocolo (documento e/ou grafo). Serve de segundo ponto de corretude, reduzindo o risco de *overfitting* ao Northwind.

## 3.2 Escala (datasets sintéticos)

Reproduzir o experimento de escala do artigo (Tabelas 3/4) **em PySpark**, confirmando que o porte preserva a propriedade de crescimento.

**Geradores (já existentes):** `gen_userprofiles.py` (MongoDB, Rotas A/B) e `gen_userprofiles_neo4j.py` (grafo). Quatro tamanhos: 100k/200k/400k/800k `User` (50k/100k/200k/400k `Movie`).

**MongoDB — duas rotas:**
- **Rota A** (`_id` ObjectId nativo) e **Rota B** (`_id` inteiro + ~15% arrays vazios — o cenário relacional→NoSQL). Referência i9 (ferramenta original): A ~0,47→4,09 s; B ~0,43→3,48 s.

**Neo4j — grafo:** `address` achatado; `watchedMovies`/`favoriteMovies` como arestas `WATCHED {stars}`/`FAVORITE`; ~15% users isolados. Referência i9: inferência ~3,83→34,86 s (a geração do grafo, ~180 s no maior, é mais cara que a inferência — assimetria do paradigma).

**Tarefas:**
- [ ] Rodar o porte nos quatro tamanhos, Rotas A/B (Mongo) e grafo (Neo4j); ler o tempo de inferência do log do Spark.
- [ ] Confirmar **leitura integral** (soma dos `count` = volume gerado).
- [ ] Comparar a **tendência** de crescimento com a do oráculo (não o tempo absoluto — PySpark vs. JVM diferem; o que importa é a curva).
- [ ] Sem `OutOfMemoryError` (ajustar heap/memória do executor se preciso).

## 3.3 Bugs corrigidos por construção (regressão + escala)

O porte trata nativamente os três casos que no Java exigiram patch. Cada um vira **teste de regressão** com dataset mínimo dedicado **e** é exercitado em escala.

| Bug | Cenário | Critério no porte |
|---|---|---|
| **#6** `_id` inteiro | origem relacional (Northwind, Rota B) | não assume `ObjectId`; roda os 800k da Rota B sem `ClassCastException` |
| **#7** array vazio | ~15% dos docs na Rota B | não indexa elemento inexistente; roda sem `IndexOutOfBounds` |
| **#8** contagem sob array de tamanho variável | `watchedMovies`/`favoriteMovies`; `details[]`, `supplier_ids[]` no Northwind | a soma dos `count` por entidade = volume real |

**Números-alvo (com a correção do #8):**
- **User Profiles:** divisão **50/50** entre as duas variações de `User` (Small 50.000+50.000 = 100.000; … Larger 400.000+400.000 = 800.000). *Sem* a correção, capturava-se só ~2,6%–31% (artefato do bug).
- **Northwind:** as **17 coleções** batem (com o bug, só 14 batiam; as 3 que erravam — `orders`, `products`, `purchase_orders` — eram exatamente as com campo array de tamanho variável).

**Tarefas:**
- [ ] Teste de regressão #6 (dataset com `_id` inteiro), #7 (dataset com `[]`), #8 (dataset com array de tamanho variável).
- [ ] Confirmar os números-alvo acima no porte (50/50 no User Profiles; 17/17 no Northwind).
- [ ] Documentar como capítulo de reprodutibilidade: o porte corrige por design o que o original corrigia por patch.

## 3.4 Coleta e análise

Conforme `roteiro_experimental.md` §6–7: CSVs de equivalência (por dataset/paradigma, divergências por categoria) e de escala (tempo × tamanho, fator de crescimento, leitura íntegra). Visualizações: tabela de equivalência, curva tempo × volume (porte vs. oráculo), tabela de contagens com/sem cada bug.

## Gate de aceite da Fase 3

- Northwind e Sakila: equivalência estrutural com o oráculo (corretude).
- Escala: tendência de crescimento reproduzida nos quatro tamanhos, leitura integral confirmada, sem OOM.
- Bugs #6/#7/#8: tratados por construção, com os números-alvo batendo e testes de regressão verdes.

## Entregáveis

Scripts de execução das baterias (corretude + escala), suíte de regressão dos bugs, CSVs de resultados, gráficos, e o material do capítulo de avaliação experimental (corretude, escala, correções por construção).

## Riscos da fase

PySpark mais lento que a JVM em RDDs (irrelevante — H1 é sobre **tendência**, não tempo absoluto; documentar); custo de **geração** do grafo Neo4j dominando o tempo de bateria (planejar; é da materialização, não da inferência); divergência estrutural residual em dataset real (o harness aponta a categoria; voltar à Fase 1/2 conforme o módulo).
