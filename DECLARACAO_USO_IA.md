# Declaração de Uso de Inteligência Artificial

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) para Python — MongoDB e Neo4j
**Repositório:** `arco-do-tc-2`
**Autores:** Davi Cavalcante · João Miguel — CESUPA
**Última atualização:** 2026-08-20

Este documento declara, de forma transparente, o uso de ferramentas de
Inteligência Artificial generativa no desenvolvimento deste Trabalho de
Conclusão de Curso, em atendimento às diretrizes de integridade acadêmica.

---

## 1. Ferramenta e modelos utilizados

| Item | Descrição |
|---|---|
| **Ferramenta** | Claude Code (CLI/extensão de IDE da Anthropic) |
| **Modelos** | Claude Opus 4.8 (`claude-opus-4-8`) e Claude Opus 5 (`claude-opus-5`), usados ao longo do desenvolvimento |
| **Fornecedor** | Anthropic |
| **Modo de acesso** | Assistente de programação interativo, sob supervisão dos autores |

---

## 2. Como a IA foi utilizada

O uso foi **assistivo e supervisionado**, com os autores mantendo o controle
das decisões técnicas e da autoria do código de implementação. As atividades em
que a IA foi empregada:

### 2.1 Atividades realizadas com apoio da IA

- **Arquitetura e estrutura inicial do repositório Python.** Montagem do projeto
  com `uv`: layout `src/`, criação dos pacotes vazios (`metamodel`, `naming`,
  `validation`, `intermediate`, `inference`, `extractors`) mapeados às fases do
  roadmap, e configuração das ferramentas de qualidade (`ruff`, `mypy`,
  `pytest`) no `pyproject.toml`.
- **Documentação de apoio.** Redação dos arquivos `README.md` por diretório, do
  `CLAUDE.md` (guia de convenções do repositório) e das docstrings de abertura
  dos `__init__.py`.
- **Documentos de método e de registro de achados.** Redação e revisão, sob
  direção dos autores, dos documentos de planejamento e análise da raiz do
  repositório: `roadmap_portabilidade.md` e os guias `fase0`…`fase3`, as listas
  `todolist_fase0`…`todolist_fase3`, o `dicionario_de_dados.md` (esquema das
  tabelas de evidência da Fase 3) e o `bugs_originais.md` (catálogo dos defeitos
  herdados do código Java original, com evidência e citação de linha). O
  levantamento dos defeitos foi feito lendo o código-fonte Java, a pedido dos
  autores, e cada achado foi conferido por eles.
- **Decisões técnicas discutidas com os autores.** Por exemplo, o *pin* da
  versão do Python em 3.12 devido à incompatibilidade do PySpark com a 3.14, e
  a escolha do layout de pacote com `src/`.
- **Organização de tarefas.** Apoio na estruturação e atualização das listas de
  tarefas de todas as fases.
- **Oráculo Java em Docker (`oracle/`, Fase 0.5).** Escrita do `Dockerfile`,
  `entrypoint.sh` e dos `.patch` (`#1`, `#4`, `#5`, `#6`, `#7` — numeração de
  `bugs_originais.md`), com pedido e revisão explícitos dos autores, e com
  correção de uma compilação real (`docker build`/`docker run` executados de
  verdade contra o dataset Northwind, não apenas simulados — o que revelou
  dois defeitos que abortavam a execução, `#6` e `#7`, corrigidos nessa
  ordem). Diferente do código de implementação Python (§2.2), essa é
  infraestrutura de compilação e empacotamento do código Java **de terceiros**
  (`modelum/uschema*`), não lógica do porte em si — `#1`, `#4` e `#5` corrigem
  incompatibilidades de compilação (Guice, `Path.of` sob JDK 8, caminho Hadoop
  fixo no código); `#6` e `#7` corrigem defeitos de equivalência que
  **abortam a execução inteira** (`_id` que não é `ObjectId`; array vazio
  indexado antes da verificação de tamanho), aplicados no oráculo porque sem
  eles não se obtém XMI algum para comparar — decisão já prevista em
  `bugs_originais.md`. O bug `#8`, que não aborta a execução (apenas distorce
  a contagem), continua corrigido **apenas** no porte Python, por decisão
  deliberada (ver `oracle/README.md`). Também configurada e testada de
  verdade: a suíte JUnit original dentro da imagem (`add-test-source` +
  dependências de teste no `pom.xml` de `oracle/uschema-build/runner`;
  65/76 passam, e a causa dos 11 restantes foi identificada lendo o
  código-fonte real — nenhum decorre do empacotamento, ver
  `oracle/docker_explain.md`) e o caminho Neo4j de ponta a ponta. Também
  unificadas as duas compilações Maven separadas (Mongo/Neo4j) numa só,
  depois de verificar que migrar o Mongo de Spark 2.4.1/Scala 2.11 para
  3.0.1/Scala 2.12 (a versão já usada pelo Neo4j) produz saída idêntica
  (`compare()`, Fase 0.3) e não conflita com as dependências transitivas do
  Neo4j; e simplificada a interface do `entrypoint.sh`, de variáveis de
  ambiente (`KIND`/`DB_NAME`) para argumentos de linha de comando
  (`--db`/`--kind`), como o plano original previa
  (`fase0_fundacao_oraculo.md`). São mudanças de infraestrutura de
  compilação, pedidas e revisadas explicitamente pelos autores, com cópia da
  versão anterior guardada por eles fora deste repositório antes da
  alteração.
- **Revisão de código.** Análise das revisões automatizadas do repositório
  (CodeRabbit) para separar achados procedentes de improcedentes, verificando
  cada um contra o código, e aplicação das correções aceitas pelos autores.

### 2.2 Delimitação — o que NÃO foi gerado por IA

Por decisão dos autores, **o código de implementação (a lógica dos módulos) é
escrito pelos próprios autores**, como parte do processo de aprendizado e da
contribuição do trabalho. A IA **não** produziu:

- A implementação do núcleo de inferência (`SchemaInference`, as estratégias, o
  `USchemaModelBuilder`, o `USchemaToDocumentDb`) nem a fachada `BuildUSchema`.
- A implementação dos extratores por driver nativo — `extractors/mongo.py`,
  `extractors/neo4j.py`, `extractors/neo4j_model.py` e `extractors/triple.py`,
  o formato de tripla em que extração e inferência se encontram.
- A implementação do harness de equivalência, do Inflector ou da camada de
  metamodelo.
- A lógica de qualquer teste de regressão portado.

Os esqueletos de código (*stubs*) que chegaram a ser gerados durante a
exploração da arquitetura foram **removidos** a pedido dos autores, restando
apenas a estrutura de diretórios e a documentação.

---

## 3. Revisão humana

Todo o conteúdo produzido com apoio da IA foi **revisado pelos autores** antes de
ser incorporado ao repositório. Os autores são responsáveis pela correção,
adequação e integridade de todo o material entregue, gerado com ou sem apoio de
IA.

---

## 4. Registro de responsabilidade

Os autores declaram que o uso de IA descrito acima foi de natureza **assistiva**
e que a concepção intelectual, as decisões de projeto e a implementação central
do trabalho são de sua autoria.
