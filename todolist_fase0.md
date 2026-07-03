# TO-DO — Fase 0: Fundação + oráculo

**Projeto:** Porte fiel e completo do U-Schema (Java/Spark/EMF) → Python — MongoDB e Neo4j
**Autores:** Davi `[D]` · João `[J]` — CESUPA
**Base:** `fase0_fundacao_oraculo.md` · **Validação:** `roteiro_experimental.md` · **Técnica:** `analise_ferramenta_uschema.md`
**Prioridade:** imediata — pré-requisito de todas as fases seguintes.

> **Ideia central.** A correção do porte não vem de uma fonte só: vem em **camadas** (0.4). A camada mais forte e mais barata — os testes de regressão JUnit portados — localiza o erro no módulo **sem depender do Docker**. O Docker fica reduzido a gerador de gabarito para datasets sem golden-master pronto.

---

## 0.0 — Fundação do repositório Python  ✅ *(scaffold pronto)*

> Estrutura montada com `uv`; **sem implementação** (o código dos módulos é dos autores). Serve de esqueleto para as tarefas 0.1–0.6.

- [x] `[D+J]` Projeto `uv` inicializado (layout `src/`, pacote `uschema`), Python **pinado em 3.12** (o PySpark ainda não suporta 3.14).
- [x] `[D+J]` Dependências de runtime declaradas: `pyecore`, `pyspark`, `pymongo`, `neo4j`, `inflection`, `pydantic`, `loguru`; dev: `ruff`, `mypy`, `pytest`, `pytest-cov` (lockfile resolvido).
- [x] `[D+J]` Ferramental configurado no `pyproject.toml`: `ruff` (docstrings NumPy, linha 100), `mypy` estrito, `pytest`.
- [x] `[D+J]` Esqueleto de pacotes criado, um por fase: `metamodel/` (0.1–0.2) · `naming/` (0.6) · `validation/` (0.3) · `intermediate/` (1.1) · `inference/` (1.2–1.4) · `extractors/` (2).
- [x] `[D+J]` Diretórios de apoio: `resources/` (`.ecore` + XMIs), `oracle/` (Dockerfile + `patches/`), `scripts/` (baterias), `tests/` (`unit`/`regression`/`datasets`), cada um com `README.md` de escopo; `CLAUDE.md` do repositório.
- [ ] `[D+J]` Copiar para `resources/` os artefatos de referência do repo Java original: `uschema.ecore`, `model_northwind.xmi`, `model.xmi`, `movies_min.xmi`.

**Saída:** repositório com esqueleto, ferramental e dependências prontos — `uv sync` resolve, `ruff`/`mypy`/`pytest` rodam limpos no esqueleto vazio.

---

## 0.1 — PyEcore sobre o `uschema.ecore`

> Metamodelo favorável: 19 EClasses em 98 linhas, sem OCL e sem EAnnotations (puramente estrutural).

- [ ] `[D]` Instalar PyEcore (`pip install pyecore`); carregar `uschema.ecore` via `ResourceSet`/`metamodel_resource`.
- [ ] `[D]` Confirmar acesso reflexivo às 19 EClasses; instanciar manualmente um `USchema` mínimo (1 `EntityType` + 1 `StructuralVariation` + 1 `Attribute`) e serializar em XMI.
- [ ] `[D]` Decidir **API reflexiva** (manipular `EObject` dinamicamente) vs. **`pyecoregen`** (gerar classes do `.ecore`). Recomendação inicial: reflexivo, para não acoplar a uma etapa de codegen; reavaliar se a ergonomia incomodar.
- [ ] `[D]` Tratar o gap conhecido: PyEcore não suporta `genmodel` multi-arquivo — se o `.ecore` referenciar outros pacotes, achatar para um único EPackage no fork.

**Saída:** módulo Python em `src/uschema/metamodel/` que cria, lê e serializa modelos U-Schema em XMI.

---

## 0.2 — Round-trip de XMI

- [ ] `[D]` Ler `model_northwind.xmi` (19 `EntityType`, incluindo o agregado `Detail`) com PyEcore.
- [ ] `[D]` Reserializar e validar que o modelo recarregado é **estruturalmente idêntico** ao original (não precisa ser byte a byte — EMF tem convenções próprias de `xmi:id`/ordenação).
- [ ] `[D]` Repetir com `model.xmi` (mínimo MongoDB) e `movies_min.xmi` (mínimo Neo4j, com `RelationshipType`).

---

## 0.3 — Harness de equivalência estrutural  *(instrumento central de validação)*

> **Não inventar do zero — espelhar o `USchemaCompareMain`** (`es.um.uschema.*.validation`), que já existe no Java: `startComparison(USchema s1, USchema s2)` compara nome → contagem de `EntityType`/`RelationshipType` → variações (via `CompareSchemaType`/`CompareStructuralVariation`), com log de *hits*/*warnings* e normalização de caixa. Reproduzir a mesma noção de equivalência evita ficar mais rígido ou mais frouxo que o original.

- [ ] `[D+J]` Ler `USchemaCompareMain` (+ `CompareSchemaType` / `CompareStructuralVariation`) e replicar sua semântica de comparação em Python.
- [ ] `[D+J]` Implementar a **assinatura canônica** de uma variação (conjunto ordenado de `(nome, tipo, papel)` das features).
- [ ] `[D+J]` Implementar a comparação e o **relatório de divergências por categoria** — `{entidade, variacao, feature, contagem}` — essencial para diagnosticar onde o porte divergiu.
- [ ] `[D+J]` Testar o harness contra ele mesmo (A == A → equivalente) e contra um XMI deliberadamente alterado (deve apontar a categoria certa).

**Deve coincidir:** conjunto de `EntityType` (nomes pós-Inflector) + flag `root`; conjunto de `RelationshipType` + propriedades; por entidade, o conjunto de `StructuralVariation`; por variação, `Attribute`/`Aggregate`/`Reference` (tipo, cardinalidade, `refsTo`, `opposite`, `optional`) e `count`.
**Ignora:** `xmi:id`, ordem de serialização, formatação.
**Saída:** `src/uschema/validation/equivalence.py`, reutilizável nas Fases 1, 2 e 3.

---

## 0.4 — Estratégia de validação + suíte JUnit existente

> Quatro camadas, da mais barata/localizante para a mais ampla: (1) regressão portada → localiza o erro no módulo; (2) golden-master de dataset → ponta a ponta sem Docker; (3) oráculo Docker → só para datasets sem gabarito; (4) validação contra o banco → checagem independente do código.

- [ ] `[D]` Inventariar os JUnit do repo (`*/test/regression`, `*/test`, `documents/.../examples/tests`) e seus dados (`testSources/*.json`).
- [ ] `[D]` **Portar primeiro** os testes de regressão (critério de aceite módulo a módulo da Fase 1): `CountTimestampTest` (área do bug #8), `ObjectIdTest` (bug #6, dado em `testSources/ObjectIds.json`), `InflectorTest`, `OptionalTest`, `TypesTest`, `SimplifyAggrTest`, `RelationshipTypeToEntityTypeTest`, `RemovePMapTest`, e no Mongo `SimplificationTest`/`PairOperationsTest`.
- [ ] `[D+J]` Mapear os golden-master de dataset (`UserProfileTest`, `EveryPoliticianTest`, `CompaniesTest`, `FacebookTest`, `StackOverflowTest`…) para a **Fase 3**.

> ⚠️ **Testes que codificam o bug.** Onde você corrigiu um bug (#6/#7/#8), porte a *estrutura* do teste mas afirme o valor **corrigido**. Na prática, os testes de regressão minúsculos em geral nem disparam o #8 (só aparece com array de tamanho variável) — a maioria porta limpa; só os das áreas de bug pedem esse ajuste.

---

## 0.5 — Oráculo Java em Docker  *(gerador de gabarito + baseline — opcional)*

> Papel reduzido: (a) rodar a suíte JUnit e obter o *baseline verde*; (b) gerar o XMI-gabarito só para datasets sem golden-master (Sakila, variações de escala). **Não entra na entrega** (a ferramenta portada é Python puro); agrega reprodutibilidade, não funcionalidade.

- [ ] `[J]` Escrever o `Dockerfile` (base JDK 8 + Spark + conectores fixados: mongo-spark 3.0.1 / neo4j-spark 2.4.5-M2 + build da `uschema-inference` com os 8 `.patch` auditáveis).
- [ ] `[J]` **Rodar a suíte JUnit** dentro da imagem para o baseline verde e extrair dados/saídas de teste reaproveitáveis.
- [ ] `[J]` Validar que a imagem regenera `model_northwind.xmi` (e os XMIs de escala) **estruturalmente idênticos** aos já gerados.
- [ ] `[J]` Versionar `Dockerfile` + `patches/` (artefato de reprodutibilidade citável no TCC).

> **Contrato:** `docker run -v $PWD/out:/output extrator-uschema --db <nome> --kind <mongodb|neo4j>` → grava `model.xmi` em `/output`. Rede: `--network=host` (Linux); memória ≥ ~5–6 GB.

---

## 0.6 — Inflector

> A capitalização/pluralização dos nomes de entidade precisa **casar** com o Java — senão os nomes de `EntityType` divergem e o harness acusa divergência em toda entidade.

- [ ] `[D]` Ler `Inflector.java` e listar as regras efetivamente usadas (capitalize, singular/plural).
- [ ] `[D]` Decidir entre uma lib Python (`inflection`/`inflect`) e uma reimplementação fiel das regras específicas.
- [ ] `[D]` Teste: aplicar a normalização aos nomes do Northwind e comparar com os nomes no XMI-oráculo.

---

## ✅ Gate de aceite da Fase 0

- [ ] Round-trip do `model_northwind.xmi` fecha (recarrega estruturalmente idêntico).
- [ ] Harness de equivalência funcionando (acerta A==A e detecta divergência injetada), com a semântica espelhada do `USchemaCompareMain`.
- [ ] Suíte JUnit inventariada — regressão mapeada para a Fase 1, golden-master para a Fase 3.
- [ ] Imagem Docker roda o baseline JUnit e regenera os XMIs-gabarito de forma reproduzível.

**Entregáveis:** `src/uschema/metamodel/` (metamodelo + round-trip XMI) · `src/uschema/validation/equivalence.py` (harness) · inventário/mapa dos testes JUnit a portar (`tests/regression/`) · `oracle/Dockerfile` + `oracle/patches/` · `src/uschema/naming/` (Inflector).
