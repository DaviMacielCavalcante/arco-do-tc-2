# Fase 2 — Extratores em PySpark (MongoDB + Neo4j) (guia detalhado)

**Parte de:** `roadmap_portabilidade.md` · **Validação:** `roteiro_experimental.md` · **Base técnica:** `analise_ferramenta_uschema.md` (§3.3–3.4)
**Responsável principal:** João · **Pré-requisito:** Fase 0 (oráculo + harness); integra com a Fase 1 pelo formato da tripla

## Objetivo

Portar para **PySpark** a camada de extração distribuída dos dois paradigmas, produzindo as triplas `{schema, count, timestamps}` que alimentam o núcleo único da Fase 1. É a parte de **menor risco técnico**: o uso de Spark é um *map-reduce* mínimo, traduzível operador a operador.

## O que o Spark realmente faz (e por que PySpark basta)

As operações usadas são de RDD de baixo nível — `map`, `mapToPair`, `reduceByKey`, `flatMap`, `collect`, `collectAsMap` —, **sem DataFrame SQL, MLlib ou streaming**. Cada documento/linha vira uma **assinatura estrutural**; o `reduceByKey` conta as ocorrências; o resultado vira as triplas. PySpark reproduz isso 1:1.

> **Decisão de arquitetura:** no Java, cada extrator `.spark` traz um `ModelDirector` próprio (mais fino). No porte, os extratores **só produzem triplas** e entregam ao núcleo `doc2uschema` da Fase 1 — um único núcleo de inferência para os dois bancos (mais limpo que o original).

---

## 2.1 Extrator MongoDB

**Classes de referência (`mongodb2uschema.spark`):** `ArchetypeMapping` (a função de assinatura), `JSONMapping` (empacota em tripla), `MapCounter`, `Helpers` (gera o par documento/meta — origem do bug #6), `TypeUtils`, `AttributeOptionalsChecker`, `Inflector`.

**Pipeline original:**
```
MongoSpark.load(jsc)
  .mapToPair(new ArchetypeMapping(collection))   // doc → assinatura (TreeMap ordenado)
  .reduceByKey((c1, c2) -> c1 + c2)              // conta por variação
  .mapToPair(new JSONMapping())                   // → {schema, count, timestamps}
  .collectAsMap();
```

**Porte PySpark (esboço):**
```python
rdd = (spark.read.format("mongodb").option("collection", col).load().rdd
       .map(archetype)            # doc → (assinatura, meta)
       .reduceByKey(combine)      # soma counts / combina timestamps
       .map(to_triple))           # → {schema, count, timestamps}
triplas = rdd.collect()           # entrega ao núcleo da Fase 1
```

**`archetype` (a função de assinatura) — pura, recursiva, `doc → assinatura`:**
- objeto aninhado → assinatura de agregado;
- lista → tratar **array vazio** (`[]`), array de escalares e array de documentos;
- escalar → o tipo.

**Tarefas:**
- [ ] Portar `ArchetypeMapping` como função Python pura sobre `dict`/`bson` (com testes unitários: documento simples, aninhado, com array vazio, com array de documentos).
- [ ] Portar `JSONMapping` (montagem da tripla) e a combinação de count/timestamps no `reduceByKey`.
- [ ] **Bug #6 por construção:** ler o `_id` **genericamente** (não assumir `ObjectId`); extrair timestamp só se for `ObjectId`, senão `0`. Suporta `_id` inteiro de origem relacional.
- [ ] **Bug #7 por construção:** a assinatura de array vazio não deve indexar elemento inexistente.
- [ ] Conectar via `spark.read.format("mongodb")` com `mongo-spark-connector 3.0.1` (`spark.jars.packages`).

**Gate:** a contagem de assinaturas por coleção é **idêntica** à do Java; o XMI final (tripla → núcleo Fase 1 → PyEcore) é estruturalmente equivalente ao oráculo (Northwind).

## 2.2 Extrator Neo4j

**Classes de referência (`neo4j2uschema`):** `SparkProcess` (o pipeline), `IdArchetypeMapping` (assinatura de nó/aresta), `ReduceByIdArchetype` (redução), `SplitMapping`, `USchemaBuilder` / `StructuralVariationBuilder` (construção; no porte, substituídos pelo núcleo único), `Json2USchemaModel`, `Constants`.

**Pipeline original (estruturalmente idêntico ao do MongoDB):**
```
neo4j.cypher(query).loadRowRdd().toJavaRDD()
  .mapToPair(new IdArchetypeMapping())
  .reduceByKey(new ReduceByIdArchetype())
  .flatMap(new SplitMapping());
```

**Especificidades do paradigma grafo a preservar:**
- `RelationshipType` de **primeira classe** (arestas viram `<relationships>`, não agregados).
- **Propriedades em arestas** inferidas (ex.: `roles`, `rating`).
- **`count` em `RelationshipType`** = número de entidades de **origem** que exercem a aresta (não o total bruto de arestas) — replicar a semântica do `ReduceByIdArchetype`/`SplitMapping`.
- O conector legado lê o **banco padrão `neo4j`** (anterior ao multi-database) e espera **auth desligada** (credenciais comentadas em `SparkProcess`).

**Tarefas:**
- [ ] Portar `IdArchetypeMapping`, `ReduceByIdArchetype` e `SplitMapping` para funções Python (com testes: nó isolado, aresta com/sem propriedade, nó-sumidouro).
- [ ] Montar as triplas a partir do grafo e entregá-las ao núcleo da Fase 1 (mesmo contrato do MongoDB).
- [ ] Conectar via PySpark + neo4j-spark-connector — **validar a versão funcional** contra o Neo4j-alvo (o legado 2.4.5-M2 conectou no 2026.05.0, mas confirmar na stack final; pode ser necessário o conector 5.x para Neo4j 5+).
- [ ] Confirmar que `RelationshipType` e propriedades de aresta saem corretas.

**Gate:** contagens (incl. a de `RelationshipType` por entidade de origem) idênticas ao Java; XMI ≡ oráculo (grafo mínimo + User Profiles em grafo).

---

## Costura com a Fase 1

Ambos os extratores produzem o **mesmo formato de tripla**. Isso é o que permite um único núcleo de inferência: a saída de 2.1 e de 2.2 é intercambiável da perspectiva do `SchemaInference` portado. Definir e congelar esse formato cedo (com a Fase 1) evita retrabalho.

## Conectores e empacotamento

- MongoDB: `mongo-spark-connector_2.12:3.0.1` (ou versão compatível com o Spark do porte) via `spark.jars.packages`.
- Neo4j: validar entre o legado `neo4j-contrib:neo4j-spark-connector:2.4.5-M2` e o oficial `org.neo4j:neo4j-connector-apache-spark` 5.x conforme o Neo4j-alvo.
- Documentar as versões exatas (reprodutibilidade).

## Gate de aceite da Fase 2

Para os dois paradigmas: contagem de assinaturas idêntica ao Java **e** XMI final estruturalmente equivalente ao oráculo, conferido pelo harness da Fase 0.

## Entregáveis

`extractor_mongo.py` (ArchetypeMapping + pipeline PySpark + montagem de tripla), `extractor_neo4j.py` (IdArchetypeMapping/ReduceByIdArchetype/SplitMapping + pipeline), testes unitários das funções de assinatura, configuração dos conectores.

## Riscos da fase

Versão do conector Neo4j incompatível com o servidor-alvo (validar cedo); a semântica de `count` em `RelationshipType` (contar fontes distintas, não arestas brutas) é sutil; a assinatura de array vazio (#7) e o `_id` genérico (#6) precisam ser tratados aqui, na origem da assinatura.
