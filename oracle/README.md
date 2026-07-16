# oracle/ — oráculo Java em Docker (Fase 0.5)

Papel **reduzido e opcional**: **não entra na entrega** (a ferramenta portada é
Python puro). Serve para (a) rodar o extrator original de forma reproduzível,
sem depender do Eclipse IDE nem de nenhuma máquina específica; e (b) gerar o
XMI-gabarito para datasets sem golden-master pronto (Sakila, variações de
escala). Agrega **reprodutibilidade**, não funcionalidade.

Todas as justificativas de design, decisões de patch e limitações conhecidas
estão em **[`docker_explain.md`](docker_explain.md)** — este README fica só
com o essencial pra usar e buildar.

## Conteúdo da imagem

- Base `maven:3.9-eclipse-temurin-8` (JDK 8, exigido pelo Spark 3.0.1).
- Fontes de `modelum/uschema` e `modelum/uschema-inference`, clonados num
  commit pinado, com os `patches/` aplicados por cima.
- Um build Maven único (`oracle/uschema-build/runner`), sem Eclipse — Mongo
  e Neo4j no mesmo classpath, Spark 3.0.1/Scala 2.12 pros dois (unificado;
  detalhe/validação em `docker_explain.md`).
- Sem *fat jar*: roda via `mvn exec:java -Dexec.mainClass=...`, offline
  depois do build.

## Por que precisa de um entrypoint

Os dois `main` Java não aceitam `--db`/`--kind` diretamente — o Mongo lê um
`config.properties` do classpath, o Neo4j tem bolt/usuário/senha fixos no
código. `entrypoint.sh` traduz `--db`/`--kind` (argumentos de linha de
comando) e, pro Mongo, `MONGO_URL`/`MONGO_COLLECTIONS` (variáveis de
ambiente) pra essa interface. Detalhe completo em `docker_explain.md`.

## Uso

```bash
# MongoDB
docker run --network=host --memory=6g -v "$PWD/out:/output" \
  -e MONGO_URL=mongodb://localhost:27017 \
  -e MONGO_COLLECTIONS=customers,employees,orders,... \
  extrator-uschema --db northwind --kind mongodb

# Neo4j
docker run --network=host --memory=6g -v "$PWD/out:/output" \
  extrator-uschema --db UserProfile --kind neo4j
```

`--network=host` porque o container se conecta a um banco **já rodando e já
populado** no host — o oráculo é um extrator, não empacota dado nenhum.
Preparar o banco é etapa à parte, fora deste Dockerfile. Memória ≥ ~5–6 GB
pros datasets de escala maior.

**Windows/Git Bash:** prefixe os comandos acima com `MSYS_NO_PATHCONV=1`.
Sem isso, o MSYS2 reescreve o lado `/output` do `-v` como caminho do
Windows — o container roda e reporta sucesso, mas o `.xmi` não aparece na
pasta host (mount silenciosamente quebrado, sem erro nenhum). Descoberto
rodando de verdade — detalhe em `docker_explain.md`.

**Suíte JUnit original** (baseline, comando manual — não passa pelo
`entrypoint.sh`/`--db`/`--kind`):

```bash
docker run --rm --entrypoint sh extrator-uschema \
  -c "cd /app/uschema-build/runner && mvn -q -B -o test"
```

Não precisa de `--network=host` nem `MONGO_URL`/`MONGO_COLLECTIONS` — os
testes cobertos não conectam em banco nenhum. Detalhe/cobertura/resultado
em `docker_explain.md`, seção "Suíte JUnit original".

## Build

```bash
docker build -t extrator-uschema oracle/
```

Os dois commits upstream vêm pinados como default de `ARG` no `Dockerfile` —
são os SHAs contra os quais este oráculo foi validado (patches aplicando
limpos, baseline JUnit 65/76, `northwind.xmi` equivalente ao gabarito):

| Repositório | SHA pinado |
|---|---|
| `modelum/uschema` | `6dfd6b4a6c04c67e49a80fb6cb6da9dd0f0f0f8c` |
| `modelum/uschema-inference` | `0f8f58c31f7661ce9be7333a1f34b9a05321a993` |

Buildar sem `--build-arg` reproduz exatamente o oráculo citado no TCC. Para
avançar o pin (deliberadamente, revalidando o conjunto), sobrescreva:

```bash
docker build \
  --build-arg USCHEMA_COMMIT=<sha> \
  --build-arg USCHEMA_INFERENCE_COMMIT=<sha> \
  -t extrator-uschema oracle/
```

## Tarefas (Fase 0.5)

- [x] `Dockerfile` + `entrypoint.sh` + `patches/` (patches #1/#4/#5/#6/#7
      verificados, #2/#3 satisfeitos estruturalmente, #8 deliberadamente
      fora — detalhe em `docker_explain.md`).
- [x] Rodar o `docker build` de verdade e validar que a imagem builda.
- [x] Rodar a extração dentro do container contra um banco de teste real
      (Northwind, MongoDB) — `out/northwind.xmi` gerado com sucesso.
- [x] Validar `out/northwind.xmi` contra o gabarito
      `resources/mongodb/model_northwind.xmi` via `compare()`
      (`uschema.validation.equivalence`, Fase 0.3): `equivalent: True`, zero
      divergências fatais (as 8 não-fatais batem com a assinatura do bug
      #8, esperado). Detalhe em `docker_explain.md`.
- [x] Testar o caminho Neo4j (`--kind neo4j`) de ponta a ponta — grafo mínimo
      (User/Movie, `WATCHED`/`FAVORITE`) via `cypher-shell`, `neo4j.xmi`
      gerado com sucesso.
- [x] Rodar a suíte JUnit original dentro da imagem — 65/76 passam; os 11
      que falham têm causa raiz identificada e são defeitos pré-existentes
      do repo original (não do empacotamento). Detalhe em `docker_explain.md`.
