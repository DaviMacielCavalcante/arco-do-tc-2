# Fase 0 — Fundação + oráculo (guia detalhado)

**Parte de:** `roadmap_portabilidade.md` · **Validação:** `roteiro_experimental.md` · **Base técnica:** `analise_ferramenta_uschema.md`
**Entregável:** fundação + oráculo (trabalho compartilhado) · **Prioridade:** imediata (pré-requisito de todas as fases)

## Objetivo

Estabelecer a fundação Python e, sobretudo, a **estratégia de validação** do porte. Quatro entregas: (1) a **camada de metamodelo em Python** (PyEcore operando `uschema.ecore`); (2) o **harness de equivalência estrutural**, espelhando o comparador `USchemaCompareMain` que **já existe** no Java; (3) o aproveitamento da **suíte de testes JUnit existente** no repositório (regressão + golden-master por dataset) como critério **primário** de correção; (4) o **oráculo em Docker** como gerador de gabarito apenas para datasets **sem** teste pronto. O ponto central: a correção do porte não vem de uma fonte só, vem em **camadas** (ver 0.4) — e a mais forte e barata (testes de regressão portados) localiza o erro no módulo, sem depender de Docker.

---

## 0.1 PyEcore sobre o `uschema.ecore`

O metamodelo é pequeno e favorável: **19 EClasses em 98 linhas, sem OCL e sem EAnnotations** (puramente estrutural). Hierarquia a instanciar: `USchema` (raiz) → `SchemaType` (abstrata) → `EntityType` / `RelationshipType`; cada `SchemaType` agrega `StructuralVariation` (com `count: long`); cada variação contém `Feature` → `Attribute` (com `Type`: primitivo ou Tuple/Set/Map/List), `Key`, `Aggregate` (cardinalidade + `refsTo`), `Reference` (com `opposite`).

**Tarefas:**
- [ ] Instalar PyEcore (`pip install pyecore`) e carregar `uschema.ecore` via `ResourceSet`/`metamodel_resource`.
- [ ] Confirmar acesso reflexivo às 19 EClasses; criar manualmente um `USchema` mínimo (1 `EntityType`, 1 `StructuralVariation`, 1 `Attribute`) e serializar em XMI.
- [ ] Decidir entre **API reflexiva** (manipular `EObject` dinamicamente) e **`pyecoregen`** (gerar classes Python a partir do `.ecore`). Recomendação inicial: reflexivo, para não acoplar a uma etapa de codegen; reavaliar se a ergonomia incomodar.
- [ ] Tratar o gap conhecido do PyEcore: `genmodel` multi-arquivo não é suportado — se o `.ecore` referenciar outros pacotes, achatar para um único EPackage no fork.

**Saída:** um módulo Python que cria, lê e serializa modelos U-Schema em XMI.

## 0.2 Round-trip de XMI

**Tarefas:**
- [ ] Ler `model_northwind.xmi` (19 `EntityType`, incluindo o agregado `Detail`) com PyEcore.
- [ ] Reserializar e validar que o modelo recarregado é estruturalmente idêntico ao original.
- [ ] Repetir com `model.xmi` (mínimo MongoDB) e `movies_min.xmi` (mínimo Neo4j, com `RelationshipType`).

> O round-trip **não precisa** ser idêntico byte a byte — o EMF tem convenções próprias de `xmi:id`/ordenação. O que se valida é a **equivalência estrutural** (ver 0.3).

## 0.3 Harness de equivalência estrutural

O instrumento central de validação de todo o porte. Compara dois XMIs no nível do **modelo**, não do texto.

> **Não inventar do zero — espelhar o `USchemaCompareMain`.** O repositório Java já traz um comparador de U-Schema (`es.um.uschema.*.validation/USchemaCompareMain`), com `startComparison(USchema s1, USchema s2)` que compara nome → contagem de `EntityType`/`RelationshipType` → variações (via `CompareSchemaType`/`CompareStructuralVariation`), com log de *hits*/*warnings* e normalização de caixa. O harness Python deve **reproduzir a mesma noção de equivalência** — assim você não fica nem mais rígido nem mais frouxo que o original, e ganha a lógica de comparação de graça.

**Compara (deve coincidir):**
1. Conjunto de `EntityType` (nomes após normalização do Inflector) + flag `root`.
2. Conjunto de `RelationshipType` (paradigma grafo) + propriedades.
3. Por entidade: conjunto de `StructuralVariation` (mesma cardinalidade; mesma assinatura de features por variação).
4. Por variação: `Attribute` (tipo), `Aggregate` (cardinalidade, alvo `refsTo`, `optional`), `Reference` (alvo, `opposite`), flag `optional`.
5. `count` por variação (e timestamps, quando aplicável).

**Ignora:** `xmi:id`, ordem de serialização, formatação.

**Esboço do algoritmo:**
```
carregar A (oráculo) e B (porte) via PyEcore
indexar entidades por nome normalizado
para cada entidade em A ∪ B:
    comparar presença, flag root
    indexar variações por assinatura canônica de features
    para cada variação:
        comparar features (tipo/cardinalidade/alvo/opcional) e count
acumular divergências por categoria: {entidade, variacao, feature, contagem}
retornar: equivalente? + lista de divergências classificadas
```

**Tarefas:**
- [ ] Ler `USchemaCompareMain` (+ `CompareSchemaType`/`CompareStructuralVariation`) e replicar sua semântica de comparação no Python.
- [ ] Implementar a assinatura canônica de uma variação (conjunto ordenado de `(nome, tipo, papel)` das features).
- [ ] Implementar a comparação e o relatório de divergências por categoria (essencial para diagnosticar onde o porte divergiu).
- [ ] Testar o harness contra ele mesmo (A == A → equivalente) e contra um XMI deliberadamente alterado (deve apontar a categoria certa).

**Saída:** `equivalencia.py` reutilizável nas Fases 1, 2 e 3.

## 0.4 Estratégia de validação e a suíte de testes Java existente

A correção do porte vem em **quatro camadas**, da mais barata/localizante para a mais ampla:

1. **Testes de regressão portados (unitários).** O repositório Java tem JUnit de regressão que fixam comportamento de casos minúsculos — e cobrem exatamente os pontos arriscados: `CountTimestampTest` (contagem/timestamp por variação — área do bug #8; documenta que em entidades não-raiz o count/timestamp é copiado do pai), `ObjectIdTest` (distinguir String de ObjectId — bug #6; dado em `testSources/ObjectIds.json`), `InflectorTest` (capitalização/pluralização), `OptionalTest`, `TypesTest`, `SimplifyAggrTest`, `RelationshipTypeToEntityTypeTest`, `RemovePMapTest`, e no Mongo `SimplificationTest`/`PairOperationsTest`. **Cada um vira um teste Python** com a mesma entrada e as mesmas asserções. É a camada que **localiza** o erro no módulo, antes de qualquer rodada ponta a ponta (validam a Fase 1 enquanto ela é escrita).
2. **Testes de dataset (golden-master).** `UserProfileTest`, `EveryPoliticianTest`, `CompaniesTest`, `FacebookTest`, `StackOverflowTest` etc. — cada um roda a inferência sobre um dataset conhecido e compara o XMI esperado. Portados, viram validação ponta a ponta **sem depender de Docker**.
3. **Oráculo via Docker (0.5).** Só para datasets **sem** gabarito pronto (Sakila, variações de escala): gera-se o XMI esperado rodando o Java.
4. **Validação contra o banco (opcional).** Os pacotes `*.validation` do Java (`MongoDBValidator`, `Doc2USchemaValidationMain`, os `Neo4j…QueryBuilder`) não são JUnit — são uma ferramenta que consulta o banco de volta e checa se o schema inferido descreve os dados. É uma checagem **independente** de qualquer implementação (confere contra a realidade, não contra outro código). Pode ser portada ou usada como referência cruzada em Java.

> **Cuidado com testes que codificam o bug.** Onde você corrigiu um bug (#6/#7/#8), porte a *estrutura* do teste mas afirme o valor **corrigido**. Na prática, os testes de regressão minúsculos em geral nem disparam o #8 (que só aparece com array de tamanho variável), então a maioria porta limpa; só os das áreas de bug pedem esse ajuste.

**Tarefas:**
- [ ] Inventariar os JUnit do repo (`*/test/regression`, `*/test`, `documents/.../examples/tests`) e seus dados (`testSources/*.json`).
- [ ] Portar **primeiro** os testes de regressão (são o critério de aceite módulo a módulo da Fase 1).
- [ ] Mapear os golden-master de dataset para a Fase 3.

## 0.5 Oráculo Java em Docker (gerador de gabarito + baseline)

Papel **reduzido e opcional**: o Docker serve para (a) **rodar a suíte JUnit existente** e obter o *baseline verde* — confirmando o comportamento esperado e reaproveitando dados/saídas de teste; e (b) **gerar o XMI-gabarito** apenas para datasets que não têm golden-master pronto. **Não entra na entrega** (a ferramenta portada é Python puro), e é dispensável no dia a dia se você guardar os XMIs já gerados como gabarito fixo — ele agrega **reprodutibilidade** (regenerar o gabarito de forma idêntica e auditável), não funcionalidade.

Congela o ambiente frágil que já funciona numa imagem, cuja **única saída é o XMI**.

**Conteúdo da imagem:** base JDK 8; Spark + conectores fixados (mongo-spark-connector 3.0.1; neo4j-spark-connector 2.4.5-M2); a `uschema-inference` compilada **com os patches aplicados no build** (`.patch` auditáveis):

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

**Contrato:** `docker run -v $PWD/out:/output extrator-uschema --db <nome> --kind <mongodb|neo4j>` → grava `model.xmi` em `/output`. Rede: usar `--network=host` (Linux) para alcançar bancos no host; memória ≥ ~5–6 GB (Spark pede ~4 GB driver/executor).

**Tarefas:**
- [ ] Escrever o `Dockerfile` (base JDK 8 + Spark + conectores + build com os 8 `.patch`).
- [ ] **Rodar a suíte JUnit existente** dentro da imagem para obter o baseline verde e extrair dados/saídas de teste reaproveitáveis.
- [ ] Validar que a imagem regenera `model_northwind.xmi` (e os XMIs de escala) idênticos estruturalmente aos já gerados.
- [ ] Versionar `Dockerfile` + `.patch` (artefato de reprodutibilidade citável no TCC).

## 0.6 Inflector

A capitalização/pluralização dos nomes de entidade (`Inflector.getInstance().capitalize(...)`, usado em `SchemaInference` e replicado em `mongodb2uschema.spark/Inflector.java`) precisa **casar** com o Java — senão os nomes de `EntityType` divergem e o harness acusa divergência em toda entidade.

**Tarefas:**
- [ ] Ler `Inflector.java` e listar as regras efetivamente usadas (capitalize, singular/plural).
- [ ] Decidir entre uma lib Python (`inflection`/`inflect`) e uma reimplementação fiel das regras específicas.
- [ ] Teste: aplicar a normalização aos nomes do Northwind e comparar com os nomes no XMI-oráculo.

---

## Gate de aceite da Fase 0

- Round-trip do `model_northwind.xmi` fecha (recarrega estruturalmente idêntico).
- Harness de equivalência funcionando (acerta A==A e detecta divergência injetada), com a semântica espelhada do `USchemaCompareMain`.
- Suíte JUnit do repositório inventariada, com os testes de regressão mapeados para a Fase 1 e os golden-master para a Fase 3.
- Imagem Docker roda o baseline JUnit e regenera os XMIs-gabarito de forma reproduzível.

## Entregáveis

`metamodelo.py` (PyEcore), `equivalencia.py` (harness espelhando `USchemaCompareMain`), inventário/mapa dos testes JUnit a portar, `Dockerfile` + `patches/` (baseline + gabarito), módulo de normalização de nomes (Inflector).

## Riscos da fase

PyEcore não cobrir alguma construção do `.ecore` (mitigar achatando para um EPackage; validar o round-trip contra o EMF uma vez); Inflector divergente (resolver aqui, não na Fase 1); harness mais rígido/frouxo que o `USchemaCompareMain` (mitigar lendo o comparador original); rede/memória do contêiner Docker (documentar `--network=host` e `--memory`).
