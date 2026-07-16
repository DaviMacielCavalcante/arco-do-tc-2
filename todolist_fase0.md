# TO-DO — Fase 0: Fundação + oráculo

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi Cavalcante · João — CESUPA
**Base:** `fase0_fundacao_oraculo.md` · **Validação:** `roteiro_experimental.md` · **Técnica:** `analise_ferramenta_uschema.md`
**Prioridade:** imediata — pré-requisito de todas as fases seguintes.

> **Organização por entrega.** As tarefas estão agrupadas por **entregável** (0.0–0.6),
> não por autor. O trabalho é amplo e **compartilhado** entre os dois autores: cada bloco
> define uma **Saída** que serve de critério de "pronto"; quem pega qual bloco é combinado
> a cada ciclo, sem dono fixo por tarefa ou por fase.
>
> **Ideia central.** A correção do porte não vem de uma fonte só: vem em **camadas** (0.4). A camada mais forte e mais barata — os testes de regressão JUnit portados — localiza o erro no módulo **sem depender do Docker**. O Docker fica reduzido a gerador de gabarito para datasets sem golden-master pronto.

---

## 0.0 — Fundação do repositório Python  ✅ *(scaffold pronto)*

> Estrutura montada com `uv`; **sem implementação** (o código dos módulos é dos autores). Serve de esqueleto para as tarefas 0.1–0.6.

- [x] Projeto `uv` inicializado (layout `src/`, pacote `uschema`), Python **pinado em 3.12** (o PySpark ainda não suporta 3.14).
- [x] Dependências de runtime declaradas: `pyecore`, `pyspark`, `pymongo`, `neo4j`, `inflection`, `pydantic`, `loguru`; dev: `ruff`, `mypy`, `pytest`, `pytest-cov` (lockfile resolvido).
- [x] Ferramental configurado no `pyproject.toml`: `ruff` (docstrings NumPy, linha 100), `mypy` estrito, `pytest`.
- [x] Esqueleto de pacotes criado, um por fase: `metamodel/` (0.1–0.2) · `naming/` (0.6) · `validation/` (0.3) · `intermediate/` (1.1) · `inference/` (1.2–1.4) · `extractors/` (2).
- [x] Diretórios de apoio: `resources/` (`.ecore` + XMIs), `oracle/` (Dockerfile + `patches/`), `scripts/` (baterias), `tests/` (`unit`/`regression`/`datasets`), cada um com `README.md` de escopo; `CLAUDE.md` do repositório.
- [x] Copiar para `resources/` os artefatos de referência do repo Java original: `uschema.ecore`, `model_northwind.xmi`, `model.xmi`, `movies_min.xmi` (+ XMIs de escala Neo4j `up_*`).

**Saída:** repositório com esqueleto, ferramental e dependências prontos — `uv sync` resolve, `ruff`/`mypy`/`pytest` rodam limpos no esqueleto vazio.

---

## 0.1 — PyEcore sobre o `uschema.ecore`

> Metamodelo favorável: 19 EClasses em 98 linhas, sem OCL e sem EAnnotations (puramente estrutural).

- [x] Instalar PyEcore (`pip install pyecore`); carregar `uschema.ecore` via `ResourceSet`/`metamodel_resource`. → `registry.load_metamodel`
- [x] Confirmar acesso reflexivo às 19 EClasses; instanciar manualmente um `USchema` mínimo (1 `EntityType` + 1 `StructuralVariation` + 1 `Attribute`) e serializar em XMI. → `build_minimal_schema` + testes (fixture com `type` válido; asserts por valor pegam o silent-swallow do PyEcore)
- [x] Decidir **API reflexiva** (manipular `EObject` dinamicamente) vs. **`pyecoregen`** (gerar classes do `.ecore`). **Decidido: reflexivo** — ergonomia ok na prática (0.1/0.2).
- [x] Tratar o gap conhecido: PyEcore não suporta `genmodel` multi-arquivo — se o `.ecore` referenciar outros pacotes, achatar para um único EPackage no fork. **Não se aplica:** o `uschema.ecore` é 1 único EPackage (nsURI `http://www.modelum.es/USchema`) — verificado.

**Saída:** módulo Python em `src/uschema/metamodel/` que cria, lê e serializa modelos U-Schema em XMI.

---

## 0.2 — Round-trip de XMI

- [x] Ler `model_northwind.xmi` (19 `EntityType`, incluindo o agregado `Detail`) com PyEcore. → `xmi.load_model` (validado: 19 entidades + `Detail`)
- [x] Reserializar e validar que o modelo recarregado é **estruturalmente idêntico** ao original (não precisa ser byte a byte — EMF tem convenções próprias de `xmi:id`/ordenação).
- [x] Repetir com `model.xmi` (mínimo MongoDB) e `movies_min.xmi` (mínimo Neo4j, com `RelationshipType`).

---

## 0.3 — Harness de equivalência estrutural  *(instrumento central de validação)*

> **Não inventar do zero — espelhar o `USchemaCompareMain`** (`es.um.uschema.*.validation`), que já existe no Java: `startComparison(USchema s1, USchema s2)` compara nome → contagem de `EntityType`/`RelationshipType` → variações (via `CompareSchemaType`/`CompareStructuralVariation`), com log de *hits*/*warnings* e normalização de caixa. Reproduzir a mesma noção de equivalência evita ficar mais rígido ou mais frouxo que o original.

- [x] Ler `USchemaCompareMain` (+ toda a árvore `custom/compare/*`) e replicar sua semântica em Python.
- [x] Portar as funções de comparação: `compare_primitive_type`, `compare_datatype`, `compare_p{list,set,map,tuple}`, `compare_attribute`, `compare_feature`, `compare_key`, `compare_variation`, `compare_aggregate`, `compare_reference`, `compare_names`, `_same_container`, `_match_bag`.
- [x] Cobrir com testes unitários (`tests/unit/test_equivalence.py`, 78 testes) e validá-los por **mutation testing** — 5 mutações reintroduzindo bugs reais, todas pegas.
- [x] Catalogar os defeitos do original em `bugs_originais.md` (#1–#8 já conhecidos + C1–C7 novos, com evidência e citação de linha).
- [ ] ~~Implementar a **assinatura canônica** de uma variação~~ — **descartado deliberadamente.** O Java não usa assinatura canônica: `CompareStructuralVariation` casa as `features` como **multiset**, via remoção de uma cópia. Portamos essa mecânica (`_match_bag`), que é mais fiel. Uma assinatura ordenada imporia uma noção de igualdade que o oráculo não tem.
- [x] Driver `USchemaComparer`: `start_comparison` (os 5 passos na ordem do Java, nenhum interrompendo o seguinte), `_compare_entities` (busca exata → fallback fuzzy → `root` não-fatal), `_compare_relationships` (sem fuzzy) e a fachada `compare`.
- [x] **Relatório de divergências por categoria** — todas as categorias populadas, com mensagem identificando os dois lados. `DivergenceCategory.FEATURE` ficou **sem emissor** (a granularidade do oráculo para na variação): reservada, e a remover se as Fases 1–3 não a usarem.
- [x] Testar o harness contra ele mesmo (A == A → equivalente) e contra um XMI deliberadamente alterado (deve apontar a categoria certa). → 2 testes A==A (northwind + movies) e 9 mutações parametrizadas, uma por categoria/fatalidade emitida.
- [x] **Conferência contra os JUnit do original** (`CompareDataTypeTest`, `ComparePropertyTest`, `CompareUSchemaTest`, `ModelIOTest`) — não portados por cima (já cobertos), mas com as asserções conferidas uma a uma. **Achou 4 lacunas reais do porte**, todas o mesmo esquecimento: o original guarda "tipo ausente dos dois lados" em **cada contêiner** (`ComparePList`, `ComparePSet`, `ComparePMap` ×2, `ComparePrimitiveType`) antes de delegar ao `CompareDataType`; portamos essa guarda só no `compare_attribute`. Três delas causavam `AttributeError` onde o Java devolve veredito. Ver `tests/regression/INVENTARIO.md`.

> **Política de estritância — "fiel + reporte extra".** O `startComparison` do Java é `void`: só acumula `hitLog`/`warningLog`. Logo `equivalent` := `warningLog` vazio, e **fatal = tudo que iria para o `warningLog`**. Ficam **não-fatais** as categorias que o Java não registra (`COUNT`, `ROOT`), as que ele registra como `hit` (fallback fuzzy de entidade) e as variações órfãs (C7). Assim o veredito nunca é mais rígido nem mais frouxo que o oráculo, e o relatório é mais informativo que o dele.

**Deve coincidir:** conjunto de `EntityType` (nomes pós-Inflector) + flag `root`; conjunto de `RelationshipType` + propriedades; por entidade, o conjunto de `StructuralVariation`; por variação, `Attribute`/`Aggregate`/`Reference` (tipo, cardinalidade, `refsTo`, `opposite`, `optional`) e `count`.
**Ignora:** `xmi:id`, ordem de serialização, formatação.
**Saída:** `src/uschema/validation/equivalence.py`, reutilizável nas Fases 1, 2 e 3.

---

## 0.4 — Estratégia de validação + suíte JUnit existente

> Quatro camadas, da mais barata/localizante para a mais ampla: (1) regressão portada → localiza o erro no módulo; (2) golden-master de dataset → ponta a ponta sem Docker; (3) oráculo Docker → só para datasets sem gabarito; (4) validação contra o banco → checagem independente do código.

- [x] Inventariar os JUnit do repo (`*/test/regression`, `*/test`, `documents/.../examples/tests`) e seus dados (`testSources/*.json`). → **`tests/regression/INVENTARIO.md`**: 37 `*Test.java`, ~2.500 linhas, classificados por bloco (regressão pura · presa a Mongo · golden-master · código morto).
- [x] Mapear os golden-master de dataset para a **Fase 3**. → bloco C do inventário: `UserProfileTest`, `FacebookTest`, `CompaniesTest`, `TypeAndRefTest`, `MapReduceTimestampTest` (todos exigem banco → `@pytest.mark.integration`).

**Saída:** inventário e mapa prontos — `tests/regression/INVENTARIO.md`.

> **O porte dos testes de regressão não é tarefa desta fase.** Eles são o
> **critério de aceite módulo a módulo da Fase 1** (e da 2.1, no caso dos dois do
> Mongo): cada um se escreve *junto* com o módulo que valida, test-alongside. Não
> há como portar o `CountTimestampTest` com o `SchemaInference` ainda em
> `NotImplementedError`. A ordem de ataque está no inventário. Exceção:
> **`InflectorTest`** não depende da inferência nem de banco — fecha junto com a
> **0.6**, e está listado lá.

> ⚠️ **Dois achados do inventário contrariam a suposição do roadmap** (detalhe em `INVENTARIO.md`):
>
> 1. **Metade dos "testes de regressão" exige um MongoDB de pé.** `CountTimestampTest`, `ObjectIdTest`, `TypesTest` e `SimplifyAggrTest` injetam o JSON no banco e rodam o **map-reduce no Mongo** antes de inferir. Não são a camada barata que o roadmap supõe — são integração disfarçada.
> 2. **Dá para portá-los sem banco, cortando na tripla.** A saída do map-reduce (`{schema, count, firstTimestamp, lastTimestamp}`) **é** o contrato de `extractors/triple.py`. Congelada como fixture (gerada uma vez pelo oráculo da 0.5), a inferência é testada em unidade. É o que os testes puros do `doc2uschema` já fazem — o `OptionalTest` traz esse JSON escrito à mão dentro da classe.
>
> Também: os 17 arquivos de `documents/.../examples/tests/` **não são testes** (16 têm corpo vazio, o 17º é um *runner* sem asserção), e o `automated/AutoTest1` só afirma `assertEquals(true, true)`. Não portar.

> ⚠️ **Testes que codificam o bug.** Onde você corrigiu um bug (#6/#7/#8), porte a *estrutura* do teste mas afirme o valor **corrigido**. Na prática, os testes de regressão minúsculos em geral nem disparam o #8 (só aparece com array de tamanho variável) — a maioria porta limpa; só os das áreas de bug pedem esse ajuste.

---

## 0.5 — Oráculo Java em Docker  *(gerador de gabarito + baseline — opcional)*

> Papel reduzido: (a) rodar a suíte JUnit e obter o *baseline verde*; (b) gerar o XMI-gabarito só para datasets sem golden-master (Sakila, variações de escala). **Não entra na entrega** (a ferramenta portada é Python puro); agrega reprodutibilidade, não funcionalidade.

- [x] Escrever o `Dockerfile` (base JDK 8 + Maven + build único — mongo-spark 3.0.1/Scala 2.12, neo4j-spark 2.4.5-M2/Spark 3.0.1/Scala 2.12 — + `entrypoint.sh` + patches `#1`/`#4`/`#5`/`#6`/`#7` verificados byte a byte). `#2`/`#3` satisfeitos estruturalmente (não precisam de `.patch` nesta build); `#8` deliberadamente fora — ver `oracle/README.md`.
- [x] Unificar os dois builds Maven separados (Mongo migrado de Spark 2.4.1/Scala 2.11 pra 3.0.1/Scala 2.12) num só (`uschema-build/runner`), testado sem colisão de dependências transitivas e com saída idêntica aos builds antigos via `compare()`; contrato simplificado de `KIND`/`DB_NAME` (env vars) pra `--db`/`--kind` (CLI args), batendo com o desenho original do plano. Detalhe em `oracle/docker_explain.md`.
- [x] `docker build` real testado (2026-07-15, Docker Desktop/Windows) — builda a imagem `extrator-uschema` do zero.
- [x] `docker run` real testado contra MongoDB/Northwind (17 coleções) — gerou `out/northwind.xmi` com sucesso, depois de corrigir `dependency:go-offline` incompleto, os crashes reais de `#6`/`#7` (não estavam previstos como patch na primeira versão) e a pasta `outputs/` faltando no `entrypoint.sh`.
- [x] **Rodar a suíte JUnit** dentro da imagem — **65/76 passam.** Os 11 que falham têm causa raiz identificada lendo o código-fonte real do commit pinado (não suposição), e nenhum aponta pra um problema do empacotamento: `OptionalTest` (helper de teste com o mesmo bug do patch #1, nunca corrigido no original), `ModelIOTest` (2, dependência de um projeto irmão nunca clonado), `CompareDataTypeTest`/`ComparePropertyTest` (9, teste e `USchemaFactory` já inconsistentes entre si no repo original — o teste passa `null` esperando sucesso, a fábrica valida e lança `IllegalArgumentException`). Detalhe completo em `oracle/docker_explain.md`.
- [x] Validar `out/northwind.xmi` contra `resources/mongodb/model_northwind.xmi` via `compare()` (Fase 0.3): `equivalent: True`, zero divergências fatais; as 8 não-fatais (todas em `Orders`/`Purchase_orders`) batem com a assinatura do bug #8, deliberadamente sem patch no oráculo.
- [x] Testar `docker run` no caminho Neo4j (`--kind neo4j`) de ponta a ponta — grafo mínimo (`User`/`Movie`, `WATCHED`/`FAVORITE`) via `cypher-shell`, `neo4j.xmi` gerado com sucesso (sem gabarito comparável, só confirmação de que o caminho roda).
- [x] Versionar `Dockerfile` + `entrypoint.sh` + `patches/` (artefato de reprodutibilidade citável no TCC).

> **Contrato real** (o `main` Java não aceita `--db`/`--kind` diretamente, o `entrypoint.sh` faz a ponte):
> `docker run --network=host -v $PWD/out:/output [-e MONGO_URL=... -e MONGO_COLLECTIONS=...] extrator-uschema --db <nome> --kind <mongodb|neo4j>` → grava `<nome>.xmi` em `/output`. Memória ≥ ~5–6 GB. `MONGO_URL`/`MONGO_COLLECTIONS` só no caso Mongo, continuam em variável de ambiente. Detalhe completo em `oracle/README.md`.

---

## 0.6 — Inflector

> A capitalização/pluralização dos nomes de entidade precisa **casar** com o Java — senão os nomes de `EntityType` divergem e o harness acusa divergência em toda entidade.

- [x] Ler `Inflector.java` e listar as regras efetivamente usadas. **É o Inflector do ModeShape vendorizado** (por sua vez inspirado no do Rails), em **duas cópias idênticas** (`doc2uschema/util/inflector` e `mongodb2uschema.spark/inflector` — diferem só no `package`): um porte serve às duas. A classe tem 10 métodos públicos, mas o pipeline só usa **três**: `capitalize` (nome da entidade raiz — `SchemaInference:183,188`), `singularize` (nome da entidade agregada — `SchemaInference:233`, `USchemaModelBuilder:194`, `ModelDirector:84,102`) e `pluralize` (`DefaultReferenceMatcherCreator:26`). `camelCase`/`underscore`/`humanize`/`titleCase`/`ordinalize` são **código morto** no pipeline — portados mesmo assim, porque são o que o `InflectorTest` cobre.
- [x] Decidir entre uma lib Python (`inflection`/`inflect`) e uma reimplementação fiel. **Decidido: reimplementação fiel.** As regras do Java são uma lista **ordenada** de ~50 regexes com semântica de inserção-na-frente (`LinkedList.addFirst`), e a saída depende dessa ordem: `pluralize("human")` → `"humen"` (a regra irregular `(m)an$` casa no fim de qualquer palavra). Nenhuma lib reproduz isso — o `inflection` é um porte do Rails **moderno**, não do snapshot que o ModeShape copiou. Usar lib trocaria nomes de `EntityType` e quebraria a equivalência. → **`inflection` removido** das dependências de runtime, do override do `mypy` e das *Key dependencies* do `CLAUDE.md` (que agora traz a nota "o Inflector é reimplementação, não lib", para ninguém reintroduzi-la).
- [x] **Porte do módulo** (`src/uschema/naming/inflector.py`) — **completo, 24 de 24 passos.**
  - [x] **Camada de regex** (infra): `_to_python_replacement` (traduz `$1` do Java → `\g<1>` do `re`, escapando a barra literal **antes** de introduzir os retrovisores), `_Rule` (compila com `IGNORECASE | re.ASCII`; `search` + `sub` = o `find()` + `replaceAll()` do Java) e `replace_all_with_uppercase`. Conferida contra as regras reais: `octopi`, `wives`, `elves`, `women`, `indices`; e contra o `shouldReplaceAllWithUppercase` do JUnit (`hEllO`, `hLlo`).
  - [x] **Tabela de regras** (`_initialize`) transcrita literalmente do Java: 22 plurais + 29 singulares + 6 irregulares + 8 incontáveis → **28 regras de plural, 35 de singular** depois da expansão dos irregulares.
  - [x] **Registro de regras**: `__init__` (dois construtores do Java fundidos num parâmetro opcional; cópia **rasa** no ramo do `clone`), `add_pluralize`/`add_singularize` (**`insert(0, …)`** — o `addFirst` do Java: a ordem de consulta é a **inversa** da de registro, e é ela que faz a irregular vencer a genérica `$ → s`), `add_irregular`, `add_uncountable`, `is_uncountable`.
  - [x] **`pluralize`** — validado contra os 83 pares do `InflectorTest`: **83/83**, mais a idempotência (pluralizar um plural não o altera).
  - [x] **`singularize`** (o mesmo laço, sobre `_singulars`, sem a sobrecarga de `count`). A guarda `vazio or is_uncountable` **antes** do laço é o que faz `sheep`/`series`/`news` sobreviverem à regra genérica `s$ → ""`.
  - [x] **`capitalize`** — **a terceira das três usadas pelo pipeline**. É o `str.capitalize()` do Python (primeira maiúscula, **resto minúsculo**), depois do `strip()` — e **não** o `str.title()`, que subiria a letra após cada `_` e renomearia entidade (`Inventory_Transaction_Types`). O ramo de 1 caractere do Java (linha 393) coincide e ficou implícito.
  - [x] Código morto no pipeline, portado só porque o `InflectorTest` cobre: `camel_case` (+ as duas fachadas), `underscore`, `humanize`, `title_case`, `ordinalize`. No `camel_case`, o ramo *lower* monta a saída com a primeira letra minúscula **+ o resto vindo do ramo Upper** — é o Upper que já comeu os `_` e subiu as iniciais internas.
  - [x] Utilidades: `clone`, property `uncountables` (devolve o conjunto **vivo**), `clear` (esvazia **no lugar**, para honrar esse contrato), `get_instance` (singleton de módulo, criado no import).
- [x] **Decisões de fidelidade** tomadas ao portar (registradas na seção "Fidelidade"/"Desvios" do módulo):
  - [x] **`re.ASCII` no módulo inteiro** (constante `_JAVA_FLAGS`). O `Pattern` do Java, sem `UNICODE_CHARACTER_CLASS`/`UNICODE_CASE`, é uma engine **ASCII**: `\d` é `[0-9]`, `\b` usa `[a-zA-Z_0-9]`, e `CASE_INSENSITIVE` só dobra caixa ASCII. O `re` do Python é Unicode por padrão. Verificado empiricamente: nas ~50 regras a diferença só aparece no `ſ` (irrelevante), mas em `underscore` (`\d`) e `title_case` (`\b`) ela é trivial de disparar com acento — `title_case("ação")` dá `Ação` no Python e **`AçãO`** no Java. Sem a flag, o teste portado passaria verde afirmando um valor que o oráculo nunca produz.
  - [x] **`ordinalize` replica o bug `I1`** (`bugs_originais.md`): o guarda de 11–13 testa o número, não o resto → `ordinalize(111) == "111st"`. Teste fixa o valor **errado**, citando a entrada. O `% 10` sai de `math.fmod`, não do `%` do Python: em negativo o resto do Java tem o sinal do dividendo (`-9`), o do Python, o do divisor (`1`).
  - [x] **`title_case(None)` devolve `None`, não replica o NPE (`I2`).** Único desvio deliberado do porte: a exceção do Java é uma linha faltando, não semântica. Justificado em `bugs_originais.md`.
  - [x] **`humanize` não trata hífen — portamos o código, não o javadoc (`I3`, achado novo).** O javadoc do `titleCase` promete `"x-men: the last stand"` → `"X Men: …"`, mas o exemplo veio do `titleize` do Rails (que chama `underscore` antes) e o método ModeShape não faz esse passo: o Java real devolve `"X-Men: …"`. Não afeta comportamento (o `titleCase` é código morto e o `InflectorTest` não cobre hífen), mas é armadilha: "consertar" o `humanize` para tratar `-` mudaria a nomeação de entidade (`order-details` → `Order details`).
- [x] **Portar o `InflectorTest`** (394 linhas, `doc2uschema/test/regression/`) → **`tests/unit/test_inflector.py`, 205 casos, 205 verdes.** Cada bloco `@Test` do JUnit virou um `@pytest.mark.parametrize` (uma falha aponta o par exato, em vez de derrubar o bloco na primeira asserção). Os ~90 pares passam pelas **4** asserções do helper `singularToPlural` (ida, volta e idempotência dos dois lados) e os 12 casos de camelCase pelo **round-trip** `underscore(camelizado) == original` — juntos, provam que a ordem das ~50 regras foi transcrita certo: bastaria uma regra registrada fora de ordem para algum dos ~360 asserts cair. Mais 2 testes que fixam bug de propósito (`ordinalize(111) == "111st"`, `title_case(None) is None`) e 1 do singleton.
- [x] Teste: aplicar a normalização aos nomes do Northwind e comparar com os nomes no XMI-oráculo. → **`tests/unit/test_inflector_northwind.py`, 5 verdes.** As 3 regras de nomeação do pipeline, aplicadas às **17 coleções** do dump, reproduzem **exatamente** as 19 `EntityType` de `resources/mongodb/model_northwind.xmi`: as 17 `capitalize`das (`orders` → `Orders`; `inventory_transaction_types` → `Inventory_transaction_types` — `capitalize` **não** faz camelCase) + `Detail` (`capitalize(singularize("details"))`) + `_id` (`capitalize("_id")`, ponto fixo). A lista de coleções é transcrita do dataset, não derivada do XMI (seria circular). Inclui uma guarda de regressão que falha se alguém trocar `capitalize` por `title_case`.

**Saída:** `src/uschema/naming/inflector.py` (porte completo, sem `NotImplementedError`) + 210 testes verdes (`test_inflector.py` · `test_inflector_northwind.py`).

---

## ✅ Gate de aceite da Fase 0

- [x] Round-trip do `model_northwind.xmi` fecha (recarrega estruturalmente idêntico).
- [x] Harness de equivalência funcionando (acerta A==A e detecta divergência injetada), com a semântica espelhada do `USchemaCompareMain`.
- [x] Suíte JUnit inventariada — regressão mapeada para a Fase 1, golden-master para a Fase 3. → `tests/regression/INVENTARIO.md`
- [x] Imagem Docker roda o baseline JUnit e regenera os XMIs-gabarito de forma reproduzível.

**Entregáveis:** `src/uschema/metamodel/` (metamodelo + round-trip XMI) · `src/uschema/validation/equivalence.py` (harness) · inventário/mapa dos testes JUnit a portar (`tests/regression/`) · `oracle/Dockerfile` + `oracle/patches/` · `src/uschema/naming/` (Inflector).
