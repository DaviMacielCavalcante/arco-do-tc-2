# resources/

Artefatos de referência versionados, consumidos pelo porte e pelos testes.

| Arquivo | Papel |
|---|---|
| `uschema.ecore` | Metamodelo (19 EClasses, sem OCL). Carregado por `uschema.metamodel` (Fase 0.1). |
| `model_northwind.xmi` | XMI-oráculo do Northwind (19 `EntityType`, agregado `Detail`). Round-trip da Fase 0.2 e golden-master da Fase 3. |
| `model.xmi` | Modelo mínimo MongoDB (round-trip Fase 0.2). |
| `movies_min.xmi` | Modelo mínimo Neo4j, com `RelationshipType` (round-trip Fase 0.2). |

> Copie estes arquivos do repositório Java original / do oráculo em Docker
> (`oracle/`). São **entrada** do porte, não gerados por ele.
