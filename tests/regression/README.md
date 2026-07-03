# tests/regression/ — testes de regressão portados do JUnit (Fase 1.6)

A camada de validação **mais barata e localizante**: cada JUnit minúsculo do
repositório Java vira um teste pytest com a **mesma entrada** e as **mesmas
asserções**, localizando o erro no módulo antes de qualquer rodada ponta a ponta.

Mapeamento teste → módulo do porte:

| JUnit (Java) | Módulo | O que fixa |
|---|---|---|
| `CountTimestampTest` | `inference.schema_inference` (1.2) | count/timestamp por variação; em não-raiz, copiados do pai (**#8**) |
| `ObjectIdTest` | `inference.schema_inference` / tipos (1.2) | distinguir ObjectId de String (**#6**) |
| `TypesTest` | 1.2 / 1.4 | inferência de tipos primitivos |
| `OptionalTest` | `inference.strategies` (1.3) | opcionalidade entre variações |
| `SimplifyAggrTest` | `inference.strategies` — merger (1.3) | merge de agregados equivalentes |
| `RelationshipTypeToEntityTypeTest` | `inference.builder` (1.4) | referência × relacionamento |
| `RemovePMapTest` | `intermediate.raw` / builder | remoção de PMap |
| `InflectorTest` | `naming.inflector` (0.6) | capitalização/pluralização |
| `SimplificationTest`, `PairOperationsTest` (Mongo) | `extractors.mongo` (2.1) | simplificação e operações de par |

> **Onde você corrigiu um bug (#6/#7/#8)**, porte a *estrutura* do teste mas
> afirme o valor **corrigido**. Para o #8, **acrescente** um teste novo com
> array de tamanho variável afirmando a contagem correta (soma = volume real).

Os dados (`testSources/*.json`) vêm junto — versionar em `tests/fixtures/`.
