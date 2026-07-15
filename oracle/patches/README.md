# patches/ — patches de portabilidade e corretude aplicados no build do oráculo

Auditáveis e citáveis no capítulo de reprodutibilidade. Numeração herdada do
catálogo de 8 patches originalmente previsto (ver `bugs_originais.md`), mas
só #1, #4, #5, #6 e #7 existem como arquivo `.patch` de verdade — #2/#3 são
satisfeitos estruturalmente pelo design do build, #8 fica deliberadamente
sem patch. Motivo de cada decisão, e como os patches foram verificados:
**[`oracle/docker_explain.md`](../docker_explain.md)**.

| Patch | Arquivo(s) | Correção | Status |
|---|---|---|---|
| **#1** | `MongoDB2USchemaMain.java` | `bind(FeatureAnalyzer.class).to(DefaultFeatureAnalyzer.class)` faltando no binding Guice | `.patch` — `0001-mongo-guice-binding.patch` |
| #2 | pom `doc2uschema` | Jackson → 2.10.5 (unificado pros dois caminhos desde a migração do Mongo pra Spark 3.0.1) | sem `.patch` — pom original nunca é lido nesta build |
| #3 | runtime | JDK 8 (Spark 3.0.1 não lê bytecode > major 52) | sem `.patch` — já garantido pela imagem base e pelo `uschema-build/runner/pom.xml` |
| **#4** | `MongoDB2USchema.java`, `Neo4j2USchema.java`, `Json2USchemaModel.java`, `USchemaToDocumentDb.java`, `EcoreModelIO.java`, `ModelIOTest.java` | `Path.of(...)` → `Paths.get(...)` (API do Java 11, incompatível com JDK 8) | `.patch` — `0004-path-of-to-paths-get-inference.patch` (4 arquivos, repo `uschema-inference`) + `0004-path-of-to-paths-get-uschema.patch` (`EcoreModelIO.java` + `ModelIOTest.java`, repo `uschema`) |
| **#5** | `Neo4j2USchemaMain.java` | remove hardcode de máquina (`hadoop.home.dir`, supressão de log); adiciona `args[0]` como nome do banco | `.patch` — `0005-neo4jmain-cli-arg-no-hardcode.patch` |
| **#6** | `Helpers.java` | `_id` genérico: `doc.get("_id")` + checagem `instanceof ObjectId`, timestamp `0L` se não for | `.patch` — `0006-helpers-generic-id.patch` |
| **#7** | `USchemaModelBuilder.java` | move `sc.getInners().get(0)` pra dentro do `else`, aproveitando o short-circuit do `\|\|` já existente | `.patch` — `0007-arraysc-empty-shortcircuit.patch` |
| #8 | `SchemaInference.java` | `combineMetadata` ao colapsar variações (contagem) | sem patch, de propósito — corrigido só no porte Python |

## Aplicação

Cada `.patch` é `-p1` a partir da raiz do respectivo clone:

```bash
# dentro de uschema-src/uschema-inference/
patch -p1 < ../../patches/0001-mongo-guice-binding.patch
patch -p1 < ../../patches/0004-path-of-to-paths-get-inference.patch
patch -p1 < ../../patches/0005-neo4jmain-cli-arg-no-hardcode.patch
patch -p1 < ../../patches/0006-helpers-generic-id.patch
patch -p1 < ../../patches/0007-arraysc-empty-shortcircuit.patch

# dentro de uschema-src/uschema/
patch -p1 < ../../patches/0004-path-of-to-paths-get-uschema.patch
```

(é exatamente o que o `Dockerfile` faz.)
