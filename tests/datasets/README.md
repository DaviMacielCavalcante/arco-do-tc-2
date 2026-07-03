# tests/datasets/ — golden-master por dataset (Fases 1.5 e 3)

Validação **ponta a ponta sem depender de Docker**: cada teste roda a inferência
sobre um dataset conhecido e compara o XMI resultante com o esperado, via
`uschema.validation.compare_uschemas`.

Portados do JUnit de dataset do repo: `UserProfileTest`, `EveryPoliticianTest`,
`CompaniesTest`, `FacebookTest`, `StackOverflowTest`, além de Northwind
(golden-master principal da Fase 1) e Sakila (segundo ponto de corretude, Fase 3).

Datasets **sem** golden-master pronto (Sakila, variações de escala) usam o
oráculo em Docker (`oracle/`) para gerar o gabarito.
