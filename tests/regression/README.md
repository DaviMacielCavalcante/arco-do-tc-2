# tests/regression/ — testes de regressão portados do JUnit (Fase 1.6)

A camada de validação **mais barata e localizante**: cada JUnit minúsculo do
repositório Java vira um teste pytest com a **mesma entrada** e as **mesmas
asserções**, localizando o erro no módulo antes de qualquer rodada ponta a ponta.

> 📋 **O inventário completo está em [`INVENTARIO.md`](INVENTARIO.md)** (entrega da
> Fase 0.4): os 37 `*Test.java` do original classificados, o que portar, para onde,
> em que ordem, e o que **não** portar. Leia antes de portar qualquer um.

Dois pontos do inventário que contrariam a suposição inicial do roadmap:

1. **Metade dos testes "de regressão" exige um MongoDB de pé** —
   `CountTimestampTest`, `ObjectIdTest`, `TypesTest` e `SimplifyAggrTest` injetam o
   JSON no banco e rodam o map-reduce **no Mongo** antes de inferir. Não são
   testes puros.
2. **Dá para portá-los sem banco, cortando o pipeline na tripla** — a saída do
   map-reduce (`{schema, count, firstTimestamp, lastTimestamp}`) é exatamente o
   contrato de `extractors/triple.py`. Congelada como fixture, a inferência é
   testada em unidade. É o que os testes puros do `doc2uschema` já fazem.

Mapeamento teste → módulo do porte:

| JUnit (Java) | Módulo | O que fixa | Precisa de banco? |
|---|---|---|---|
| `InflectorTest` | `naming.inflector` (0.6) | capitalização/pluralização | não — **desbloqueado hoje** |
| `J2SchemaSimpleTests` | `intermediate.raw` (1.1) | JSON → schema cru | não |
| `OptionalTest` | `inference.strategies` (1.3) | opcionalidade entre variações | não |
| `RemovePMapTest` | `intermediate.raw` / builder | remoção de PMap | não |
| `RelationshipTypeToEntityTypeTest` | `inference.builder` (1.4) | referência × relacionamento | não |
| `SimplificationTest`, `PairOperationsTest` | `extractors.mongo` (2.1) | simplificação e operações de par | não |
| `CountTimestampTest` | `inference.schema_inference` (1.2) | count/timestamp por variação (**#8**) | sim → cortar na tripla |
| `ObjectIdTest` | tipos (1.2) | distinguir ObjectId de String (**#6**) | sim → cortar na tripla |
| `TypesTest` | 1.2 / 1.4 | o `_type` interno não vaza para o modelo | sim → cortar na tripla |
| `SimplifyAggrTest` | `inference.strategies` (1.3) | merge de agregados equivalentes | sim → cortar na tripla |

> **Onde você corrigiu um bug (#6/#7/#8)**, porte a *estrutura* do teste mas
> afirme o valor **corrigido**. Para o #8, **acrescente** um teste novo com
> array de tamanho variável afirmando a contagem correta (soma = volume real).
> O **#7** (array vazio) não tem JUnit nenhum — é teste novo.

Os dados (`testSources/*.json`) vêm junto — versionar em `tests/fixtures/`.
