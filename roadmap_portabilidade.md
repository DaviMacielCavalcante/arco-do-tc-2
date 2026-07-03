# Roadmap de portabilidade — porte fiel e completo do U-Schema para Python

**Escopo deste documento:** *apenas* a portabilidade da ferramenta. A contribuição original (metacamada de acesso) é **trabalho futuro** e não entra no caminho crítico. Base técnica em `analise_ferramenta_uschema.md`.

> **Mudança de premissa (substitui a versão anterior).** O orientador definiu que **o foco do TCC é a portabilidade**, com a metacamada adiada. Isso inverte a lógica do roadmap anterior, que tratava o porte como infraestrutura e recomendava blackboxar o Java em Docker. Agora o **porte fiel e completo da inferência é a espinha do trabalho** — o Docker é rebaixado a andaime de desenvolvimento, e a metacamada sai para "trabalhos futuros".

---

## 1. Objetivo e bordas de escopo

**Objetivo:** reimplementar em Python, de forma **fiel e completa**, o pipeline de **extração + inferência + serialização** do U-Schema para os paradigmas **documento (MongoDB)** e **grafo (Neo4j)**.

Duas bordas, confirmadas com o orientador:

- **Bancos:** apenas **MongoDB + Neo4j**. Os outros quatro backends do repositório (`cassandra`, `hbase`, `redis`, `sql`) estão fora — não pertencem à pergunta de pesquisa (documento + grafo a partir do relacional).
- **Camadas:** o porte cobre o **pipeline que produz o modelo U-Schema/XMI**, não o ferramental Eclipse em volta dele. Ver §3 para o que isso inclui e exclui.

**Definição operacional de "fiel":** equivalência de **comportamento/estrutura**, não XMI idêntico byte a byte. O serializador do EMF tem convenções próprias de `xmi:id` e ordenação que o PyEcore não reproduz à risca; o modelo é o mesmo, mas os bytes diferem. Logo, o critério de aceite é **equivalência estrutural** (mesmas entidades, variações, atributos, agregados, referências e contagens), verificada contra o XMI gerado pela ferramenta Java patcheada (o **oráculo**).

---

## 2. Arquitetura-alvo

```
[MongoDB] ─┐                                    ┌─ PySpark: map(ArchetypeMapping) ─┐
           ├─ extrator PySpark ── triplas ──────┤                                  ├─→ doc2uschema (porte) ─→ PyEcore ─→ XMI
[Neo4j]  ──┘  {schema, count, timestamps}       └─ PySpark: map(IdArchetypeMapping)┘     (núcleo único)
```

Decisão central: **um único núcleo de inferência compartilhado** pelos dois paradigmas. No Java, cada extrator `.spark` traz um `ModelDirector` próprio (mais fino); o caminho canônico e rico é o `doc2uschema` (`SchemaInference` + `USchemaModelBuilder`). O porte adota o `doc2uschema` como alvo e faz os extratores apenas **alimentarem as triplas** — o que é mais limpo que o original (sem `ModelDirector` duplicado por banco) **sem violar a fidelidade de comportamento**.

---

## 3. O que entra, o que fica de fora

**Entra (precisa ser portado para "fiel e completo"):**
- Metamodelo via **PyEcore** carregando `uschema.ecore` (19 classes, puramente estrutural — substitui Factory/Package/Switch/AdapterFactory gerados pelo EMF).
- Modelos intermediários: `raw` (Composite: `SchemaComponent` e filhos) e `firsto` (`MultiValued`, `Ranged`, …).
- Núcleo `doc2uschema/process`: `SchemaInference`, `USchemaModelBuilder` e **todas** as estratégias (`AliasedAggregatedEntityJoiner`, `EVariationMerger`, `OptionalTagger`, `FeatureAnalyzer`, `ReferenceMatcher` + `Creator`, `StructuralVariationSorter`).
- Extratores `mongodb2uschema.spark` e `neo4j2uschema` em **PySpark**.

**Fica de fora — e por quê (status corrigido):**
- **OCL** — **ausente neste metamodelo**. O `uschema.ecore` não tem nenhuma constraint OCL (nem EAnnotations). Não-questão. (Se houvesse, seriam invariantes reescritas como checagens Python — não exige motor OCL.)
- **Codegen EMF** — existe `pyecoregen`, e o PyEcore reflexivo dispensa codegen. Não é barreira.
- **Sirius / editor visual** (`es.um.uschema.design`) — único item sem equivalente pronto em Python. **Está fora do escopo do porte fiel** (é UI) e, se um dia for desejado, é reconstruível com outra stack (web: React Flow / Cytoscape) — trabalho futuro, não impossibilidade.

> **Não há impossibilidade no objetivo.** Toda "limitação" é da forma "sem drop-in equivalente ao do Eclipse → reimplementar o comportamento ou usar outra stack". É esforço e tempo, não barreira técnica.

---

## 4. Fases

### Fase 0 — Fundação + oráculo · prioridade imediata
1. PyEcore carrega `uschema.ecore`; instanciar `EntityType`, `StructuralVariation`, `Aggregate`, `Attribute`, `Reference`.
2. Round-trip XMI: ler `model_northwind.xmi`, reserializar, validar.
3. **Harness de equivalência estrutural** (não textual): compara conjuntos de entidades, variações e contagens entre dois XMIs. É o critério de aceite de todas as fases seguintes.
4. **Docker como andaime:** a ferramenta Java patcheada, isolada em imagem (JDK 8 + Spark + patches #6/#7), serve só para **gerar os XMIs de referência** de forma reproduzível. Não é a entrega — é o gerador do oráculo.

### Fase 1 — Núcleo de inferência (`doc2uschema`) · a espinha
- Modelos intermediários `raw`/`firsto` → `dataclasses` (Composite vira árvore recursiva).
- `SchemaInference.infer`: recursão JSON → `SchemaComponent`; **igualdade estrutural** e **ordenação de campos** replicadas fielmente (são o que torna o porte verificável); objetos aninhados viram entidades internas.
- Estratégias: `joiner` (une aliases), `merger` (funde variações equivalentes), `optionalTagger`/`featureAnalyzer` (opcionalidade entre variações), `referenceMatcher` (+`creator`; detecção de `Reference` por id, só entidades com variação raiz), `varSorter` (ordem determinística).
- `USchemaModelBuilder.build` + `fillEV`: `Attribute` / `Aggregate` / `Reference`; depois `sort` + `setOptionalProperties`.
- Guice **desaparece** (wiring por construtor, que já existe); `abstractjson` **desaparece** (`dict`/`bson` nativo).
- **Gate:** cada módulo reproduz o XMI-oráculo estruturalmente.

### Fase 2 — Extratores em PySpark (MongoDB + Neo4j)
- Portar a função de assinatura (`ArchetypeMapping` / `IdArchetypeMapping`) para funções Python puras; pipeline `rdd.map(...).reduceByKey(add)...` produzindo as triplas.
- Conectores via `spark.jars.packages` (mongo-spark-connector 3.0.1; neo4j-spark-connector — validar versão, o legado conectou no 2026.05.0).
- **Gate:** contagem de assinaturas idêntica ao Java; XMI final ≡ oráculo, para os dois paradigmas.

### Fase 3 — Ponta a ponta + escala
- Corretude: Northwind e Sakila.
- Escala: User Profiles (quatro tamanhos), reproduzindo a tendência da Tabela 4 do artigo em PySpark.
- Bugs **#6/#7 corrigidos por construção** (tratar `_id` inteiro e array vazio desde o início, em vez de patch) — material direto para o capítulo de reprodutibilidade.

---

## 5. Riscos e pontos de atenção

O risco é **tempo**, não impossibilidade. Com a metacamada fora do caminho crítico, a estimativa de 4–6 pessoa-meses registrada na avaliação inicial (jun/2026) deixa de ser "não cabe" e passa a ser **plausível como o próprio TCC**, com dois autores em 6 meses.

- **Paralelização:** o núcleo de inferência (Fase 1) e os extratores + um paradigma (Fase 2) avançam **em paralelo**, encontrando-se pelo formato da tripla. O trabalho é **compartilhado** entre os dois autores, sem dono fixo por fase.
- **Watch-items de fidelidade** (reproduzíveis, exigem cuidado): o **Inflector** (capitalização/pluralização dos nomes de entidade tem de casar — há libs de inflection em Python, mas talvez seja preciso reproduzir as regras exatas); o **determinismo** (ordenação de campos, `equals` estrutural, ordem das variações); e a natureza **estrutural-não-byte** da comparação de XMI.

---

## 6. Resumo das fases

| Fase | Entrega | Gate de aceite |
|---|---|---|
| 0 | PyEcore + round-trip + harness de equivalência + oráculo Java em Docker | round-trip do Northwind fecha |
| 1 | núcleo `doc2uschema` em Python (inferência completa) | cada módulo ≡ XMI-oráculo (estrutural) |
| 2 | extratores MongoDB + Neo4j em PySpark | contagens == Java; XMI ≡ oráculo |
| 3 | ponta a ponta, corretude + escala, bugs corrigidos | Northwind/Sakila ok; tendência Tabela 4 reproduzida |

**Sequência:** 0 → 1 → 2 → 3. Metacamada: trabalho futuro. Sirius/UI: fora de escopo (reconstruível em outra stack se desejado).
