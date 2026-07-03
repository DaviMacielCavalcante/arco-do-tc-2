# patches/ — os 8 `.patch` aplicados no build do oráculo

Auditáveis e citáveis no capítulo de reprodutibilidade. Os bugs **#6/#7/#8**
são corrigidos **por construção** no porte Python (não por patch).

| Patch | Arquivo | Correção |
|---|---|---|
| #1 | binding Guice (`MongoDB2USchemaMain`) | `bind(FeatureAnalyzer.class).to(DefaultFeatureAnalyzer.class)` |
| #2 | pom `doc2uschema` | Jackson → 2.6.7.1 (Mongo) / databind → 2.10.5 (Neo4j) |
| #3 | runtime | JDK 8 (Spark 2.4/3.0.1 não lê bytecode > major 52) |
| #4 | `MongoDB2USchema.java`, `EcoreModelIO.java`, `Neo4j2USchema.java`, `Json2USchemaModel.java` | `Path.of(...)` → `Paths.get(...)` |
| #5 | `Neo4j2USchemaMain.java` | desfazer hardcode/supressão/caminho Hadoop |
| #6 | `Helpers.java` | `_id` genérico (timestamp 0 se não-ObjectId) |
| #7 | `USchemaModelBuilder.java` | `get(0)` depois de `size()==0` (array vazio) |
| #8 | `SchemaInference.java` | `combineMetadata` ao colapsar variações (contagem) |
