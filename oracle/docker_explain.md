# docker_explain.md — Justificativas do oráculo Docker (Fase 0.5)

Os comentários no `Dockerfile`, `entrypoint.sh` e nos `.patch` ficam curtos de
propósito (no máximo 2 linhas cada). Este arquivo é onde a razão completa de
cada escolha, a alternativa descartada e a limitação conhecida ficam
registradas — citável no capítulo de reprodutibilidade do TCC sem precisar
reconstruir o raciocínio a partir de comentários telegráficos.

**Como ler.** Cada seção é uma decisão isolada, na ordem aproximada em que
aparece no `Dockerfile`. Decisões marcadas **testado de verdade** foram
confirmadas rodando `docker build`/`docker run` reais (2026-07-15, Docker
Desktop no Windows, host networking habilitado, contra o dataset Northwind) —
não só verificadas em teoria ou por inspeção de código.

---

## Sumário

| Decisão | Onde | Motivo resumido |
|---|---|---|
| Commit pinado (SHA, não branch) | `ARG USCHEMA_COMMIT`/`_INFERENCE_COMMIT` | reprodutibilidade citável no TCC |
| Maven puro, sem Eclipse | `uschema-build/runner/pom.xml` | build via CLI, containerizável |
| Build Maven único (unificado) | idem | Mongo migrado pra Spark 3.0.1/Scala 2.12 (era 2.4.1/2.11) — testado idêntico, elimina a necessidade dos dois builds |
| `entrypoint.sh` como ponte | `entrypoint.sh` | os `main` Java não aceitam `--db`/`--kind` diretamente; traduz pro `-Dexec.mainClass`/`config.properties` que cada um espera |
| Patches #1, #4, #5 | `patches/000{1,4,5}-*.patch` | incompatibilidade de build (Guice, JDK 8, hardcode de máquina) |
| Patches #6, #7 | `patches/000{6,7}-*.patch` | crashes reais — sem eles não há XMI algum |
| #8 sem patch | — | preserva a divergência que a Fase 0.3 precisa citar |
| #2, #3 sem patch | — | pom original nunca é lido nesta build |
| `dependency:go-offline` sem `-o` no `compile` | `Dockerfile` | resolução incompleta, descoberto rodando de verdade |
| `mkdir -p outputs/` no caminho Mongo | `entrypoint.sh` | `EcoreModelIO.write()` não cria a pasta sozinho |
| Suíte JUnit original (baseline, manual) | `uschema-build/runner/pom.xml` | 65/76 passam; os 11 que falham são defeitos pré-existentes do repo original, não do empacotamento |
| Contrato `--db`/`--kind` (CLI args) | `entrypoint.sh` | volta ao desenho original do plano (`fase0_fundacao_oraculo.md`), viável depois da unificação — só `MONGO_URL`/`MONGO_COLLECTIONS` continuam em env var |
| Correções de revisão automática (CodeRabbit) | `Dockerfile`/`entrypoint.sh`/`patch #5`/`runner/pom.xml` | pin por digest, validação de `DB_NAME`, `org.json` atualizado; detalhe na seção "Mudanças a partir de revisão automática" |

---

## Commit pinado, não branch

`ARG USCHEMA_COMMIT`/`USCHEMA_INFERENCE_COMMIT` trazem como **default** os dois
SHAs contra os quais este oráculo foi de fato validado:

| Repositório | SHA pinado |
|---|---|
| `modelum/uschema` | `6dfd6b4a6c04c67e49a80fb6cb6da9dd0f0f0f8c` |
| `modelum/uschema-inference` | `0f8f58c31f7661ce9be7333a1f34b9a05321a993` |

O pin deve ser **explícito**, nunca implícito num "a branch não costuma
mudar": um commit novo em qualquer um dos dois repos, mesmo que raro,
poderia alterar silenciosamente o que o TCC cita como oráculo de referência.
Reprodutibilidade citável exige apontar pra um SHA fixo, não para "o que
estava em `main` no dia em que alguém rodou `docker build`".

Por isso o SHA fica **registrado no `Dockerfile`**, e não resolvido na hora do
build via `git ls-remote` — que devolve a ponta da branch do dia, exatamente o
"o que estava em `main`" que o parágrafo acima recusa. Tudo que esta fase
afirma está amarrado a esses dois commits: os patches aplicando sem
*fuzz*/*reject*, o baseline JUnit 65/76 e o `northwind.xmi` saindo equivalente
ao gabarito.

Exigir `--build-arg` sem default (como a primeira versão fazia) força um SHA
**qualquer** a ser informado: garante explicitude, não reprodutibilidade. Com o
default, build sem argumento nenhum reproduz o oráculo citado, e avançar o pin
segue sendo ato deliberado — sobrescrever o `ARG`, revalidando o conjunto. A
branch default dos dois repositórios upstream é `main` (não `master`), caso
precise.

**Mesmo princípio aplicado à imagem base.** `FROM maven:3.9-eclipse-temurin-8`
sozinho é uma *tag*, não um artefato imutável — o mantenedor pode
republicá-la (patch de segurança, rebuild) e o `docker build` passaria a
puxar bytes diferentes sem nenhuma mudança neste repo. Pinado por digest
(`@sha256:b595d84...`, capturado via
`GET https://hub.docker.com/v2/repositories/library/maven/tags/3.9-eclipse-temurin-8/`,
campo `digest` de nível superior — é o digest do manifest list multi-arch,
não de uma arquitetura específica, então continua resolvendo pra
amd64/arm64/etc. corretamente no pull). Se a tag precisar avançar (nova
versão do Maven/JDK), o digest é atualizado manualmente, do mesmo jeito
deliberado que os `USCHEMA_COMMIT`/`USCHEMA_INFERENCE_COMMIT`.

## Maven puro (sem Eclipse), build único

Os repositórios upstream foram desenvolvidos como projetos Eclipse (PDE),
com resolução de dependência via `Require-Bundle` OSGi. Um Dockerfile não
tem GUI nem workspace do Eclipse — replicar isso exigiria empacotar o IDE
inteiro (instalação completa + X virtual + automação de clique, já que não
existe modo headless oficial do Eclipse para "Run As Java Application", só
para builds PDE/Tycho). Nenhum ganho de comportamento justificaria esse
custo: o programa Java, uma vez compilado, não sabe nem se importa se o
classpath foi calculado pelo Eclipse ou por outra ferramenta — só a JVM
importa em tempo de execução.

A alternativa adotada é `oracle/uschema-build/runner/pom.xml`: um projeto
Maven "runner" (não os `pom.xml` originais de cada módulo) que usa
`build-helper-maven-plugin` (goal `add-source`) para somar os source folders
certos num único classpath, substituindo manualmente o que o Eclipse
resolvia via `Require-Bundle`. Essa abordagem foi validada de ponta a ponta
**(testado de verdade)**: o runner compila e o container gera XMI correto
tanto pro caminho Mongo quanto pro Neo4j, contra o Northwind e um grafo
mínimo, respectivamente.

Sem *fat jar*: `exec-maven-plugin` sem `mainClass` fixo — o `entrypoint.sh`
escolhe qual `main` rodar via `-Dexec.mainClass` na hora, já que os dois
convivem no mesmo classpath agora.

## Unificação mongo+neo4j num build único (testado de verdade)

Até 2026-07-15 este Dockerfile tinha **dois** builds Maven independentes
(`uschema-build/mongo`, `uschema-build/neo4j`), porque os dois caminhos de
extração pareciam usar versões de Spark/Scala incompatíveis: MongoDB em
Spark 2.4.1/Scala 2.11 (`mongo-spark-connector_2.11`), Neo4j em Spark
3.0.1/Scala 2.12 (`neo4j-spark-connector 2.4.5-M2`, só disponível via
`repos.spark-packages.org`).

Essa suposição nunca tinha sido testada — só herdada das versões que cada
caminho usava originalmente. Testando de verdade (bind-mount de um
`pom.xml` experimental sobre a imagem já buildada, sem rebuild, pra não
mexer no artefato real):

1. **Mongo isolado em Spark 3.0.1/Scala 2.12**
   (`mongo-spark-connector_2.12:3.0.1`, que existe no Maven Central — linha
   antiga baseada em RDD, distinta do connector 10.x/DataSource-V2 mais
   recente) compilou limpo e extraiu o Northwind com sucesso.
   `compare()` (Fase 0.3) contra `resources/mongodb/model_northwind.xmi` e
   contra o XMI gerado pelo Spark 2.4.1 original: **`equivalent: True`** nos
   dois casos, mesmas 8 divergências não-fatais (assinatura do bug #8) —
   comportamento idêntico entre as duas versões de Spark.
2. **Mongo + Neo4j num classpath único** (mesmo pom, com os dois conjuntos
   de dependências e `add-source` combinados): compilou limpo — sem colisão
   transitiva entre `mongo-spark-connector_2.12` e `neo4j-spark-connector`.
3. **Execução real dos dois caminhos** nesse classpath único (Northwind via
   Mongo, grafo mínimo via Neo4j): os dois XMIs gerados batem
   **exatamente** com os XMIs dos builds separados antigos —
   `northwind-unified.xmi` `equivalent: True` (mesmas 8 divergências do bug
   #8) contra o gabarito e contra `northwind.xmi`; `neo4j-unified.xmi`
   **byte-a-byte idêntico em estrutura** (`equivalent: True`, zero
   divergências) contra `neo4j.xmi`.

Uma armadilha de metodologia encontrada nesse processo (não afeta o
`Dockerfile` real, só o jeito de testar): `mvn exec:java` sozinho **não**
recompila nem recopia recursos — ele usa o que já está em `target/classes`.
Testando com `docker run --rm` (container descartável) chamando só
`exec:java`, a extração Neo4j falhava com `ClassNotFoundException`, porque
o `target/classes` daquele container efêmero vinha do build da imagem
*antiga* (só com classes do Mongo). A correção foi rodar `compile` e
`exec:java` no mesmo `docker run`. No `Dockerfile` real isso não é um
problema porque o `compile` roda uma vez, no build da imagem — o
`entrypoint.sh` só chama `exec:java` depois, contra classes já compiladas e
persistidas na imagem final.

Com os três pontos confirmados, o `Dockerfile`/`uschema-build/` reais foram
atualizados pra usar só `uschema-build/runner/pom.xml`, eliminando a
duplicação de `dependency:go-offline`/`compile` e os dois diretórios
paralelos. Backup da versão com dois builds guardado pelos autores fora
deste repo.

## Por que precisa de `entrypoint.sh`

Os dois `main` Java **não** implementam a interface simples
`--db`/`--kind` diretamente — descoberto lendo o código-fonte real, não
assumido:

- **Neo4j** (`Neo4j2USchemaMain`, depois do patch `0005`): aceita o nome do
  banco como `args[0]`. A URL/usuário/senha do bolt (`bolt://localhost:7687`,
  `neo4j`/`test`) continuam fixos no código-fonte — não vêm de argumento nem
  variável de ambiente (ver seção "Limitações conhecidas").
- **MongoDB** (`MongoDB2USchemaMain`): não lê `args` nenhum. Carrega um
  `config.properties` do **classpath**, com três chaves
  (`MONGO_URL`/`MONGO_DATABASE`/`MONGO_COLLECTIONS`, conferidas em
  `Constants.java` do módulo). Não tem como passar isso por linha de comando.

`entrypoint.sh` faz a ponte: lê `--db`/`--kind` como argumentos de linha de
comando (`docker run extrator-uschema --db <nome> --kind <mongodb|neo4j>`,
o mesmo contrato originalmente esboçado em `fase0_fundacao_oraculo.md`,
antes de virar interface via variável de ambiente na primeira versão), gera
o `config.properties` na hora pro caso Mongo (usando `MONGO_URL`/
`MONGO_COLLECTIONS`, que continuam em variável de ambiente — não viram
flag porque `MONGO_URL` pode carregar credenciais e `MONGO_COLLECTIONS` é
uma lista, os dois mais naturais como env que como argv), escolhe o
`-Dexec.mainClass` certo pro `uschema-build/runner` único, e copia o `.xmi`
resultante pra `/output/<DB_NAME>.xmi`.

**Sobre a mudança de env vars pra CLI args:** o contrato originalmente
esboçado em `fase0_fundacao_oraculo.md` (antes de qualquer implementação)
já era `--db`/`--kind`. A primeira versão implementada usou `KIND`/
`DB_NAME` como variável de ambiente em vez disso — decisão de conveniência
(consistência com `MONGO_URL`/`MONGO_COLLECTIONS`, que precisam ser env de
qualquer forma), não uma necessidade técnica imposta pelos dois builds
separados. Reescrito agora pra `--db`/`--kind` a pedido explícito dos
autores, batendo com o contrato original do plano.

## Patches: o que vira `.patch` e o que não vira

Numeração herdada do catálogo de 8 defeitos em `bugs_originais.md`.

### #1, #4, #5 — incompatibilidades de build

Bugs/incompatibilidades no código-fonte em si, sem os quais o build nem
compila ou o `main` nem roda fora da máquina do autor original:

- **#1** — `MongoDB2USchemaMain.configure()` está sem
  `bind(FeatureAnalyzer.class).to(DefaultFeatureAnalyzer.class)` no binding
  Guice.
- **#4** — `Path.of(...)` (API do Java 11) usado em 5 arquivos de produção
  (`MongoDB2USchema`, `Neo4j2USchema`, `Json2USchemaModel`,
  `USchemaToDocumentDb`, `EcoreModelIO`), incompatível com o JDK 8 exigido
  pelo Spark 2.4/3.0.1. Trocado por `Paths.get(...)`. Um 6º arquivo,
  `ModelIOTest.java` (teste, não produção), tinha o mesmo bug — descoberto
  só depois, rodando a suíte JUnit (ver seção "Suíte JUnit original"
  abaixo) — e entrou no mesmo `.patch`.
- **#5** — `Neo4j2USchemaMain` tinha `hadoop.home.dir` hardcoded pra
  `F:\hadoop` (caminho da máquina do autor original) e supressão de
  log/stderr. Removidos; **adicionado** `args[0]` como nome do banco (não
  existia no original — sem isso não dá pra parametrizar via
  `entrypoint.sh`). **Também adicionada** uma validação de `databaseName`
  (rejeita `/`, `\` e `..`) logo depois de ler `args[0]` — defesa em
  profundidade contra o mesmo problema que o `entrypoint.sh` já bloqueia no
  caminho oficial (`--db`), mas que ficaria aberto pra quem chamar
  `mvn exec:java -Dexec.args=...` direto, pulando o `entrypoint.sh` (como
  fizemos várias vezes nesta sessão, pra debug). `databaseName` compõe
  caminho de arquivo (`OUTPUTS_FOLDER + databaseName + ...`); sem a
  validação, um valor como `../outside` escaparia da pasta de saída.

### #2, #3 — satisfeitos estruturalmente, sem `.patch`

- **#2** (pin de versão do Jackson no pom do `doc2uschema`) e **#3** (alvo
  JDK 8): o pom de cada módulo original **nunca é invocado** nesta build —
  `uschema-build/runner/pom.xml` substitui completamente a resolução de
  dependência (`dependencyManagement` fixa Jackson 2.10.5 pros dois
  caminhos, desde a unificação — antes era 2.6.7.1 pro Mongo/Spark 2.4.1 e
  2.10.5 pro Neo4j/Spark 3.0.1) e o `<source>`/`<target>` do compilador
  (`1.8`) por conta própria. Aplicar um patch num pom que nunca é lido seria
  um no-op documentado como se fizesse algo — por isso ficou de fora, com
  esta nota no lugar do patch.

### #6, #7 — crashes reais, descobertos rodando de verdade

A primeira versão deste Dockerfile deixava #6, #7 e #8 igualmente sem
patch, generalizando a lógica "bug de corretude, corrigido só no porte
Python". Isso estava errado para #6 e #7: rodar o build/run de verdade
contra o Northwind expôs os dois como **crashes que abortam o job Spark
inteiro**, não como números levemente errados.

- **#6** — `Helpers.generateDocumentPair` chama `doc.getObjectId("_id")`
  sem checar o tipo, lançando `ClassCastException` pra qualquer coleção com
  `_id` não-`ObjectId` (comum em dados de origem relacional, como o próprio
  Northwind). `bugs_originais.md` já previa essa correção especificamente
  no oráculo (cabeçalho "Correção (patch no oráculo, por construção no
  porte)"). Corrigido lendo `_id` genericamente
  (`doc.get("_id")` + `instanceof ObjectId`), com timestamp `0L` quando não
  é `ObjectId` — consequência aceitável porque timestamp não entra na
  equivalência estrutural.
- **#7** — depois de corrigir o #6, a extração avançou e bateu num segundo
  crash: `USchemaModelBuilder.structuralFeatureFromSchemaComponent(ArraySC)`
  chama `sc.getInners().get(0)` **antes** de checar `sc.size() == 0`,
  lançando `IndexOutOfBoundsException` ("Index: 0, Size: 0") pra qualquer
  documento com um array vazio (~15% dos documentos na Rota B do plano de
  escala, por `bugs_originais.md`). `bugs_originais.md` não usava o mesmo
  cabeçalho "patch no oráculo" pra esse item, mas o sintoma documentado já
  dizia a mesma coisa — não é um bug "silencioso", é outro crash
  incondicional. Corrigido aproveitando o short-circuit do `||` que já
  existia na condição, só materializando `sc.getInners().get(0)` depois de
  saber que a lista não está vazia.

Nenhum dos dois produz XMI parcial ou número errado — produz **zero XMI**.
Sem os patches `0006`/`0007`, o oráculo não gera saída alguma pra qualquer
dataset realista com `_id` não-`ObjectId` ou algum array vazio.

### #8 — deliberadamente sem patch

Ao contrário de #6/#7, o bug #8 (`SchemaInference`, `meta`/contagem
descartado ao colapsar uma variação já existente) **não derruba o job** —
produz XMI completo, só com a contagem estruturalmente errada. Se o oráculo
também o corrigisse, ele deixaria de ser um baseline independente nesse
ponto: a comparação estrutural (Fase 0.3, `uschema.validation.equivalence`)
pararia de conseguir mostrar a diferença de comportamento que o capítulo de
bugs do TCC documenta — o porte Python corrige #8 "por construção", e é
justamente contra um oráculo que ainda tem o bug que essa correção precisa
ser demonstrada.

O oráculo existe para reproduzir o comportamento **original**, bugs
inclusos; só os bugs que impedem sequer compilar, rodar ou completar a
extração (#1–#7) são corrigidos.

## Como os patches foram verificados

Cada `.patch` foi construído comparando o texto **pristine** dos
arquivos-alvo (baixado direto de `raw.githubusercontent.com/modelum/...`,
branch `main`, antes de qualquer edição) contra a versão corrigida, com
`diff -u`. Depois, cada `.patch` foi re-aplicado com `patch -p1` contra uma
cópia limpa do pristine, e o resultado conferido byte a byte (`diff -r`)
contra o texto esperado — todos aplicam sem *fuzz* nem *reject*.

Além disso, os patches foram re-verificados de ponta a ponta num **clone
real** dos dois repositórios, nos commits pinados atuais
(`6dfd6b4a...`/`0f8f58c3...`) — não só contra os arquivos isolados. Essa
segunda verificação foi o que pegou `USchemaToDocumentDb.java`: tem o mesmo
`Path.of(...)` dos outros arquivos do patch #4, mas tinha ficado de fora da
lista original — só apareceu como erro de compilação real no
`docker build` (`cannot find symbol: method of(String)`), porque esse
arquivo só entra no classpath do runner Mongo (via
`es.um.uschema.doc2uschema`), então uma checagem arquivo-a-arquivo isolada
não o testava em conjunto com os outros.

## `dependency:go-offline` incompleto

O `Dockerfile` roda `mvn dependency:go-offline` e depois `mvn compile` (uma
vez só, desde a unificação em `uschema-build/runner`), mas o `compile`
**não** usa `-o` (offline) — de propósito, ao contrário do que a primeira
versão fazia. `dependency:go-offline` é *best-effort* e não resolve 100% da
árvore de dependências transitivas nesse tipo de build agregado via
`build-helper-maven-plugin`: rodando de verdade, faltaram `commons-codec`,
`httpclient`, `xml-apis`, `scala-reflect` e `joda-time` — o `compile` em
modo offline falhava com "Cannot access central... in offline mode".

A rede já está disponível nesse estágio do build (é a mesma usada pro
`git clone` e pelo próprio `go-offline`), então tirar o `-o` do `compile`
não custa nada em reprodutibilidade — o offline continua valendo em tempo
de `docker run` (`entrypoint.sh` chama `mvn -o exec:java`), que é quando de
fato não deve depender de internet além do banco-alvo.

## Pasta `outputs/` ausente no caminho Mongo

`MongoDB2USchema.write()` grava em `./outputs/model.xmi` (caminho relativo
ao diretório de trabalho do `mvn exec:java`), mas — ao contrário do caminho
Neo4j, que já tem `new File(...).mkdirs()` antes de escrever — nunca cria
essa pasta sozinho. Sem isso, `EcoreModelIO.write()` falhava com
`NoSuchFileException: ./outputs/model.xmi` no primeiro `docker run` real,
depois de toda a extração já ter rodado sem erro. Não é um bug do Java (nem
cataloga-do em `bugs_originais.md`) — é uma lacuna de infraestrutura do
próprio `entrypoint.sh`, corrigida com um `mkdir -p "$RUNNER/outputs"` antes
do `mvn exec:java` no caminho Mongo.

## Suíte JUnit original (baseline)

Não é parte do `Dockerfile`/`entrypoint.sh` — é um comando manual (`mvn
test` dentro da imagem já buildada), fora da interface fixa
`--db`/`--kind`, só pra ter um baseline citável de "os testes do autor
original passam".

**Cobertura**: só os bundles já presentes no classpath do runner único
(`es.um.uschema.utils`, `es.um.uschema.doc2uschema`,
`es.um.uschema.mongodb2uschema`, mais o comparador). Fora do
escopo: os testes de dataset em `es.um.uschema.documents/test/test/*`
(ex.: `UserProfileTest`) — dependem de um MongoDB já populado num formato
específico (mapreduce pré-computado) que não está no repo, mesmo tipo de
dependência externa do `ModelIOTest` abaixo.

**Setup**: `uschema-build/runner/pom.xml` ganhou uma segunda
execução do `build-helper-maven-plugin` (`add-test-source`, apontando pras
pastas `test/` dos bundles já cobertos) mais `junit:junit:4.13.2`,
`junit-jupiter:5.9.3` e `junit-vintage-engine:5.9.3` — o repo original
mistura JUnit4 e JUnit5 entre arquivos de teste diferentes, então os dois
motores rodam lado a lado via `maven-surefire-plugin:2.22.2`. Rodar com
`-o` (offline) funciona porque as dependências de teste já foram baixadas
no `dependency:go-offline` do build da imagem.

**`ModelIOTest.java` tinha o mesmo bug do patch #4** (`Path.of`, API do
Java 11, incompatível com JDK 8) — descoberto rodando `mvn test` de
verdade, não visível na inspeção original dos 5 arquivos do patch #4 (que
cobria só código de produção, não teste). Corrigido estendendo
`0004-path-of-to-paths-get-uschema.patch` com um segundo hunk, verificado
do mesmo jeito que o resto (clone limpo do commit pinado, `patch -p1`,
`diff -r` contra o esperado).

**Resultado — 65 de 76 testes passam.** Os 11 que falham têm causa raiz
identificada lendo o código-fonte real do commit pinado, e nenhum aponta
pra um problema do empacotamento Docker ou dos patches #1–#7:

- `OptionalTest` (1): o helper `regression.config.OptionalTestConfig`
  (dentro da própria pasta `test/`) copia o módulo Guice de
  `DefaultBuildUSchema` mas esquece
  `bind(FeatureAnalyzer.class).to(DefaultFeatureAnalyzer.class)` — mesma
  família do bug do patch #1, só que num arquivo de teste que nunca
  recebeu a correção original.
- `ModelIOTest.testOpenWrite`/`testWrite` (2): lêem/escrevem num projeto
  irmão (`es.um.uschema.models`) nunca clonado — dependência externa ao
  repo, mesmo padrão do resto das limitações conhecidas.
- `CompareDataTypeTest`/`ComparePropertyTest` (9): os testes chamam a
  fábrica com `null` de propósito (`f.createPList(null)`,
  `f.createReference(null, 0, 0, null)`, etc.), esperando um objeto
  "vazio" pro comparador testar contra. Mas `USchemaFactory.java` do
  mesmo commit **valida e lança `IllegalArgumentException`** pra esses
  mesmos argumentos — teste e implementação, ambos originais, já estavam
  inconsistentes entre si antes de qualquer patch nosso (confirmado lendo
  o `USchemaFactory.java` pristine, não por suposição).

Nenhum dos 11 foi corrigido: são bugs no **próprio código de teste** do
repo original, fora do escopo de "impede build/execução" que justificou os
patches #1–#7. Corrigi-los alteraria o comportamento do oráculo além do
que foi pedido.

## Limitações conhecidas

- **Credenciais do Neo4j continuam fixas no código-fonte** mesmo depois do
  patch `0005` (`bolt://localhost:7687`, usuário `neo4j`, senha `test`).
  Funciona sem alterar mais nada só se o Neo4j alvo estiver alcançável em
  `localhost:7687` dentro do container (daí o `--network=host`) com auth
  desabilitada (`NEO4J_AUTH=none` — variável de ambiente documentada da
  imagem oficial `neo4j` do Docker Hub, que desliga a autenticação do
  bolt). Parametrizar usuário/senha/URL por variável de ambiente exigiria
  um patch adicional, não incluído por não ter sido pedido.
- **`docker build` deste `Dockerfile` nunca foi rodado num ambiente
  diferente do Docker Desktop/Windows usado em 2026-07-15** — não há
  garantia de que os mesmos comandos (`mkdir -p`, `patch`, `git`) se
  comportem idênticos em outro SO/versão de Docker, embora a imagem base
  seja Linux em qualquer plataforma.

## Validação real realizada

`docker build` e `docker run` foram testados de verdade (2026-07-15, Docker
Desktop no Windows, host networking habilitado) contra o dataset Northwind
real (17 coleções, importado via `mongodb-community-server`). Isso pegou os
três problemas documentados acima (`dependency:go-offline` incompleto, os
crashes reais de #6/#7, e a pasta `outputs/` ausente) — nenhum deles
aparecia na verificação isolada dos `.patch` contra o texto-fonte.

Depois das correções, `out/northwind.xmi` foi gerado com sucesso e validado
contra o gabarito `resources/mongodb/model_northwind.xmi` via `compare()`
(`uschema.validation.equivalence`, Fase 0.3): **`equivalent: True`**, zero
divergências fatais. As 8 divergências não-fatais (todas em
`Orders`/`Purchase_orders`, `count` errado ou variação órfã) batem
exatamente com a assinatura do bug #8 — esperado, já que #8 continua
deliberadamente sem patch no oráculo (ver seção acima).

O caminho Neo4j (`--kind neo4j`) também foi testado de ponta a ponta: um grafo
mínimo (`User`/`Movie`, relacionamentos `WATCHED`/`FAVORITE`, criado via
`cypher-shell` contra `neo4j:5.26` com `NEO4J_AUTH=none`) gerou
`neo4j.xmi` com sucesso. Sem gabarito comparável (o grafo foi construído
ad hoc, não reproduz nenhum dataset com XMI-gabarito existente), então não
houve validação estrutural aqui — só confirmação de que o caminho roda sem
erro.

A suíte JUnit original também foi rodada dentro da imagem (ver seção
acima): 65/76 testes passam, com causa raiz identificada pros 11 que
falham.

A unificação mongo+neo4j num build único e o novo contrato `--db`/`--kind`
(ver seções acima) também foram validados de ponta a ponta: os dois XMIs
gerados pelo classpath unificado batem exatamente com os dos builds
separados antigos, via `compare()`.

## Mudanças a partir de revisão automática (CodeRabbit)

Depois da unificação mongo+neo4j, a revisão automática do CodeRabbit sobre o
diff apontou achados que motivaram as correções abaixo (2026-07-15). Os
comentários curtos que ficariam no código (`Dockerfile`/`entrypoint.sh`/
`.patch`) foram deliberadamente **removidos de lá** e centralizados aqui —
mesma convenção já usada pro resto do arquivo ("Como ler", no topo): código
com comentário mínimo, razão completa só neste documento.

### Aplicadas

- **Imagem base pinada por digest.** `FROM maven:3.9-eclipse-temurin-8`
  sozinho é uma *tag*, não um artefato imutável — o mantenedor pode
  republicá-la (patch de segurança, rebuild) e o `docker build` passaria a
  puxar bytes diferentes sem nenhuma mudança neste repo. Pinado por digest
  (`@sha256:b595d84...`, capturado via
  `GET https://hub.docker.com/v2/repositories/library/maven/tags/3.9-eclipse-temurin-8/`,
  campo `digest` de nível superior — é o digest do manifest list multi-arch,
  não de uma arquitetura específica, então continua resolvendo pra
  amd64/arm64/etc. corretamente no pull). Mesmo princípio do commit pinado
  dos fontes (ver "Commit pinado, não branch" acima). Se a tag precisar
  avançar (nova versão do Maven/JDK), o digest é atualizado manualmente.
- **`entrypoint.sh`: guarda antes do `shift 2`.** `--db`/`--kind` sem valor
  (ex.: `--db` como último argumento) fazia `shift 2` falhar sob `set -e`,
  e o script morria sem mostrar o uso esperado. Corrigido checando
  `[ $# -ge 2 ]` antes de cada `shift 2`.
- **`entrypoint.sh`: validação de `DB_NAME`.** `DB_NAME` vira nome de
  arquivo (`$OUTPUT_DIR/${DB_NAME}.xmi`) e, no caminho Mongo, uma linha de
  `config.properties` (`MONGO_DATABASE=${DB_NAME}`). Sem validação, um
  valor com barra ou `..` poderia escrever fora de `$OUTPUT_DIR`, e um
  valor com quebra de linha poderia injetar uma propriedade extra no
  `config.properties` (ex.: uma segunda linha `MONGO_URL=...`,
  redirecionando a conexão configurada). Corrigido rejeitando `/`, `\` e
  quebra de linha em `DB_NAME` antes de usá-lo.
- **Patch #5: mesma validação no Java.** A validação do `entrypoint.sh`
  cobre o caminho oficial (`--db`/`--kind`), mas não protege quem rodar
  `mvn exec:java -Dexec.args=...` direto, pulando o `entrypoint.sh` — como
  foi feito várias vezes nesta sessão, pra debug/experimento (ver
  "Unificação mongo+neo4j..." acima). `databaseName` (`args[0]`) compõe
  `OUTPUTS_FOLDER + databaseName + ...` em `Neo4j2USchemaMain.main()`; sem
  validação, um valor como `../outside` escaparia da pasta de saída.
  Estendido o patch `0005-neo4jmain-cli-arg-no-hardcode.patch` com a mesma
  checagem (rejeita `/`, `\`, `..`), verificado do mesmo jeito que as
  outras extensões de patch desta sessão (clone limpo do commit pinado,
  `patch -p1`, `diff -r` contra o esperado, zero `.orig`/`.rej`).
- **`org.json` 20180130 → 20231013** em `uschema-build/runner/pom.xml` —
  versão antiga afetada por uma vulnerabilidade de negação de serviço
  conhecida; a nova existe no Maven Central (confirmado via
  `search.maven.org`) e mantém compatibilidade com JDK 8.
- **Contagem do patch #4 corrigida.** A descrição original ("5 arquivos")
  não contava `ModelIOTest.java`, adicionado depois — na sessão do
  baseline JUnit — como um 6º arquivo (teste, não produção). Corrigido
  aqui e em `patches/README.md` pra descrever consistentemente 5 arquivos
  de produção + 1 de teste.

### Deliberadamente não aplicadas

- **Rodar o container como usuário não-root.** Achado genérico de
  linter/SAST (`Source: Linters/SAST tools`), correto em abstrato — mitiga
  processo comprometido escrevendo fora do que deveria dentro do
  container. Mas o modelo de ameaça não bate bem com o uso real daqui: o
  oráculo é `--rm`, rodado manualmente, sem porta exposta, sem entrada de
  rede não confiável — quem roda o comando já tem controle total da
  própria máquina. Implementar exigiria criar usuário, ajustar dono de
  `/app` e do cache Maven (`~/.m2`, preenchido como root durante o
  `docker build`) e garantir que esse usuário escreve no bind mount
  `/output` — justamente o ponto mais frágil já visto quebrar nesta sessão
  (bug do `MSYS_NO_PATHCONV` no Windows/Git Bash). Custo/risco de
  implementação alto, ganho de segurança baixo pro caso de uso real.
- **Manifesto separado para os SHAs aprovados** (`USCHEMA_COMMIT`/
  `USCHEMA_INFERENCE_COMMIT`) — como **arquivo à parte**. A preocupação de
  fundo (registrar quais SHAs são os aprovados) era procedente e foi
  atendida: os SHAs validados agora são o **default do `ARG`** no
  `Dockerfile`, documentados em "Commit pinado, não branch". Isso registra o
  pin no lugar onde ele é consumido, sem a indireção de mais um arquivo pra
  um componente que já é opcional e fora da entrega.
