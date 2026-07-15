# Declaração de Uso de Inteligência Artificial

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) para Python — MongoDB e Neo4j
**Repositório:** `arco-do-tc-2`
**Autores:** Davi Cavalcante · João — CESUPA
**Última atualização:** 2026-07-01

Este documento declara, de forma transparente, o uso de ferramentas de
Inteligência Artificial generativa no desenvolvimento deste Trabalho de
Conclusão de Curso, em atendimento às diretrizes de integridade acadêmica.

---

## 1. Ferramenta e modelo utilizados

| Item | Descrição |
|---|---|
| **Ferramenta** | Claude Code (CLI/extensão de IDE da Anthropic) |
| **Modelo** | Claude Opus 4.8 (`claude-opus-4-8`) |
| **Fornecedor** | Anthropic |
| **Modo de acesso** | Assistente de programação interativo, sob supervisão dos autores |

---

## 2. Como a IA foi utilizada

O uso foi **assistivo e supervisionado**, com os autores mantendo o controle
das decisões técnicas e da autoria do código de implementação. As atividades em
que a IA foi empregada:

### 2.1 Atividades realizadas com apoio da IA

- **Arquitetura e scaffold do repositório Python.** Estruturação inicial do
  projeto com `uv`: layout `src/`, criação do esqueleto de pacotes
  (`metamodel`, `naming`, `validation`, `intermediate`, `inference`,
  `extractors`) mapeado às fases do roadmap, e configuração de ferramental
  (`ruff`, `mypy`, `pytest`) no `pyproject.toml`.
- **Documentação de apoio.** Redação de arquivos `README.md` por diretório,
  do `CLAUDE.md` (guia de convenções do repositório) e de docstrings de
  marcação de pacote.
- **Decisões técnicas discutidas com os autores.** Por exemplo, o *pin* da
  versão do Python em 3.12 devido à incompatibilidade do PySpark com a 3.14, e
  a escolha do layout de pacote com `src/`.
- **Organização de tarefas.** Apoio na estruturação e atualização das listas de
  tarefas (`todolist_fase0.md`).
- **Oráculo Java em Docker (`oracle/`, Fase 0.5).** Escrita do `Dockerfile`,
  `entrypoint.sh` e dos `.patch` (`#1`, `#4`, `#5`, `#6`, `#7` — numeração de
  `bugs_originais.md`), com pedido e revisão explícitos dos autores, e com
  correção de um build real (`docker build`/`docker run` testados de
  verdade contra o dataset Northwind, não só simulados — o que revelou dois
  crashes reais, `#6` e `#7`, corrigidos nessa ordem). Diferente do código de
  implementação Python (§2.2), essa é infraestrutura de *build*/
  empacotamento do código Java **de terceiros** (`modelum/uschema*`), não
  lógica do porte em si — `#1`, `#4`, `#5` corrigem incompatibilidades de
  build (Guice, `Path.of`/JDK 8, hardcode de máquina); `#6` e `#7` corrigem
  bugs de corretude que **derrubam o job inteiro** (`_id` não-`ObjectId`;
  array vazio indexado antes do teste de tamanho), aplicados no oráculo
  porque sem eles não há XMI algum pra comparar — decisão já prevista em
  `bugs_originais.md`. O bug `#8`, que não derruba o job (só distorce a
  contagem), continua corrigido **apenas** no porte Python, por decisão
  deliberada (ver `oracle/README.md`). Também configurada e testada de
  verdade: a suíte JUnit original dentro da imagem (`add-test-source` +
  dependências de teste no `pom.xml` de `oracle/uschema-build/runner`;
  65/76 passam, causa raiz dos 11 restantes identificada lendo o
  código-fonte real — nenhum é bug do empacotamento, ver
  `oracle/docker_explain.md`) e o caminho Neo4j de ponta a ponta. Também
  unificados os dois builds Maven separados (Mongo/Neo4j) num só, depois de
  testar que migrar o Mongo de Spark 2.4.1/Scala 2.11 pra 3.0.1/Scala 2.12
  (a versão já usada pelo Neo4j) produz saída idêntica (`compare()`, Fase
  0.3) e não colide com as dependências transitivas do Neo4j; e
  simplificado o contrato do `entrypoint.sh` de variáveis de ambiente
  (`KIND`/`DB_NAME`) pra argumentos de linha de comando (`--db`/`--kind`),
  batendo com o desenho original do plano (`fase0_fundacao_oraculo.md`).
  Mudanças de infraestrutura de build, pedidas e revisadas explicitamente
  pelos autores, com backup da versão anterior guardado por eles fora deste
  repo antes da alteração.

### 2.2 Delimitação — o que NÃO foi gerado por IA

Por decisão dos autores, **o código de implementação (a lógica dos módulos) é
escrito pelos próprios autores**, como parte do processo de aprendizado e da
contribuição do trabalho. A IA **não** produziu:

- A implementação do núcleo de inferência (`SchemaInference`, estratégias,
  `USchemaModelBuilder`).
- A implementação dos extratores PySpark (MongoDB e Neo4j).
- A implementação do harness de equivalência, do Inflector ou da camada de
  metamodelo.
- A lógica de qualquer teste de regressão portado.

Stubs de código que chegaram a ser gerados durante a exploração da arquitetura
foram **removidos** a pedido dos autores, permanecendo apenas o esqueleto de
diretórios e a documentação.

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
