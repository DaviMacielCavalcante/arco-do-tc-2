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
